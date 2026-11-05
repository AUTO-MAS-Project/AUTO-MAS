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


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["M7A", "SRA"])
async def test_cancelled_builtin_prefetch_removes_private_partial(
    tmp_path, monkeypatch, engine
):
    """Cancel after actual HSR download dispatch has written some bytes."""
    from app.task.HSR.tools.update import download as transport
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate

    candidate = UpdateCandidate(
        engine, "1.0", "2.0", "GitHub", "zip", "https://example.invalid/pkg"
    )
    monkeypatch.setattr(
        update,
        "check_engine_update",
        AsyncMock(return_value=DiscoveryResult(engine, "1.0", "2.0", True, candidate)),
    )
    monkeypatch.setattr(update, "_remote_size", AsyncMock(return_value=0))
    started = asyncio.Event()

    async def interrupted(_url, destination, **_kwargs):
        destination.write_bytes(b"partial bytes")
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(transport, "download_script_package", interrupted)
    root = tmp_path / "script"
    root.mkdir()
    downloads = tmp_path / "downloads"
    task = asyncio.create_task(
        update.prepare_engine_update(
            engine,
            root,
            source="GitHub",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=downloads,
        )
    )
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list(downloads.rglob("*.part"))
    assert not list(downloads.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,keep",
    [
        ("ordinary", False),
        ("unsafe", True),
        ("resumable", True),
    ],
)
async def test_hsr_prefetch_failure_releases_only_owned_files(
    tmp_path, monkeypatch, failure, keep
):
    """Do not delete FluxDown-owned segments from an unreturned candidate."""
    from app.services.common.update.fluxdown import FluxdownResumableError
    from app.task.HSR.tools.update import download as transport
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate
    from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

    candidate = UpdateCandidate(
        "M7A", "1.0", "2.0", "GitHub", "zip", "https://example.invalid/pkg"
    )
    monkeypatch.setattr(
        update,
        "check_engine_update",
        AsyncMock(return_value=DiscoveryResult("M7A", "1.0", "2.0", True, candidate)),
    )
    monkeypatch.setattr(update, "_remote_size", AsyncMock(return_value=0))
    monkeypatch.setattr(transport, "_RETRY_DELAY", 0)

    async def interrupted(_url, destination, **_kwargs):
        destination.write_bytes(b"partial bytes")
        if failure == "unsafe":
            raise FluxdownCancelUnconfirmed("daemon may still write")
        if failure == "resumable":
            raise FluxdownResumableError("resume later")
        raise OSError("connection reset")

    monkeypatch.setattr(transport, "download_script_package", interrupted)
    root = tmp_path / "script"
    root.mkdir()
    downloads = tmp_path / "downloads"
    exception = {
        "ordinary": update.HSRUpdateError,
        "unsafe": FluxdownCancelUnconfirmed,
        "resumable": FluxdownResumableError,
    }[failure]
    with pytest.raises(exception):
        await update.prepare_engine_update(
            "M7A",
            root,
            source="GitHub",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=downloads,
        )
    assert bool(list(downloads.rglob("*.part"))) is keep
    assert bool(list(downloads.iterdir())) is keep


@pytest.mark.asyncio
async def test_hsr_prefetch_digest_failure_cleans_package(tmp_path, monkeypatch):
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate

    candidate = UpdateCandidate(
        "M7A", "1.0", "2.0", "GitHub", "zip", "https://example.invalid/pkg"
    )
    monkeypatch.setattr(
        update,
        "check_engine_update",
        AsyncMock(return_value=DiscoveryResult("M7A", "1.0", "2.0", True, candidate)),
    )

    async def downloaded(_candidate, package, **_kwargs):
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b"downloaded")
        return package

    monkeypatch.setattr(update, "_download_with_space_check", downloaded)
    monkeypatch.setattr(
        update, "_package_digest", Mock(side_effect=OSError("digest failed"))
    )
    root = tmp_path / "script"
    root.mkdir()
    downloads = tmp_path / "downloads"
    with pytest.raises(OSError, match="digest failed"):
        await update.prepare_engine_update(
            "M7A",
            root,
            source="GitHub",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=downloads,
        )
    assert not list(downloads.iterdir())


@pytest.fixture
def hsr_prefetch_case(tmp_path, monkeypatch):
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate

    install = tmp_path / "installed"
    install.mkdir()
    download_dir = tmp_path / "prefetch"
    candidate = UpdateCandidate(
        "SRA",
        "1.0",
        "2.0",
        "AutoSite",
        "zip",
        "https://example.invalid/SRA-2.0.zip",
    )
    discovered = DiscoveryResult("SRA", "1.0", "2.0", True, candidate)
    monkeypatch.setattr(
        update, "check_engine_update", AsyncMock(return_value=discovered)
    )
    monkeypatch.setattr(update, "_remote_size", AsyncMock(return_value=0))
    return install, download_dir, candidate


@pytest.mark.asyncio
async def test_prefetch_cancel_after_partial_builtin_download_removes_private_directory(
    hsr_prefetch_case, monkeypatch
):
    """Cancellation through prepare_engine_update must reclaim the UUID stage."""
    from app.task.HSR.tools.update import download as hsr_download

    install, download_dir, _ = hsr_prefetch_case
    started = asyncio.Event()

    async def partial_download(_url, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Keep a real OS handle open until the coroutine receives cancellation.
        with destination.open("wb") as handle:
            handle.write(b"downloaded-but-not-verified")
            handle.flush()
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(hsr_download, "download_script_package", partial_download)
    task = asyncio.create_task(
        update.prepare_engine_update(
            "SRA",
            install,
            source="AutoSite",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=download_dir,
        )
    )
    await asyncio.wait_for(started.wait(), 3)
    assert list(download_dir.rglob("*.part"))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert not list(download_dir.iterdir())
    assert install.is_dir()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["ordinary", "resumable", "writer-unconfirmed"])
async def test_prefetch_failure_cleans_only_when_downloader_releases_ownership(
    hsr_prefetch_case, monkeypatch, failure
):
    from app.services.common.update.fluxdown import FluxdownResumableError
    from app.task.HSR.tools.update import download as hsr_download
    from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

    install, download_dir, _ = hsr_prefetch_case
    monkeypatch.setattr(hsr_download, "_RETRIES", 1)

    async def partial_download(_url, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"partial")
        if failure == "resumable":
            raise FluxdownResumableError("server task can resume")
        if failure == "writer-unconfirmed":
            raise FluxdownCancelUnconfirmed("server writer may be active")
        raise OSError("network lost")

    monkeypatch.setattr(hsr_download, "download_script_package", partial_download)
    exception = (
        FluxdownResumableError
        if failure == "resumable"
        else (
            FluxdownCancelUnconfirmed
            if failure == "writer-unconfirmed"
            else update.HSRUpdateError
        )
    )
    with pytest.raises(exception):
        await update.prepare_engine_update(
            "SRA",
            install,
            source="AutoSite",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=download_dir,
        )
    stages = list(download_dir.iterdir()) if download_dir.exists() else []
    if failure == "ordinary":
        assert not stages
    else:
        assert len(stages) == 1
        assert list(stages[0].glob("*.part"))[0].read_bytes() == b"partial"


@pytest.mark.asyncio
async def test_prefetch_verified_package_transfers_ownership_to_candidate(
    hsr_prefetch_case, monkeypatch
):
    import hashlib

    from app.task.HSR.tools.update import download as hsr_download
    from app.task.HSR.tools.update.discover import DiscoveryResult, UpdateCandidate

    install, download_dir, old = hsr_prefetch_case
    payload = b"verified script package"
    candidate = UpdateCandidate(
        old.engine,
        old.current_version,
        old.latest_version,
        old.source,
        old.asset_kind,
        old.download_url,
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(
        update,
        "check_engine_update",
        AsyncMock(return_value=DiscoveryResult("SRA", "1.0", "2.0", True, candidate)),
    )

    async def download(_url, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return len(payload)

    monkeypatch.setattr(hsr_download, "download_script_package", download)
    prepared = await update.prepare_engine_update(
        "SRA",
        install,
        source="AutoSite",
        channel="stable",
        cdk="",
        proxy=None,
        download_dir=download_dir,
    )
    assert isinstance(prepared, update.PreparedUpdate)
    assert prepared.package.is_file()
    assert prepared.digest == hashlib.sha256(payload).hexdigest()
    assert len(list(download_dir.iterdir())) == 1
    update.discard_prepared_update(prepared)
    assert not list(download_dir.iterdir())


@pytest.mark.asyncio
async def test_prefetch_digest_failure_reclaims_private_directory(
    hsr_prefetch_case, monkeypatch
):
    install, download_dir, _ = hsr_prefetch_case

    async def download(_candidate, package, **_kwargs):
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b"bad file")
        return package

    monkeypatch.setattr(update, "_download_with_space_check", download)
    monkeypatch.setattr(
        update, "_package_digest", Mock(side_effect=OSError("hash failure"))
    )
    with pytest.raises(OSError, match="hash failure"):
        await update.prepare_engine_update(
            "SRA",
            install,
            source="AutoSite",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=download_dir,
        )
    assert not list(download_dir.iterdir())


@pytest.mark.asyncio
async def test_prefetch_cancel_during_first_verify_waits_for_open_file(
    hsr_prefetch_case, monkeypatch
):
    """Verification must release its file handle before Windows stage removal."""
    from app.task.HSR.tools.update import download as hsr_download

    install, download_dir, _ = hsr_prefetch_case
    started, release, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    async def fetch(_url, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"completed package")
        return 17

    def verify(path, _candidate):
        with path.open("rb") as reader:
            started.set()
            try:
                assert release.wait(5)
                assert reader.read() == b"completed package"
            finally:
                finished.set()

    monkeypatch.setattr(hsr_download, "download_script_package", fetch)
    monkeypatch.setattr(hsr_download, "_verify", verify)
    task = asyncio.create_task(
        update.prepare_engine_update(
            "SRA",
            install,
            source="AutoSite",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=download_dir,
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "file cleanup must wait for first verification"
        assert list(download_dir.rglob("*.part"))
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    assert finished.is_set()
    assert not list(download_dir.iterdir())


@pytest.mark.asyncio
async def test_prefetch_preserves_daemon_owned_stage_when_history_is_cancelled(
    hsr_prefetch_case, monkeypatch
):
    """Exercise HSR -> public downloader -> interrupted history -> HSR cleanup."""
    from app.services.common.update import fluxdown as transport
    from app.task.HSR.tools.update import download as hsr_download
    from app.utils.common import fluxdown_cli as cli

    install, download_dir, _ = hsr_prefetch_case
    entered = asyncio.Event()
    cli_exe = download_dir / "fluxdown.exe"

    async def unsafe_probe(*_args, **_kwargs):
        return False

    async def blocked_history(_record):
        entered.set()
        await asyncio.Event().wait()

    async def shared_download(url, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"daemon may still own this")
        return await transport.download_file(
            url,
            destination,
            timeout=10,
            options=transport.FluxdownOptions(
                "builtin", kwargs["source"], str(cli_exe), 8, True
            ),
            downloader="builtin",
            write_history=blocked_history,
            http_download=AsyncMock(return_value=10),
        )

    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: cli_exe)
    monkeypatch.setattr(cli, "_to_thread_strong", unsafe_probe)
    monkeypatch.setattr(cli, "fluxdown_server_mark_failure", lambda *_a: 1)
    monkeypatch.setattr(hsr_download, "download_script_package", shared_download)
    task = asyncio.create_task(
        update.prepare_engine_update(
            "SRA",
            install,
            source="AutoSite",
            channel="stable",
            cdk="",
            proxy=None,
            download_dir=download_dir,
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await asyncio.wait_for(task, 3)
    stages = [stage for stage in download_dir.iterdir() if stage.is_dir()]
    assert len(stages) == 1
    assert list(stages[0].rglob("*.part"))
