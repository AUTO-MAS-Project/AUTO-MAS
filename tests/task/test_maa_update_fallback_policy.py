"""普通更新失败后继续任务，托管期间仍暂停 MAA 原生更新。"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.task.MAA import manager
from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError


@pytest.fixture
def managed_run(tmp_path, monkeypatch):
    (tmp_path / "MAA.exe").touch()
    (tmp_path / "config").mkdir()
    instance = object.__new__(manager.MaaManager)
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=True)
    )
    instance.script_info = SimpleNamespace(log="", script_id="script-test")
    instance.task_info = SimpleNamespace(task_id="test-task")
    instance.maa_set_path = tmp_path / "config"
    instance.temp_path = tmp_path / "snapshot"
    instance._updater_running = False
    monkeypatch.setattr(instance, "_remember_pending_update", Mock())
    monkeypatch.setattr(
        instance, "_prepare_software_update_strict", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        manager.System, "is_process_running", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    monkeypatch.setattr(
        manager,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    monkeypatch.setattr(manager, "update_maa", AsyncMock())
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RuntimeError("CDK unavailable"), TimeoutError(), OSError(), ValueError()],
)
async def test_recoverable_failure_continues_with_pending_package_preserved(
    managed_run, error
):
    managed_run._prepare_software_update_strict.side_effect = error
    assert await managed_run._prepare_software_update(object()) is False
    managed_run._remember_pending_update.assert_called_once_with()
    assert managed_run.script_config.Update.TakeoverEnabled is True
    assert managed_run.script_info.log
    manager.Publisher.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_takeover_off_does_not_attempt_updates(managed_run):
    managed_run.script_config.Update.TakeoverEnabled = False
    assert await managed_run._prepare_software_update(object()) is False
    managed_run._prepare_software_update_strict.assert_not_awaited()
    managed_run._remember_pending_update.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_update_still_reports_success(managed_run):
    assert await managed_run._prepare_software_update(object()) is True
    managed_run._remember_pending_update.assert_not_called()
    manager.Publisher.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        manager.MaaUpdaterRunningError("still running"),
        MaaUpdateUnsafeError("partial install"),
        manager._utils_fluxdown_cli.FluxdownCancelUnconfirmed("unknown writer"),
    ],
)
async def test_cancellation_and_unsafe_updates_are_not_swallowed(managed_run, error):
    managed_run._prepare_software_update_strict.side_effect = error
    with pytest.raises(type(error)) as raised:
        await managed_run._prepare_software_update(object())
    assert raised.value is error
    managed_run._remember_pending_update.assert_not_called()
    manager.Publisher.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["exe", "release", "version", "clock", "failure"])
async def test_fallback_requires_an_identifiable_installation(
    managed_run, monkeypatch, missing
):
    managed_run._prepare_software_update_strict.side_effect = TimeoutError()
    if missing == "exe":
        (managed_run.maa_set_path.parent / "MAA.exe").unlink()
    elif missing in ("release", "version"):
        monkeypatch.setattr(
            manager,
            "read_installed_release",
            lambda root: None if missing == "release" else ("invalid", "x64"),
        )
    elif missing == "clock":
        monkeypatch.setattr(manager, "read_resource_clock", lambda root: None)
    else:
        monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: True)
    with pytest.raises(MaaUpdateUnsafeError):
        await managed_run._prepare_software_update(object())
    managed_run._remember_pending_update.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_never_starts_while_official_updater_is_running(managed_run):
    managed_run._prepare_software_update_strict.side_effect = TimeoutError()
    manager.System.is_process_running.return_value = True
    with pytest.raises(manager.MaaUpdaterRunningError):
        await managed_run._prepare_software_update(object())
    assert managed_run._updater_running is True


@pytest.mark.asyncio
async def test_notice_failure_does_not_block_safe_fallback(managed_run):
    managed_run._prepare_software_update_strict.side_effect = TimeoutError()
    manager.Publisher.send.side_effect = RuntimeError("websocket unavailable")
    assert await managed_run._prepare_software_update(object()) is False
    managed_run._remember_pending_update.assert_called_once_with()


@pytest.mark.asyncio
async def test_official_install_exception_is_marked_unsafe(managed_run):
    error = OSError("failed to replace a DLL")
    manager.update_maa.side_effect = error
    with pytest.raises(MaaUpdateUnsafeError) as raised:
        await managed_run._install_pending_software_update(target="v6.1.0")
    assert raised.value.__cause__ is error


@pytest.mark.asyncio
async def test_unconfirmed_installation_remains_unsafe(managed_run):
    with pytest.raises(MaaUpdateUnsafeError):
        await managed_run._install_pending_software_update(target="v6.1.0")


@pytest.mark.asyncio
async def test_official_failure_marker_remains_unsafe(managed_run, monkeypatch):
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: True)
    with pytest.raises(MaaUpdateUnsafeError):
        await managed_run._install_pending_software_update()


@pytest.mark.asyncio
async def test_official_update_cancellation_propagates(managed_run):
    manager.update_maa.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await managed_run._install_pending_software_update()


@pytest.mark.asyncio
async def test_completed_official_installation_is_accepted(managed_run):
    await managed_run._install_pending_software_update(target="v6.0.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", ["normal", "crash"])
async def test_failed_update_injects_runtime_config_and_restores_pending_package(
    managed_run, monkeypatch, tmp_path, recovery
):
    import json
    import shutil

    from app.task.MAA import AutoProxy as auto_proxy
    from app.task.MAA.base_preset import get_maa_base_preset
    from app.task.MAA.tools.software_package import (
        load_deferred_update,
        read_pending_update,
        write_pending_update,
    )
    from app.utils import io as io_utils

    monkeypatch.chdir(tmp_path)
    scheduler = managed_run
    root = scheduler.maa_set_path.parent
    original = get_maa_base_preset()
    original.setdefault("Update", {}).update(
        CheckOnStartup=True,
        CheckOnSchedule=True,
        AutoDownloadUpdatePackage=True,
        AutoInstallUpdatePackage=True,
        UpdateSource="MirrorChyan",
    )
    io_utils.write_file(root / "config/gui.new.json", original)
    package = root / "pending.zip"
    package.write_bytes(b"opaque pending package")
    write_pending_update(root, version="v6.1.0", package=str(package))
    original = io_utils.read_file(root / "config/gui.new.json")
    snapshot = tmp_path / "data/script-test/Temp"
    shutil.copytree(scheduler.maa_set_path, snapshot)
    io_utils.write_native_config_snapshot(
        snapshot,
        script_id="script-test",
        original_exists=True,
        baseline=io_utils.dir_fingerprint(snapshot),
    )

    task = object.__new__(auto_proxy.AutoProxyTask)
    task.script_config = scheduler.script_config
    task.script_config.Run = SimpleNamespace(TaskTransitionMethod="ExitEmulator")
    task.script_config.Emulator = SimpleNamespace(Index="")
    task.script_info = SimpleNamespace(script_id="script-test")
    task.cur_user_config = SimpleNamespace(
        Info=SimpleNamespace(Server="Official", Id="", IfQuickConfig=False)
    )
    task.config_base = auto_proxy.CONFIG_BASE_NATIVE
    task.native_base = True
    task.mode = "Routine"
    task.maa_root_path = root
    task.maa_set_path = root / "config"
    task.maa_exe_path = root / "MAA.exe"
    task.maa_tasks_path = root / "tasks"
    task.pending_update = None
    task.maa_process_manager = SimpleNamespace(kill=AsyncMock())
    adb = root / "adb.exe"
    adb.touch()
    task.emulator_manager = SimpleNamespace(get_adb_path=lambda: adb)
    monkeypatch.setattr(task, "_resolve_avd_device", lambda: None)
    monkeypatch.setattr(auto_proxy, "resolve_device_ref", lambda *args: None)
    monkeypatch.setattr(auto_proxy.System, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(auto_proxy, "agree_bilibili", AsyncMock())
    monkeypatch.setattr(
        auto_proxy.Config,
        "setting",
        SimpleNamespace(Function=SimpleNamespace(IfSilence=False)),
    )
    scheduler._active_proxy_task = task
    scheduler._pending_update = None
    monkeypatch.setattr(
        scheduler,
        "_remember_pending_update",
        manager.MaaManager._remember_pending_update.__get__(scheduler),
    )
    scheduler._prepare_software_update_strict.side_effect = TimeoutError()

    assert await scheduler._prepare_software_update(task) is False
    assert load_deferred_update(root) == ("v6.1.0", str(package))
    await task.set_maa(SimpleNamespace(adb_address="127.0.0.1:5555"))
    runtime = io_utils.read_file(root / "config/gui.new.json")
    for key in (
        "CheckOnStartup",
        "CheckOnSchedule",
        "AutoDownloadUpdatePackage",
        "AutoInstallUpdatePackage",
    ):
        assert runtime["Update"][key] is False
    assert runtime["Update"]["UpdateSource"] == "GitHub"
    assert runtime["Update"]["UpdatePackage"] == ""
    assert package.is_file()
    assert task.pending_update == ("v6.1.0", str(package))

    if recovery == "crash":
        assert (
            io_utils.recover_native_config(
                snapshot, task.maa_set_path, expected_script_id="script-test"
            )
            == "restored"
        )
    else:
        # 使用 manager 正常收尾的原生目录恢复与待更新登记恢复入口。
        io_utils.swap_in_dir(snapshot, task.maa_set_path)
        await scheduler._restore_pending_update()
        io_utils.clear_native_config_snapshot(snapshot)
    restored = json.loads((root / "config/gui.new.json").read_text(encoding="utf-8"))
    assert restored == original
    assert read_pending_update(root) == ("v6.1.0", str(package))
