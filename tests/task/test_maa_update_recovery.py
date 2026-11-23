"""安装阶段在首个账号配置注入前中断，也能恢复临时配置并保护用户修改。"""

import asyncio
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MAA import manager
from app.task.MAA.base_preset import get_maa_base_preset
from app.task.MAA.tools import UpdateMAA as installer
from app.task.MAA.tools.software_package import (
    read_pending_update,
    round_package_ready,
    round_resource_record,
    save_deferred_update,
    write_pending_update,
)
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
    monkeypatch.setattr(installer.process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(installer.ProcessRunner, "run_process", AsyncMock())
    monkeypatch.setattr(installer, "_wait_for_updater", AsyncMock())
    scheduler = object.__new__(manager.MaaManager)
    scheduler.maa_set_path = config
    scheduler.temp_path = snapshot
    scheduler.script_info = SimpleNamespace(script_id="test-script")
    return root, snapshot, original, scheduler


def _write_full_package(path, *, machine):
    dll = bytearray(70)
    dll[:2] = b"MZ"
    dll[60:64] = (64).to_bytes(4, "little")
    dll[64:68] = b"PE\x00\x00"
    dll[68:] = machine.to_bytes(2, "little")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("MAA.exe", b"exe")
        archive.writestr("MAA.dll", dll)


@pytest.mark.asyncio
@pytest.mark.parametrize("takeover", [False, True])
async def test_round_installs_ready_package_before_return(
    installation, monkeypatch, takeover
):
    root, _, original, scheduler = installation
    original["Update"]["UpdatePackage"] = ""
    config = root / "config/gui.new.json"
    io_utils.write_file(config, original)
    package = root / "pending.zip"
    _write_full_package(package, machine=0x8664)
    version = "v6.0.0"
    scheduler.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=takeover)
    )
    scheduler.script_info.set_log = AsyncMock()
    monkeypatch.setattr(manager, "read_installed_release", lambda _: (version, "x64"))
    monkeypatch.setattr(
        manager.process, "is_process_stopped", AsyncMock(return_value=True)
    )
    clock = datetime.now(timezone.utc)
    monkeypatch.setattr(manager, "read_resource_clock", lambda _: clock)

    async def launch(exe, **kwargs):
        nonlocal version
        assert exe == root / "MAA.exe"
        assert round_resource_record(root).exists() == takeover
        update = io_utils.read_dict_file(config)["Update"]
        assert (
            update["UpdatePackage"] == package.name
            and update["AutoInstallUpdatePackage"]
        )
        version = update["Name"]

    launcher = AsyncMock(side_effect=launch)
    monkeypatch.setattr(installer.ProcessRunner, "run_process", launcher)
    scheduler._pending_update = None
    await scheduler._install_account_update()
    launcher.assert_not_awaited()
    pending = ("v6.1.0", package.name)
    scheduler._pending_update = pending
    await scheduler._install_account_update()
    assert version == pending[0] and io_utils.read_dict_file(config) == original
    assert scheduler._pending_update is None
    assert not round_resource_record(root).exists()
    await scheduler._install_account_update()
    launcher.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["wrong-baseline", "wrong-arch", "opaque-arch", "incomplete", "older"]
)
async def test_unusable_package_is_not_installed_or_registered_again(
    installation, monkeypatch, kind
):
    root, _, original, scheduler = installation
    target = "v6.0.0" if kind == "older" else "v6.2.0"
    if kind == "older":
        name = f"MAA-{target}-win-x64.zip"
        _write_full_package(root / name, machine=0x8664)
    elif kind == "wrong-baseline":
        name = f"MAAComponent-OTA-v6.0.0_{target}-win-x64.zip"
        with zipfile.ZipFile(root / name, "w") as archive:
            archive.writestr("changes.json", "{}")
    elif kind == "incomplete":
        name = f"MAA-{target}-win-x64.zip"
        (root / name).write_bytes(b"PK\x03\x04")
    else:
        name = (
            f"MirrorChyanApp{target}.zip"
            if kind == "opaque-arch"
            else f"MAA-{target}-win-arm64.zip"
        )
        _write_full_package(root / name, machine=0xAA64)
    pending = (target, name)
    monkeypatch.setattr(manager, "read_installed_release", lambda _: ("v6.1.0", "x64"))
    scheduler.script_info.set_log = AsyncMock()
    scheduler._pending_update = pending
    config = root / "config/gui.new.json"
    write_pending_update(root, version=target, package=name)
    await scheduler._install_pending_software_update(target=target)
    installer.ProcessRunner.run_process.assert_not_awaited()
    # 原生配置快照本身也可能带有登记。
    write_pending_update(root, version=target, package=name)
    save_deferred_update(root, version=pending[0], package=name)
    await scheduler._restore_pending_update()
    assert not io_utils.read_dict_file(config)["Update"]["UpdatePackage"]
    assert (root / name).is_file()


@pytest.mark.asyncio
async def test_package_without_target_does_not_block_takeover(
    installation, monkeypatch
):
    root, _, original, scheduler = installation
    scheduler.script_info.set_log = AsyncMock()
    original["Update"].pop("Name")
    io_utils.write_file(root / "config/gui.new.json", original)
    monkeypatch.setattr(manager, "read_installed_release", lambda _: ("v6.1.0", "x64"))

    await scheduler._install_pending_software_update(target="")
    assert read_pending_update(root) == ("", "")
    assert (root / "pending.zip").exists()
    installer.ProcessRunner.run_process.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", ["account", "takeover", "already-updated"])
async def test_stopped_native_download_resumes_on_next_run(
    installation, monkeypatch, resumed
):
    root, _, original, scheduler = installation
    target = "v6.2.0"
    package = root / f"MirrorChyanApp{target}.zip"
    pending = (target, package.name)
    release = ("v6.1.0", "x64")
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("changes.json", "{}")
    save_deferred_update(root, version=target, package=package.name)

    config = root / "config/gui.new.json"
    original["Update"]["UpdatePackage"] = ""
    io_utils.write_file(config, original)
    scheduler._pending_update = None
    if resumed == "already-updated":
        release = (target, "x64")
    monkeypatch.setattr(manager, "read_installed_release", lambda _: release)
    await scheduler._restore_pending_update()
    if resumed == "already-updated":
        assert read_pending_update(root) == ("", "")
        assert package.is_file()
        return

    assert read_pending_update(root) == pending
    scheduler.script_info.set_log = AsyncMock()
    scheduler.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=False)
    )
    monkeypatch.setattr(
        manager.process, "is_process_stopped", AsyncMock(return_value=True)
    )

    async def install(exe, **kwargs):
        nonlocal release
        assert read_pending_update(root) == pending
        release = (target, "x64")
        package.unlink()

    monkeypatch.setattr(installer.ProcessRunner, "run_process", install)
    if resumed == "takeover":
        await scheduler._install_pending_software_update(target=target)
    else:
        io_utils.write_file(config, original)  # 账号注入临时清空登记。
        scheduler._pending_update = pending
        await scheduler._install_account_update()
    assert release == (target, "x64")


def test_round_ota_matches_baseline_or_native_package(tmp_path):
    release, target = ("v6.0.0+build1", "x64"), "v6.2.0"
    path = tmp_path / f"MirrorChyanApp{target}.zip"
    pending = (target, path.name)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("changes.json", "{}")
    assert round_package_ready(tmp_path, pending, release)
    ota = path.rename(tmp_path / "MAAComponent-OTA-v6.0.0+build1_v6.2.0-win-x64.zip")
    assert round_package_ready(tmp_path, (target, ota.name), release)
    assert not round_package_ready(
        tmp_path, (target, ota.name), ("v6.0.0+build2", "x64")
    )
    assert not round_package_ready(tmp_path, (target, ota.name), (release[0], "arm64"))


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
@pytest.mark.parametrize("uncertain", ["query-error", "updater", "gui"])
async def test_unknown_updater_process_state_does_not_restore_config(
    installation, monkeypatch, uncertain
):
    root, snapshot, _, _ = installation
    monkeypatch.setattr(installer, "_wait_for_updater", _wait_for_updater)
    monkeypatch.setattr(installer, "_UPDATER_TIMEOUT", 0.01)
    monkeypatch.setattr(
        installer.process, "is_process_running", AsyncMock(return_value=False)
    )

    async def confirm_stopped(path):
        if uncertain == "query-error":
            raise OSError("process query failed")
        return (path.name == "MAA.exe") == (uncertain == "updater")

    monkeypatch.setattr(installer.process, "is_process_stopped", confirm_stopped)
    with pytest.raises(installer.MaaUpdaterRunningError):
        await installer.update_maa(
            root, snapshot_path=snapshot, script_id="test-script"
        )
    assert snapshot.with_name("Temp.maa-update.json").exists()
    assert (
        io_utils.read_file(root / "config/gui.new.json")["Update"]["UpdateSource"]
        == "GitHub"
    )


def test_switch_install_root_archives_previous_recovery_journal(installation, tmp_path):
    """同脚本从安装 A 切到 B：不污染 B，保留 A 的完整恢复证据。"""
    root_a, snapshot, original_a, scheduler = installation
    injected = deepcopy(original_a)
    injected["Update"]["UpdateSource"] = "GitHub"
    installer.write_maa_update_config(
        root_a, injected, snapshot_path=snapshot, script_id="test-script"
    )
    journal = snapshot.with_name("Temp.maa-update.json")
    saved = journal.read_bytes()
    assert io_utils.read_file(root_a / "config/gui.new.json") == injected

    root_b = tmp_path / "maa-other"
    config_b = root_b / "config"
    config_b.mkdir(parents=True)
    original_b = deepcopy(original_a)
    original_b["Update"]["UpdateSource"] = "UserSelected"
    io_utils.write_file(config_b / "gui.new.json", original_b)
    scheduler.maa_set_path = config_b

    # 使用生产 manager 恢复入口，而不是直接调用通用 helper。
    scheduler._recover_previous_run()
    assert io_utils.read_file(config_b / "gui.new.json") == original_b
    assert io_utils.read_file(root_a / "config/gui.new.json") == injected
    assert not journal.exists()
    archived = journal.with_name(f"{journal.name}.other-install")
    assert archived.read_bytes() == saved
    # 再次运行应幂等，不能让 A 的日志阻塞 B。
    scheduler._recover_previous_run()
    assert io_utils.read_file(config_b / "gui.new.json") == original_b
    assert archived.read_bytes() == saved
