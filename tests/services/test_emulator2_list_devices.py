"""Emulator 2.0 设备表的组装逻辑：每条安装只问一次状态，设置按需读。"""

import json
import unittest
from unittest.mock import patch

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.utils.emulator2 import service
from app.utils.emulator2.facade import Emulator2Manager
from app.utils.emulator2.settings import build_settings

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
    {"slot": "1", "pathId": "ld", "nativeIndex": "1", "state": "active"},
    {"slot": "2", "pathId": "mumu", "nativeIndex": "0", "state": "active"},
    {"slot": "3", "pathId": "mumu", "nativeIndex": "2", "state": "tombstone"},
]


class FakeBackend:
    """记录每个方法被调了几次的假后端。"""

    def __init__(self, info: dict[str, DeviceInfo], *, fail_info: bool = False):
        self.info = info
        self.fail_info = fail_info
        self.calls: dict[str, int] = {"getInfo": 0, "overview": 0, "list": 0}

    async def getInfo(self, idx):
        self.calls["getInfo"] += 1
        if self.fail_info:
            raise RuntimeError("list2 失败")
        return dict(self.info)

    async def list_devices(self):
        self.calls["list"] += 1
        return {index: item.title for index, item in self.info.items()}

    async def read_instance_overview(self, idx):
        self.calls["overview"] += 1
        # 雷电实例配置是平铺键，不是嵌套对象
        settings = build_settings(
            {"advancedSettings.cpuCount": 6, "basicSettings.fps": 60}, None
        )
        return settings, True, []


async def _make_manager(backends: dict[str, FakeBackend]) -> Emulator2Manager:
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

    async def manager_for(path):
        return backends[path.path_id]

    manager.manager_for = manager_for  # type: ignore[method-assign]
    return manager


def _info(status: DeviceStatus, title: str, adb: str) -> DeviceInfo:
    return DeviceInfo(title=title, status=status, adb_address=adb)


class ListDevicesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.ld = FakeBackend(
            {
                "0": _info(DeviceStatus.ONLINE, "0", "emulator-5554"),
                "1": _info(DeviceStatus.OFFLINE, "1", "emulator-5556"),
            }
        )
        self.mumu = FakeBackend(
            {
                "0": _info(DeviceStatus.OFFLINE, "MuMu安卓设备", "127.0.0.1:5555"),
                "2": _info(DeviceStatus.OFFLINE, "MuMu安卓设备-2", "127.0.0.1:5559"),
            }
        )
        self.backends = {"ld": self.ld, "mumu": self.mumu}

    async def _list(self, **kwargs) -> dict:
        manager = await _make_manager(self.backends)
        with (
            patch.object(service, "build_manager", return_value=manager),
            patch.object(service, "_save") as save,
        ):
            result = await service.list_devices("emu", **kwargs)
        self.saved = save.called
        return result

    async def test_each_install_is_queried_once_and_settings_come_along(self) -> None:
        result = await self._list()

        self.assertEqual(self.ld.calls["getInfo"], 1)
        self.assertEqual(self.mumu.calls["getInfo"], 1)
        # 三台活跃设备各读一次设置，墓碑那台不读
        self.assertEqual(self.ld.calls["overview"], 2)
        self.assertEqual(self.mumu.calls["overview"], 1)

        rows = {row["slot"]: row for row in result["devices"]}
        self.assertEqual(sorted(rows), ["0", "1", "2"])
        self.assertEqual(rows["0"]["status"], int(DeviceStatus.ONLINE))
        self.assertEqual(rows["0"]["adbAddress"], "emulator-5554")
        self.assertEqual(rows["0"]["settings"]["cpu"]["value"], 6)
        self.assertTrue(rows["0"]["stableMode"])
        self.assertEqual(rows["2"]["title"], "MuMu安卓设备")

    async def test_status_only_skips_settings(self) -> None:
        result = await self._list(with_settings=False)

        self.assertEqual(self.ld.calls["overview"], 0)
        self.assertEqual(self.mumu.calls["overview"], 0)
        for row in result["devices"]:
            self.assertEqual(row["settings"], {})
            self.assertEqual(row["availability"], "ok")
        self.assertEqual(len(result["devices"]), 3)

    async def test_failed_install_is_unavailable_but_others_still_listed(self) -> None:
        self.ld.fail_info = True

        result = await self._list()

        rows = {row["slot"]: row for row in result["devices"]}
        self.assertEqual(rows["0"]["availability"], "unavailable")
        self.assertEqual(rows["1"]["availability"], "unavailable")
        self.assertEqual(rows["2"]["availability"], "ok")
        # 查不成的那条安装不读设置，也不因此写槽位表
        self.assertEqual(self.ld.calls["overview"], 0)
        self.assertFalse(self.saved)

    async def test_new_native_instance_gets_a_slot_and_is_persisted(self) -> None:
        self.mumu.info["5"] = _info(DeviceStatus.OFFLINE, "新实例", "127.0.0.1:5565")

        result = await self._list(with_settings=False)

        rows = {row["slot"]: row for row in result["devices"]}
        # 墓碑占了 3 号，新实例拿到 4 号
        self.assertEqual(rows["4"]["nativeIndex"], "5")
        self.assertEqual(rows["4"]["title"], "新实例")
        self.assertTrue(self.saved)

    async def test_instance_missing_from_enumeration_is_not_listed(self) -> None:
        del self.ld.info["1"]

        result = await self._list(with_settings=False)

        self.assertEqual(sorted(row["slot"] for row in result["devices"]), ["0", "2"])


class ListDevicesForComboboxTest(unittest.IsolatedAsyncioTestCase):
    async def test_labels_carry_the_slot_and_use_the_light_listing(self) -> None:
        ld = FakeBackend({"0": _info(DeviceStatus.OFFLINE, "0", "")})
        mumu = FakeBackend({"0": _info(DeviceStatus.OFFLINE, "MuMu安卓设备", "")})
        manager = await _make_manager({"ld": ld, "mumu": mumu})

        devices = await manager.list_devices()

        self.assertEqual(devices, {"0": "#0 0", "2": "#2 MuMu安卓设备"})
        # 下拉框只要名字：走 list_devices 一条命令，不走带 adb 核对的 getInfo
        self.assertEqual(ld.calls, {"getInfo": 0, "overview": 0, "list": 1})
        self.assertEqual(mumu.calls, {"getInfo": 0, "overview": 0, "list": 1})
