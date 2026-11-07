"""运行前更新的准备回退、安装中断恢复与一次更新多用户启动。"""

import asyncio
import hashlib
import sys
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from packaging.version import Version

from app.task.Whimbox import manager
from app.task.Whimbox.tools import update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from app.utils.common.process.runner import ProcessCleanupUnconfirmed


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "Whimbox"
    (root / "python-embedded").mkdir(parents=True)
    (root / update.APP_EXE_NAME).touch()
    (root / update.REL_PYTHON_EXE).touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update, "find_upstream_pids", lambda root: [])
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=False)),
        ),
    )
    wheel = b"official-wheel"
    release = {
        "tag_name": "3.1.1",
        "assets": [
            {
                "name": "whimbox-3.1.1-py3-none-any.whl",
                "digest": "sha256:" + hashlib.sha256(wheel).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))
    monkeypatch.setattr(
        update, "installed_version", AsyncMock(return_value=Version("3.1.0"))
    )
    monkeypatch.setattr(update, "run_python", AsyncMock(return_value=""))

    async def download(url, path, **kwargs):
        path.write_bytes(wheel)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=download))
    return root


@pytest.mark.asyncio
async def test_no_downgrade_or_unnecessary_install(installation, monkeypatch):
    update.installed_version.return_value = Version("3.2.0")
    confirm = AsyncMock()
    monkeypatch.setattr(update, "confirm_usable_installation", confirm)
    await update.ensure_backend_updated(installation)
    update.download_file.assert_not_awaited()
    confirm.assert_awaited_once_with(installation)


@pytest.mark.asyncio
async def test_unconfirmed_build_keeps_downloaded_packages(installation):
    update.run_python.side_effect = ProcessCleanupUnconfirmed("writer not stopped")
    with pytest.raises(ProcessCleanupUnconfirmed):
        await update.prepare_update(installation)
    stages = list((installation.parent / "data/whimbox_update").rglob("download-*"))
    assert len(stages) == 1
    assert list(stages[0].glob("*.whl"))


@pytest.mark.asyncio
async def test_unconfirmed_install_keeps_marker_and_packages(installation):
    candidate = await update.prepare_update(installation)
    update.run_python.side_effect = ProcessCleanupUnconfirmed("writer not stopped")
    with pytest.raises(ProcessCleanupUnconfirmed):
        await update.apply_update(installation, candidate)
    assert update.pending_marker(installation).exists()
    assert candidate.packages.exists() and candidate.wheel.exists()


@pytest.mark.asyncio
async def test_partial_install_blocks_fallback_then_forces_repair(
    installation, monkeypatch
):
    async def fail_install(root, *args, **kwargs):
        if "install" in args:
            raise RuntimeError("interrupted pip")
        return ""

    update.run_python.side_effect = fail_install
    with pytest.raises(RuntimeError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await update.confirm_usable_installation(installation)
    # 版本已写入也不能跳过残留未完成标记。
    update.installed_version.return_value = Version("3.1.1")
    update.run_python.side_effect = None
    await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    installs = [
        call for call in update.run_python.await_args_list if "install" in call.args
    ]
    assert "--force-reinstall" in installs[-1].args


@pytest.mark.asyncio
@pytest.mark.parametrize("resumable", [False, True])
async def test_failed_prefetch_cleans_download_stage(installation, resumable):
    from app.services.common.update.fluxdown import FluxdownResumableError

    error = FluxdownResumableError if resumable else TimeoutError
    update.download_file.side_effect = error("network unavailable, stopped")
    with pytest.raises(error):
        await update.prepare_update(installation)
    assert not list((installation.parent / "data/whimbox_update").rglob("download-*"))


@pytest.mark.asyncio
async def test_stale_no_update_prefetch_rechecks_pending_marker(installation):
    update.pending_marker(installation).touch()
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await update.apply_update(installation, "already up to date")


@pytest.mark.asyncio
async def test_bad_download_never_starts_installation(installation):
    update.request_release.return_value["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    update.run_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefetch_only_builds_dependencies_and_rejects_tampering(installation):
    candidate = await update.prepare_update(installation)
    assert isinstance(candidate, update.PreparedUpdate)
    assert all("install" not in call.args for call in update.run_python.await_args_list)
    assert not update.pending_marker(installation).exists()
    candidate.wheel.write_bytes(b"tampered")
    try:
        with pytest.raises(RuntimeError):
            await update.apply_update(installation, candidate)
        assert not update.pending_marker(installation).exists()
        assert all(
            "install" not in call.args for call in update.run_python.await_args_list
        )
    finally:
        update.discard_update(candidate)


@pytest.mark.asyncio
async def test_install_cancel_keeps_marker(installation):
    async def cancel_install(root, *args, **kwargs):
        if "install" in args:
            raise asyncio.CancelledError()
        return ""

    update.run_python.side_effect = cancel_install
    with pytest.raises(asyncio.CancelledError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()


@pytest.mark.asyncio
async def test_version_mismatch_keeps_marker(installation):
    with pytest.raises(RuntimeError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()


def test_access_lock_excludes_same_installation(installation):
    with update.installation_access(installation):
        with pytest.raises(RuntimeError):
            with update.installation_access(installation):
                pytest.fail("concurrent installation access")
    with update.installation_access(installation):
        pass


@pytest.fixture
def managed_batch(installation, monkeypatch):
    instance = object.__new__(manager.WhimboxManager)
    users = [
        SimpleNamespace(user_id=str(uuid.uuid4()), status="等待") for _ in range(2)
    ]
    instance.script_info = SimpleNamespace(
        script_id=str(uuid.uuid4()), user_list=users, current_index=0, log=""
    )
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=True)
    )
    instance.user_config = {uuid.UUID(user.user_id): object() for user in users}
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id="test")
    instance.check_result = "Pass"
    instance.check_user_before_run = AsyncMock(return_value=True)
    instance.run_user_task = AsyncMock()
    monkeypatch.setattr(
        manager,
        "AutoProxyTask",
        lambda **kwargs: SimpleNamespace(check=AsyncMock(return_value="Pass")),
    )
    monkeypatch.setattr(
        manager, "ensure_backend_updated", AsyncMock(return_value="updated")
    )
    monkeypatch.setattr(manager, "confirm_usable_installation", AsyncMock())
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), ValueError(), OSError()])
async def test_preparation_failure_warns_and_continues(
    managed_batch, installation, error
):
    manager.ensure_backend_updated.side_effect = error
    await managed_batch._run_prepared(installation)
    manager.confirm_usable_installation.assert_awaited_once_with(installation)
    assert managed_batch.run_user_task.await_count == 2
    assert managed_batch.check_result == "Pass"
    manager.Publisher.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        FluxdownCancelUnconfirmed("active"),
        update.WhimboxUpdateUnsafeError("partial"),
    ],
)
async def test_unsafe_or_cancelled_update_never_falls_back(
    managed_batch, installation, error
):
    manager.ensure_backend_updated.side_effect = error
    with pytest.raises(type(error)):
        await managed_batch._run_prepared(installation)
    manager.confirm_usable_installation.assert_not_awaited()
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_rejects_unusable_installation(managed_batch, installation):
    manager.ensure_backend_updated.side_effect = TimeoutError()
    manager.confirm_usable_installation.side_effect = update.WhimboxUpdateUnsafeError(
        "unusable"
    )
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await managed_batch._run_prepared(installation)
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_takeover_cannot_bypass_partial_install(
    managed_batch, installation
):
    managed_batch.script_config.Update.TakeoverEnabled = False
    update.pending_marker(installation).touch()
    with pytest.raises(RuntimeError):
        await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_not_awaited()
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_update_prefetch_is_rechecked_at_launch(managed_batch, installation):
    managed_batch._update_candidate = "backend already up to date"
    await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_awaited_once_with(installation)
    assert managed_batch.run_user_task.await_count == 2


@pytest.mark.asyncio
async def test_disabled_takeover_keeps_existing_run(managed_batch, installation):
    managed_batch.script_config.Update.TakeoverEnabled = False
    await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_not_awaited()
    assert managed_batch.run_user_task.await_count == 2


@pytest.mark.asyncio
async def test_dependency_download_failure_does_not_dirty_installation(installation):
    update.run_python.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    assert all("install" not in call.args for call in update.run_python.await_args_list)


def test_release_must_match_official_package_and_digest():
    with pytest.raises(ValueError):
        update.select_wheel(
            {"tag_name": "3.1.1", "assets": [{"name": "other-3.1.1-py3-none-any.whl"}]}
        )
    with pytest.raises(ValueError):
        update.select_wheel(
            {
                "tag_name": "3.1.1",
                "assets": [
                    {"name": "whimbox-3.1.1-py3-none-any.whl", "digest": "invalid"}
                ],
            }
        )


@pytest.mark.asyncio
async def test_app_repair_does_not_bypass_pending_marker(installation):
    marker = update.pending_marker(installation)
    marker.write_text("3.1.1", encoding="utf-8")
    update.installed_version.return_value = Version("3.1.1")
    with pytest.raises(update.WhimboxUpdateUnsafeError) as error:
        await update.confirm_usable_installation(installation)
    assert str(error.value) == update.RECOVERY_HINT
    assert marker.exists()
    update.installed_version.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation", ["verify_digest", "_package_hashes", "_wheel_digest"]
)
async def test_prefetch_cancel_waits_for_readers_before_removing_package(
    installation, monkeypatch, operation
):
    started, release = threading.Event(), threading.Event()
    original = getattr(update, operation)

    def read(path, *args):
        package = path if path.is_file() else path / "dependency.whl"
        if not package.exists():
            package.write_bytes(b"dependency")
        with package.open("rb"):
            started.set()
            assert release.wait(5)
            return original(path, *args)

    monkeypatch.setattr(update, operation, read)
    task = asyncio.create_task(update.prepare_update(installation))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert list((installation.parent / "data/whimbox_update").rglob("*.whl"))
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert not list((installation.parent / "data/whimbox_update").rglob("download-*"))


@pytest.mark.asyncio
async def test_repeated_prefetch_cancel_waits_for_stage_removal(
    installation, monkeypatch
):
    started, release = threading.Event(), threading.Event()
    remove = update.shutil.rmtree

    def remove_stage(path, *args, **kwargs):
        if path.name.startswith("download-"):
            started.set()
            assert release.wait(5)
        return remove(path, *args, **kwargs)

    monkeypatch.setattr(update.shutil, "rmtree", remove_stage)
    update.download_file.side_effect = asyncio.CancelledError()
    task = asyncio.create_task(update.prepare_update(installation))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done, "清理目录的线程仍在执行，预取还不能交还所有权"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert not list((installation.parent / "data/whimbox_update").rglob("download-*"))


@pytest.mark.asyncio
async def test_python_probes_leave_cold_installation_modules_unchanged(
    tmp_path, monkeypatch
):
    """预取的版本探测/构建导入不能给正在运行的安装补写 pyc 文件。"""
    root = tmp_path / "Whimbox"
    modules = root / "python-embedded" / "Lib" / "site-packages"
    modules.mkdir(parents=True)
    (modules / "mas_prefetch_probe.py").write_text("value = 'read-only'\n")
    run = update.ProcessRunner.run_process

    async def run_test_python(program, *args, **kwargs):
        assert program == root / update.REL_PYTHON_EXE
        return await run(sys.executable, *args, **kwargs)

    monkeypatch.setattr(update.ProcessRunner, "run_process", run_test_python)
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import mas_prefetch_probe; print(mas_prefetch_probe.value, flush=True)"
    )
    result = await update.run_python(
        root,
        "-c",
        probe + "; import subprocess; subprocess.run("
        "[sys.executable, '-c', sys.argv[2], sys.argv[1]], check=True)",
        str(modules),
        probe,
    )
    assert result.splitlines() == ["read-only", "read-only"]
    assert sorted(path.name for path in modules.iterdir()) == ["mas_prefetch_probe.py"]
