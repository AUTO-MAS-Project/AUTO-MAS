"""ModAVD 旧根目录（没有 modavd.exe，走 Python 实现）关机的顺序与时限契约测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.emulator import DeviceStatus, EmulatorRuntimePolicy
from app.utils.common.emulator2.applaunch import AppLaunchResult
from app.utils.common.emulator2.avd import manager as manager_module
from app.utils.common.emulator2.avd.constants import CLOSE_BUDGET_SECONDS
from app.utils.common.emulator2.avd.instances import create_instance_files
from app.utils.common.emulator2.avd.manager import AvdManager

GAME = "com.example.game"


class _Qemu:
    """假 qemu 进程：安卓收到关机命令后，``exits_on_shutdown`` 为真就自己退出。"""

    def __init__(self, exits_on_shutdown: bool) -> None:
        self.exits_on_shutdown = exits_on_shutdown
        self.running = True
        self.waits: list[float] = []

    def is_running(self) -> bool:
        return self.running

    def wait(self, timeout: float) -> None:
        self.waits.append(timeout)


class _Host:
    """记下发给客体的 shell 命令（连同时限）、控制台 kill 和强杀。"""

    def __init__(self, qemu: _Qemu) -> None:
        self.qemu = qemu
        self.shell: list[tuple[str, float]] = []
        self.console: list[str] = []
        self.killed = False

    async def run_adb(
        self, root: object, *args: str, timeout: float = 0.0, **kwargs: object
    ) -> tuple[int, str]:
        del root, kwargs
        command = " ".join(args[1:]) if args[:1] == ("shell",) else " ".join(args)
        self.shell.append((command, timeout))
        if command == "svc power shutdown":
            if self.qemu.exits_on_shutdown:
                self.qemu.running = False
            # 关机途中 adbd 被结束，adb 报 255（实测约 2.4 秒后）
            return 255, ""
        return 0, ""

    async def console_command(self, port: int, command: str, timeout: float) -> str:
        del port, timeout
        self.console.append(command)
        return ""

    def kill_process_tree(self, process: _Qemu) -> None:
        self.killed = True
        process.running = False


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> _Host:
    fake = _Host(_Qemu(exits_on_shutdown=True))

    async def prepare_adb_for_close(root: object, port: int, *, timeout: float) -> None:
        del root, port, timeout

    async def ensure_app_running(run_adb: object, package: str, **kwargs: object):
        del run_adb, kwargs
        return AppLaunchResult(True, "launched", package)

    module_host = manager_module.host
    monkeypatch.setattr(module_host, "run_adb", fake.run_adb)
    monkeypatch.setattr(module_host, "console_command", fake.console_command)
    monkeypatch.setattr(module_host, "kill_process_tree", fake.kill_process_tree)
    monkeypatch.setattr(module_host, "prepare_adb_for_close", prepare_adb_for_close)
    monkeypatch.setattr(module_host, "find_qemu_process", lambda name, port: fake.qemu)
    monkeypatch.setattr(manager_module, "ensure_app_running", ensure_app_running)
    monkeypatch.setattr(manager_module, "GO_HOME_SETTLE_SECONDS", 0.0)
    return fake


def _manager(tmp_path: Path) -> AvdManager:
    create_instance_files(
        tmp_path, 7, title=None, memory_mb=4096, cpu=4, data_partition_gb=32
    )
    return AvdManager(
        tmp_path / "sdk" / "emulator" / "emulator.exe",
        60,
        False,
        runtime_policy=EmulatorRuntimePolicy(
            silence_enabled=lambda: True,
            block_ads_enabled=lambda: False,
            resource_path=Path("."),
        ),
    )


@pytest.mark.asyncio
async def test_close_after_game_goes_home_syncs_then_framework_shutdown(
    tmp_path: Path, host: _Host
) -> None:
    manager = _manager(tmp_path)
    await manager.launch_app("7", GAME)
    host.shell.clear()

    assert await manager.close("7") == DeviceStatus.OFFLINE

    # 先让游戏退到后台、sync，再走安卓框架的正常关机（不用 su、不直接写 sys.powerctl）。
    # adb 因 adbd 被结束报 255 不算失败：qemu 自己退出了，不退回控制台 kill / 强杀
    assert [command for command, _ in host.shell] == [
        "input keyevent KEYCODE_HOME",
        "sync",
        "svc power shutdown",
    ]
    assert host.console == []
    assert not host.killed


@pytest.mark.asyncio
async def test_close_waits_for_android_until_deadline_then_falls_back(
    tmp_path: Path, host: _Host
) -> None:
    host.qemu.exits_on_shutdown = False
    manager = _manager(tmp_path)

    assert await manager.close("7") == DeviceStatus.OFFLINE

    # 这次没拉起游戏，不按 HOME；安卓一直没关完才退回 sync + 控制台 kill + 强杀
    commands = [command for command, _ in host.shell]
    assert commands == ["sync", "svc power shutdown", "sync"]
    assert host.console == ["kill"]
    assert host.killed

    android_wait, console_wait, force_wait = host.qemu.waits
    fallback_sync = host.shell[2][1]
    # 宿主负载高时安卓关机实测要 14.5 秒，等它至少 20 秒
    assert android_wait >= 20
    # 调用方整体只给 30 秒，退回那几步也要做完：最坏不超过 28 秒
    # 等待值来自 time.monotonic() 的浮点差值，会带上 1e-14 级零头；预算断言留 1 微秒余量
    assert (
        android_wait + fallback_sync + console_wait + force_wait
        <= CLOSE_BUDGET_SECONDS + 1e-6
    )
