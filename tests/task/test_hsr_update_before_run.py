"""HSR 双引擎运行前更新、安装取消和异常状态保护。"""

import asyncio
import threading
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.task.HSR import manager
from app.task.HSR.tools import update
from app.task.HSR.tools.update import apply as installer


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    instance = object.__new__(manager.HSRManager)
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(
            AutoUpdateMode="BeforeRun",
            Channel="stable",
            MirrorChyanCDK="",
            M7ASource="GitHub",
            SRASource="AutoSite",
        )
    )
    instance.script_info = SimpleNamespace(script_id=str(uuid.uuid4()))
    instance.check_result = "Pass"
    instance.stopped_manually = False
    instance.crashed = False
    instance._append_log = Mock()
    instance._update_aborted = lambda: False
    monkeypatch.setattr(
        manager, "resolve_script_path", lambda config, engine: str(tmp_path / engine)
    )
    monkeypatch.setattr(manager, "Config", SimpleNamespace(proxy=None))
    monkeypatch.setattr(
        update,
        "update_engine_if_needed",
        AsyncMock(return_value=SimpleNamespace(blocking=False)),
    )
    return instance


@pytest.mark.asyncio
async def test_disabled_update_does_not_download(scheduler):
    scheduler.script_config.Update.AutoUpdateMode = "Off"
    await scheduler._update_external_scripts()
    update.update_engine_if_needed.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsafe_install_stops_before_second_engine(scheduler):
    update.update_engine_if_needed.return_value = SimpleNamespace(
        blocking=True, message="unsafe"
    )
    assert await scheduler._update_external_scripts() == "unsafe"
    assert update.update_engine_if_needed.await_count == 1


@pytest.mark.asyncio
async def test_pending_journal_that_cannot_roll_back_blocks_start(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(update, "has_pending_journal", lambda root: True)
    monkeypatch.setattr(update, "rollback", lambda root: False)
    with pytest.raises(update.HSRUpdateError):
        await update.rollback_pending(tmp_path)


@pytest.mark.asyncio
async def test_install_worker_finishes_writes_before_cancellation_returns():
    started = threading.Event()
    finish = threading.Event()
    written = threading.Event()

    def install():
        started.set()
        assert finish.wait(5)
        written.set()

    task = asyncio.create_task(update._run_install_worker(install))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not written.is_set()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written.is_set()


def test_failed_rollback_is_reported_as_unsafe(tmp_path, monkeypatch):
    root = tmp_path / "script"
    root.mkdir()
    (root / "SRA-cli.exe").write_bytes(b"old")
    package = tmp_path / "package.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("SRA-cli.exe", b"new")
    monkeypatch.setattr(installer, "_commit", Mock(side_effect=OSError("write failed")))
    monkeypatch.setattr(installer, "rollback", lambda root: False)
    with pytest.raises(installer.HSRUpdateApplyError) as error:
        installer.apply_package(
            package,
            root,
            engine="SRA",
            from_version="1.0",
            to_version="2.0",
            seven_zip=None,
        )
    assert error.value.rolled_back is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine,exe", [("M7A", "March7th Assistant.exe"), ("SRA", "SRA-cli.exe")]
)
@pytest.mark.parametrize("prefetch", [False, True])
async def test_reused_pipeline_installs_package_and_preserves_user_files(
    tmp_path, monkeypatch, engine, exe, prefetch
):
    root = tmp_path / "script"
    root.mkdir()
    (root / exe).write_bytes(b"old engine")
    config = root / "user-custom-config.json"
    config.write_bytes(b"user settings")
    package = tmp_path / "package.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(exe, b"new engine")
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate

    candidate = UpdateCandidate(
        engine, "1.0", "2.0", "MirrorChyan", "zip", "https://example.invalid/package"
    )
    monkeypatch.setattr(
        update,
        "check_engine_update",
        AsyncMock(return_value=DiscoveryResult(engine, "1.0", "2.0", True, candidate)),
    )
    monkeypatch.setattr(
        update, "_download_with_space_check", AsyncMock(return_value=package)
    )
    monkeypatch.setattr(update, "check_no_process_running", lambda root: None)
    monkeypatch.setattr(update, "check_writable", lambda root: None)
    monkeypatch.setattr(update, "check_disk_space", lambda **kwargs: None)
    prepared = None
    if prefetch:
        monkeypatch.setattr(update, "read_installed_version", lambda *args: "1.0")
        prepared = await update.prepare_engine_update(
            engine,
            root,
            source="MirrorChyan",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=tmp_path,
        )
        assert (root / exe).read_bytes() == b"old engine"
        assert not installer.has_pending_journal(root)
    result = await update.update_engine_if_needed(
        engine, root, source="MirrorChyan", download_dir=tmp_path, prepared=prepared
    )
    assert result.updated
    assert not result.blocking
    assert (root / exe).read_bytes() == b"new engine"
    assert config.read_bytes() == b"user settings"
    assert not installer.has_pending_journal(root)
    update.check_engine_update.assert_awaited_once()
    update._download_with_space_check.assert_awaited_once()


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.txt",
        "/tmp/outside.txt",
        "C:/outside.txt",
        "sub/../outside.txt",
        "sub\\outside.txt",
    ],
)
def test_unsafe_rollback_journal_never_changes_other_files(tmp_path, unsafe_path):
    import json

    root = tmp_path / "script"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    journal = installer.journal_path(root)
    journal.parent.mkdir(parents=True)
    journal.write_text(
        json.dumps(
            {
                "schema": 1,
                "engine": "SRA",
                "entries": [{"rel": unsafe_path, "action": "create"}],
            }
        ),
        encoding="utf-8",
    )
    assert installer.rollback(root) is False
    assert journal.exists()
    assert outside.read_bytes() == b"keep"


def test_rollback_journal_validates_all_entries_before_mutating(tmp_path):
    import json

    root = tmp_path / "script"
    root.mkdir()
    first = root / "created.txt"
    first.write_text("must be preserved")
    journal = installer.journal_path(root)
    journal.parent.mkdir(parents=True)
    journal.write_text(
        json.dumps(
            {
                "schema": 1,
                "engine": "SRA",
                "entries": [
                    {"rel": "created.txt", "action": "create"},
                    {"rel": "../outside.txt", "action": "create"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert installer.rollback(root) is False
    assert first.read_text() == "must be preserved"
