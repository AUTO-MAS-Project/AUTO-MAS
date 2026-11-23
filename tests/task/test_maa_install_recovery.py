"""MAA 官方本体失败与资源半更新：统一自动恢复且保持 fail-closed。"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import ConfigCollection, config_manager
from app.models.config import EmulatorConfig, MaaConfig
from app.models.task import TaskItem, TaskMode
from app.services import script_install
from app.task.history_core import TaskHistorySession
from app.task.MAA import manager
from app.task.MAA.registration import build_config_handler
from app.task.MAA.tools import install_recovery as recovery
from app.task.MAA.tools.update_config import write_maa_update_config
from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError
from app.utils import ProcessManager
from app.utils import io as io_utils
from tests.config_support import activate_config
from tests.task_stop_support import add_script


@pytest.fixture
def maa_root(tmp_path, monkeypatch):
    root = tmp_path / "maa"
    (root / "config").mkdir(parents=True)
    # 真实 PE 头：MZ -> e_lfanew=64 -> PE\0\0 + Machine=x64。
    executable = bytearray(128)
    executable[:2] = b"MZ"
    executable[60:64] = (64).to_bytes(4, "little")
    executable[64:70] = b"PE\x00\x00\x64\x86"
    (root / "MAA.exe").write_bytes(executable)
    (root / "MAA.dll").touch()
    monkeypatch.setattr(
        recovery,
        "read_installed_release",
        lambda root: ("v6.2.0", "x64"),
    )
    monkeypatch.setattr(
        recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(recovery, "read_pending_update", lambda root: ("", ""))
    monkeypatch.setattr(
        recovery.process, "is_process_running", AsyncMock(return_value=False)
    )
    return root


@pytest.mark.asyncio
async def test_manual_repair_can_acknowledge_old_official_failure(maa_root):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official install failed")
    version = await recovery.skip_delegated_failure(
        maa_root, {"software": flag.read_bytes()}
    )
    assert version == "v6.2.0"
    assert not flag.exists()
    backup = list(script_install.workspace(maa_root).glob("maa-failure-ack-*.txt"))
    assert len(backup) == 1
    assert backup[0].read_bytes() == b"official install failed"


@pytest.mark.asyncio
async def test_resource_write_can_never_be_skipped(maa_root):
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target": "2026-11-10T01:00:00+00:00"}')
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"failure")
    with pytest.raises(MaaUpdateUnsafeError, match="只能跳过"):
        await recovery.skip_delegated_failure(
            maa_root,
            {"software": flag.read_bytes(), "resource": resource.read_bytes()},
        )
    assert resource.exists()
    assert flag.exists()


@pytest.mark.asyncio
async def test_install_corrupted_or_pending_package_never_skips(maa_root, monkeypatch):
    flag = maa_root / "pending-update-failure.txt"
    flag.touch()
    snapshot = {"software": flag.read_bytes()}
    (maa_root / "MAA.dll").unlink()
    with pytest.raises(MaaUpdateUnsafeError, match="核心程序集"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    (maa_root / "MAA.dll").touch()
    (maa_root / "pending.zip").touch()
    monkeypatch.setattr(
        recovery, "read_pending_update", lambda root: ("v6.3.0", "pending.zip")
    )
    with pytest.raises(MaaUpdateUnsafeError, match="待安装"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    assert flag.exists()


@pytest.mark.asyncio
async def test_updater_running_or_marker_changed_never_skips(maa_root):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"old")
    snapshot = {"software": flag.read_bytes()}
    flag.write_bytes(b"new")
    with pytest.raises(MaaUpdateUnsafeError, match="变化"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    assert flag.read_bytes() == b"new"
    recovery.process.is_process_running.return_value = True
    with pytest.raises(MaaUpdateUnsafeError, match="仍在写盘"):
        await recovery.skip_delegated_failure(maa_root, {"software": flag.read_bytes()})
    assert flag.exists()


@pytest.mark.asyncio
async def test_maa_managed_recovery_does_not_depend_on_frontend(maa_root, monkeypatch):
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"native installer failed")
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    state = await adapter.inspect()
    assert state.pending
    assert not state.updated_confirmed
    assert flag.exists()


@pytest.mark.asyncio
async def test_maa_manager_resource_recovery_goes_through_common_entry(
    maa_root, monkeypatch
):
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target":"2026-10-01T00:00:00+00:00"}')
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(
        name="MAA", script_id="test-script", set_log=AsyncMock()
    )
    instance.task_info = SimpleNamespace(task_id="task")
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=False, MirrorChyanCDK="")
    )
    instance._maa_update_checked = False
    common = AsyncMock(return_value="reinstalled")
    monkeypatch.setattr(manager, "auto_recover_script_install", common)
    await instance._recover_unconfirmed_update()
    common.assert_awaited_once()
    assert instance._maa_update_checked
    instance.script_info.set_log.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pending",
    [
        "resource-recovery",
        "registered-package",
        "snapshot",
        "journal",
        "relocated",
        "relocated-late",
    ],
)
async def test_view_with_pending_update_keeps_installation_intact(
    maa_root, monkeypatch, pending
):
    workspace = maa_root.parent / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    config_file = maa_root / "config/gui.new.json"
    record = manager.round_resource_record(maa_root)
    package = maa_root / "MirrorChyanAppv6.3.0.zip"
    update = {"UpdatePackage": ""}
    original_update = {"Name": "v6.3.0", "UpdatePackage": package.name}
    if pending == "resource-recovery":
        io_utils.write_file(record, {"target": "2026-10-02T00:00:00+00:00"})
    else:
        package.write_bytes(b"downloaded package")
        if pending == "registered-package":
            update.update(original_update)
    io_utils.write_file(config_file, {"Update": update})
    original_record = record.read_bytes() if record.is_file() else None
    original_config = config_file.read_bytes()
    resource_clock = datetime(2026, 10, 1, tzinfo=timezone.utc)

    emulators = ConfigCollection.build([EmulatorConfig])
    await emulators.activate()
    emulator_id = emulators.add(EmulatorConfig)
    await emulators.commit()
    monkeypatch.setitem(config_manager._collections, "EmulatorConfig", emulators)
    config = await activate_config(
        MaaConfig(
            Emulator={"Id": emulator_id, "Index": "0"},
            Update={"TakeoverEnabled": True},
        )
    )
    config.Info.Path = maa_root
    await config.commit()
    root = TaskItem(info={"mode": TaskMode.SCRIPT_VIEW})
    script = await add_script(root, str(config.uid))
    instance = manager.MaaManager(script, device_provider=AsyncMock())
    instance.history = TaskHistorySession(root)
    snapshot = workspace / f"data/{script.script_id}/Temp"
    if pending in ("snapshot", "journal"):
        io_utils.write_file(config_file, {"Update": original_update})
        if pending == "snapshot":
            io_utils.commit_native_config_snapshot(
                snapshot, config_file.parent, script_id=script.script_id
            )
            io_utils.write_file(config_file, {"Update": update})
            io_utils.mark_native_config_injected(
                snapshot, config_file.parent, script_id=script.script_id
            )
        else:
            write_maa_update_config(
                maa_root,
                {"Update": update},
                snapshot_path=snapshot,
                script_id=script.script_id,
            )
    monkeypatch.setattr(manager.Config, "ScriptConfig", {config.uid: config})
    access = AsyncMock(return_value=None)
    kill = AsyncMock(return_value=True)
    if pending in ("relocated", "relocated-late"):
        destination = maa_root.with_name("another-maa")
        name = "gui.new.json" if pending == "relocated-late" else "gui.new.json.bak"
        destination_config = destination / "config" / name
        io_utils.write_file(
            destination_config, {"Update": original_update}, format=".json"
        )
        (destination / "MAA.exe").touch()
        (destination / package.name).write_bytes(package.read_bytes())
        monkeypatch.setitem(
            manager.Config._script_config_handlers, MaaConfig, build_config_handler()
        )

        async def change_install_while_waiting(install, **_):
            if install == maa_root:
                refusal = await manager.Config.update_script_settings(
                    script.script_id, {"Info": {"Path": str(destination)}}
                )
                assert refusal is None

        if pending == "relocated":
            access.side_effect = change_install_while_waiting
        else:

            async def relocate_during_stop(exe):
                await change_install_while_waiting(exe.parent)
                return True

            kill.side_effect = relocate_during_stop
    monkeypatch.setattr(manager, "acquire_resource_access_lock", access)
    monkeypatch.setattr(
        manager.process, "is_process_stopped", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(manager.process, "kill_process", kill)
    monkeypatch.setattr(manager, "read_resource_clock", lambda root: resource_clock)

    launch = AsyncMock(side_effect=AssertionError("backup view started MAA"))
    monkeypatch.setattr(ProcessManager, "open_process", launch)
    repair = AsyncMock(
        side_effect=AssertionError("backup view attempted resource repair")
    )
    monkeypatch.setattr(manager, "auto_recover_script_install", repair)

    try:
        with pytest.raises(MaaUpdateUnsafeError, match="查看"):
            await instance.main_task()
        repair.assert_not_awaited()
        launch.assert_not_awaited()
        assert config_file.read_bytes() == original_config
        assert not (maa_root / ".automas-resource-update.json").exists()
        if pending in ("resource-recovery", "snapshot", "journal"):
            kill.assert_not_awaited()
        if pending in ("relocated", "relocated-late"):
            assert config.Info.Path == destination
            assert io_utils.read_dict_file(destination_config, format=".json") == {
                "Update": original_update
            }
            assert (destination / package.name).is_file()
            if pending == "relocated":
                assert not destination_config.with_suffix("").exists()
        if pending == "resource-recovery":
            assert record.read_bytes() == original_record
        else:
            assert package.read_bytes() == b"downloaded package"
        if pending == "snapshot":
            assert snapshot.is_dir()
        if pending == "journal":
            assert snapshot.with_name("Temp.maa-update.json").is_file()
    finally:
        await instance._finalize_task()
        await instance.history.close()


@pytest.mark.asyncio
async def test_mid_round_resource_recovery_preserves_first_software_check(
    maa_root, monkeypatch
):
    monkeypatch.chdir(maa_root.parent)
    clock = datetime(2026, 10, 1, tzinfo=timezone.utc)
    record = manager.round_resource_record(maa_root)
    io_utils.write_file(record, {"target": clock.isoformat()})
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target":"2026-10-01T00:00:00+00:00"}')
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(script_id="test-script", set_log=AsyncMock())
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=True)
    )
    instance._maa_update_checked = False
    instance._updater_running = False
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.1.0", "x64")
    )
    monkeypatch.setattr(manager, "read_resource_clock", lambda root: clock)

    async def repair(*args, **kwargs):
        resource.unlink()
        return "reinstalled"

    monkeypatch.setattr(manager, "auto_recover_script_install", repair)
    await instance._recover_unconfirmed_update()
    assert not record.exists()
    prepare = AsyncMock()
    monkeypatch.setattr(instance, "_prepare_software_update", prepare)
    await instance._prepare_software_update_once(
        SimpleNamespace(update_config_dir=instance.maa_set_path)
    )
    prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_maa_corrupted_executable_blocks_manual_acknowledge(
    maa_root, monkeypatch
):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official error")
    (maa_root / "MAA.exe").write_bytes(b"")
    with pytest.raises(MaaUpdateUnsafeError, match="PE 架构"):
        await recovery.skip_delegated_failure(maa_root, {"software": flag.read_bytes()})
    assert flag.read_bytes() == b"official error"


@pytest.mark.asyncio
async def test_maa_missing_executable_never_becomes_healthy(maa_root, monkeypatch):
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official error")
    (maa_root / "MAA.exe").unlink()
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    state = await adapter.inspect()
    assert state.pending and not state.healthy
    assert flag.exists()


@pytest.mark.asyncio
async def test_native_failure_marker_with_package_does_not_fake_automatic_retry(
    maa_root, monkeypatch
):
    """真实公共入口必须在原生启动前阻断无效重试，保留原始失败现场。"""
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official updater failed")
    package = maa_root / "pending.zip"
    package.write_bytes(b"official archive")
    monkeypatch.setattr(
        managed_recovery, "read_pending_update", lambda root: ("v6.3.0", "pending.zip")
    )
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(script_id="test-script", set_log=AsyncMock())
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(MirrorChyanCDK="", TakeoverEnabled=True)
    )
    instance._maa_update_checked = False
    native = AsyncMock()
    monkeypatch.setattr(instance, "_install_pending_software_update", native)
    with pytest.raises(MaaUpdateUnsafeError, match="官方界面"):
        await instance._recover_unconfirmed_update()
    native.assert_not_awaited()
    assert flag.read_bytes() == b"official updater failed"
    assert package.read_bytes() == b"official archive"
    assert not instance._maa_update_checked


@pytest.mark.asyncio
async def test_resource_failure_without_official_marker_keeps_automatic_repair(
    maa_root, monkeypatch
):
    from app.task.MAA.tools import managed_recovery

    resource = maa_root / ".automas-resource-update.json"
    resource.write_bytes(b'{"target": "2026-11-10T00:00:00+00:00"}')
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    called = AsyncMock()

    async def prepared():
        resource.unlink()

    called.side_effect = prepared
    monkeypatch.setattr(
        managed_recovery,
        "verify_resource_recovery_marker",
        lambda root, snapshot: None,
    )
    monkeypatch.setattr(
        managed_recovery,
        "has_incomplete_resource_update",
        lambda root: resource.exists(),
    )
    await adapter.reinstall(called)
    called.assert_awaited_once()
    assert not resource.exists()
