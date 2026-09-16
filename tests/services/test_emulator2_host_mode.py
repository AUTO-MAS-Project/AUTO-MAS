import json
import unittest
from pathlib import Path
from unittest import mock

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.utils.emulator2 import facade
from app.utils.emulator2.facade import Emulator2Manager

_PATHS = [
    {
        "pathId": "ld",
        "installPath": "D:/leidian/LDPlayer14",
        "alias": "LDPlayer14",
        "type": "ldplayer",
        "version": "14.0.25.1",
    },
    {
        "pathId": "mumu",
        "installPath": "C:/Program Files/Netease/MuMu/nx_main",
        "alias": "nx_main",
        "type": "mumu",
        "version": "6.6.4.0",
    },
]

_SLOTS = [
    {"slot": "0", "pathId": "ld", "nativeIndex": "0", "state": "active"},
    {"slot": "2", "pathId": "mumu", "nativeIndex": "0", "state": "active"},
]


class FakeBackend:
    def __init__(self) -> None:
        self.opened: list[str] = []

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        self.opened.append(idx)
        return DeviceInfo(title=idx, status=DeviceStatus.ONLINE, adb_address="")

    async def apply_stable_mode(self, idx: str) -> list[str]:  # pragma: no cover
        return []


async def _make_manager() -> tuple[Emulator2Manager, FakeBackend]:
    config = EmulatorConfig()
    await config.load(
        {
            "Info": {
                "Type": "emulator2",
                "Paths": json.dumps(_PATHS),
                "Slots": json.dumps(_SLOTS),
            }
        }
    )
    manager = Emulator2Manager(config)
    backend = FakeBackend()

    async def manager_for(path):
        return backend

    manager.manager_for = manager_for  # type: ignore[method-assign]
    manager._manager_exe = lambda path: Path(path.install_path) / "x.exe"  # type: ignore[method-assign]
    return manager, backend


class HostModeOnOpenTest(unittest.IsolatedAsyncioTestCase):
    """起任一台设备前，配置下每条安装的宿主层都对齐一次；某条失败不拦启动。"""

    async def test_every_install_is_handled_before_the_launch(self) -> None:
        manager, backend = await _make_manager()
        calls: list[tuple[str, Path | None, bool]] = []

        def fake_apply(emulator_type, manager_exe, enabled):
            calls.append((emulator_type, manager_exe, enabled))
            self.assertEqual(backend.opened, [])  # 宿主层先于后端 open
            return emulator_type == "mumu"

        with (
            mock.patch.object(facade, "apply_host_mode", side_effect=fake_apply),
            mock.patch.object(facade, "is_master_mode_enabled", return_value=True),
        ):
            await manager.open("0")

        self.assertEqual(
            calls,
            [
                ("ldplayer", Path("D:/leidian/LDPlayer14/x.exe"), True),
                ("mumu", Path("C:/Program Files/Netease/MuMu/nx_main/x.exe"), True),
            ],
        )
        self.assertEqual(backend.opened, ["0"])

    async def test_failure_on_one_install_does_not_block_the_others(self) -> None:
        manager, backend = await _make_manager()
        seen: list[str] = []

        def fake_apply(emulator_type, manager_exe, enabled):
            seen.append(emulator_type)
            if emulator_type == "ldplayer":
                raise OSError("locked")
            return False

        with (
            mock.patch.object(facade, "apply_host_mode", side_effect=fake_apply),
            mock.patch.object(facade, "is_master_mode_enabled", return_value=False),
        ):
            await manager.open("2")

        self.assertEqual(seen, ["ldplayer", "mumu"])
        self.assertEqual(backend.opened, ["0"])
