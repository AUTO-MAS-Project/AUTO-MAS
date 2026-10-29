"""安装阶段在首个账号配置注入前中断，也能恢复临时配置并保护用户修改。"""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MAA import manager
from app.task.MAA.base_preset import get_maa_base_preset
from app.task.MAA.tools import UpdateMAA as installer
from app.task.MAA.tools.update_config import restore_maa_update_config
from app.utils import io as io_utils

_wait_for_updater = installer._wait_for_updater


class SimulatedCrash(BaseException):
    """模拟安装配置已提交，但进程尚未进入安装收尾时被强制终止。"""


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "maa"
    config = root / "config"
    config.mkdir(parents=True)
    package = root / "pending.zip"
    package.touch()
    (root / "MAA.exe").touch()
    original = get_maa_base_preset()
    original.setdefault("Update", {}).update(
        Name="v6.1.0",
        UpdatePackage=str(package),
        CheckOnStartup=True,
        CheckOnSchedule=True,
        AutoDownloadUpdatePackage=True,
        AutoInstallUpdatePackage=False,
        UpdateSource="MirrorChyan",
    )
    original.setdefault("Timers", {})["List"] = [{"IsEnabled": True}]
    io_utils.write_file(config / "gui.new.json", original)
    snapshot = tmp_path / "Temp"
    io_utils.commit_native_config_snapshot(snapshot, config, script_id="test-script")
    monkeypatch.setattr(installer.System, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(installer.ProcessRunner, "run_process", AsyncMock())
    monkeypatch.setattr(installer, "_wait_for_updater", AsyncMock())
    scheduler = object.__new__(manager.MaaManager)
    scheduler.maa_set_path = config
    scheduler.temp_path = snapshot
    scheduler.script_info = SimpleNamespace(script_id="test-script")
    return root, snapshot, original, scheduler


@pytest.mark.asyncio
@pytest.mark.parametrize("manual_edit", [False, True])
async def test_installation_crash_before_account_injection_restores_owned_fields(
    installation, monkeypatch, manual_edit
):
    root, snapshot, original, scheduler = installation
    write = installer.write_maa_update_config

    def write_then_crash(*args, **kwargs):
        write(*args, **kwargs)
        raise SimulatedCrash()

    monkeypatch.setattr(installer, "write_maa_update_config", write_then_crash)
    with pytest.raises(SimulatedCrash):
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    current = io_utils.read_file(root / "config/gui.new.json")
    assert current["Update"]["UpdateSource"] == "GitHub"
    installer.ProcessRunner.run_process.assert_not_awaited()
    expected = deepcopy(original)
    if manual_edit:
        current["Update"]["UpdateSource"] = "Manual"
        current["Gui"]["UserTheme"] = "dark"
        expected["Update"]["UpdateSource"] = "Manual"
        expected["Gui"]["UserTheme"] = "dark"
        io_utils.write_file(root / "config/gui.new.json", current)
    # 与下轮 prepare 相同：已确认更新器退出，再执行原生配置恢复。
    scheduler._recover_previous_run()
    assert io_utils.read_file(root / "config/gui.new.json") == expected
    assert not snapshot.with_name("Temp.maa-update.json").exists()
    assert not snapshot.exists()


@pytest.mark.asyncio
async def test_crash_between_journal_commit_and_config_write_is_idempotent(
    installation, monkeypatch
):
    root, snapshot, original, scheduler = installation
    write = io_utils.write_file

    def fail_live_write(path, data, **kwargs):
        if path == root / "config/gui.new.json":
            raise SimulatedCrash()
        return write(path, data, **kwargs)

    monkeypatch.setattr(io_utils, "write_file", fail_live_write)
    with pytest.raises(SimulatedCrash):
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    monkeypatch.setattr(io_utils, "write_file", write)
    scheduler._recover_previous_run()
    assert io_utils.read_file(root / "config/gui.new.json") == original
    restore_maa_update_config(root, snapshot_path=snapshot, script_id="test-script")
    assert io_utils.read_file(root / "config/gui.new.json") == original


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_installation_restores_overrides_after_updater_exit(
    installation, cancelled
):
    root, snapshot, original, _ = installation
    path = root / "config/gui.new.json"

    async def run(*args, **kwargs):
        current = io_utils.read_file(path)
        assert current["Update"]["CheckOnStartup"] is False
        assert current["Timers"]["List"][0]["IsEnabled"] is False
        # 官方写回自己的版本字段，不应被临时配置恢复抹掉。
        current["Update"]["Name"] = "installed-version"
        current["Update"]["UpdatePackage"] = ""
        io_utils.write_file(path, current)
        if cancelled:
            raise asyncio.CancelledError()

    installer.ProcessRunner.run_process.side_effect = run
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await installer.update_maa(
                root, snapshot_path=snapshot, script_id="test-script"
            )
    else:
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    expected = deepcopy(original)
    expected["Update"]["Name"] = "installed-version"
    expected["Update"]["UpdatePackage"] = ""
    assert io_utils.read_file(path) == expected
    installer._wait_for_updater.assert_awaited_once()
    assert not snapshot.with_name("Temp.maa-update.json").exists()


@pytest.mark.asyncio
async def test_running_updater_preserves_journal_until_next_recovery(installation):
    root, snapshot, original, scheduler = installation
    installer._wait_for_updater.side_effect = installer.MaaUpdaterRunningError(
        "still running"
    )
    with pytest.raises(installer.MaaUpdaterRunningError):
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    assert (
        io_utils.read_file(root / "config/gui.new.json")["Update"]["UpdateSource"]
        == "GitHub"
    )
    assert snapshot.with_name("Temp.maa-update.json").exists()
    # 当前轮禁止恢复；模拟更新器后来退出，下一轮沿恢复协议还原。
    scheduler._recover_previous_run()
    assert io_utils.read_file(root / "config/gui.new.json") == original


@pytest.mark.asyncio
async def test_restore_write_failure_keeps_journal_for_retry(installation, monkeypatch):
    root, snapshot, original, _ = installation
    injected = deepcopy(original)
    injected["Update"]["UpdateSource"] = "GitHub"
    installer.write_maa_update_config(
        root, injected, snapshot_path=snapshot, script_id="test-script"
    )
    write = io_utils.write_file

    def fail_write(*args, **kwargs):
        raise OSError("injected restore failure")

    monkeypatch.setattr(io_utils, "write_file", fail_write)
    with pytest.raises(OSError):
        restore_maa_update_config(root, snapshot_path=snapshot, script_id="test-script")
    assert snapshot.with_name("Temp.maa-update.json").exists()
    assert io_utils.read_file(root / "config/gui.new.json") == injected
    monkeypatch.setattr(io_utils, "write_file", write)
    restore_maa_update_config(root, snapshot_path=snapshot, script_id="test-script")
    assert io_utils.read_file(root / "config/gui.new.json") == original
    assert not snapshot.with_name("Temp.maa-update.json").exists()


@pytest.mark.asyncio
async def test_unknown_updater_process_state_does_not_restore_config(
    installation, monkeypatch
):
    root, snapshot, _, _ = installation
    monkeypatch.setattr(installer, "_wait_for_updater", _wait_for_updater)
    monkeypatch.setattr(
        installer.System,
        "is_process_running",
        AsyncMock(side_effect=OSError("process query failed")),
    )
    with pytest.raises(installer.MaaUpdaterRunningError):
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    assert snapshot.with_name("Temp.maa-update.json").exists()
    assert (
        io_utils.read_file(root / "config/gui.new.json")["Update"]["UpdateSource"]
        == "GitHub"
    )
