import json
import unittest
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.utils.emulator2.facade import DeviceUnavailableError, Emulator2Manager
from app.utils.emulator2.slots import PathRecord, SlotTable, make_path_id

LD_A = r"D:\leidian\LDPlayer14"
LD_B = r"E:\leidian\LDPlayer14-second"


class FakeDevice:
    """站位的 LDPlayerDevice：只需要 idx / pid / title 三个字段。"""

    def __init__(self, idx: int, pid: int, title: str) -> None:
        self.idx = idx
        self.pid = pid
        self.title = title


class FakeBackend:
    """替身后端管理器，记录收到的原生索引。"""

    def __init__(self, native_indexes: list[str], fail: bool = False) -> None:
        self.native_indexes = native_indexes
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        self.calls.append(("open", idx))
        return DeviceInfo(
            title=f"实例{idx}", status=DeviceStatus.ONLINE, adb_address=""
        )

    async def close(self, idx: str) -> DeviceStatus:
        self.calls.append(("close", idx))
        return DeviceStatus.OFFLINE

    async def getStatus(self, idx: str) -> DeviceStatus:
        self.calls.append(("getStatus", idx))
        return DeviceStatus.ONLINE

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        self.calls.append(("setVisible", idx))
        return DeviceStatus.ONLINE

    async def getInfo(self, idx):
        if self.fail:
            raise RuntimeError("枚举失败")
        rows = {
            native: DeviceInfo(
                title=f"实例{native}", status=DeviceStatus.ONLINE, adb_address=""
            )
            for native in self.native_indexes
        }
        return rows if idx is None else {idx: rows[idx]}

    async def get_device_info(self, idx):
        if self.fail:
            raise RuntimeError("枚举失败")
        rows = {
            native: FakeDevice(int(native), 1000 + int(native), f"实例{native}")
            for native in self.native_indexes
        }
        return rows if idx is None else {idx: rows[idx]}


async def build_manager(
    paths: list[PathRecord], slots: SlotTable, backends: dict[str, FakeBackend]
) -> Emulator2Manager:
    config = EmulatorConfig()
    await config.load(
        {
            "Info": {
                "Type": "emulator2",
                "Paths": json.dumps([p.to_dict() for p in paths], ensure_ascii=False),
                "Slots": slots.to_json(),
            }
        }
    )
    manager = Emulator2Manager(config)

    async def fake_manager_for(path: PathRecord):
        return backends[path.path_id]

    manager.manager_for = fake_manager_for  # type: ignore[method-assign]
    manager._manager_exe = staticmethod(  # type: ignore[method-assign]
        lambda path: Path(path.install_path) / "ldconsole.exe"
    )
    return manager


def make_path(install_path: str, alias: str) -> PathRecord:
    return PathRecord.create(install_path, alias, "ldplayer", "14.0.25.1")


class SlotTranslationTest(unittest.IsolatedAsyncioTestCase):
    """设备号 → 原生索引的翻译。两条安装的原生索引会撞号，翻译错就连到别的实例。"""

    async def asyncSetUp(self) -> None:
        self.path_a = make_path(LD_A, "主力")
        self.path_b = make_path(LD_B, "备用")
        self.slots = SlotTable()
        self.slots.sync_path(self.path_a.path_id, ["0", "1"])
        self.slots.sync_path(self.path_b.path_id, ["0", "2"])
        self.backend_a = FakeBackend(["0", "1"])
        self.backend_b = FakeBackend(["0", "2"])
        self.manager = await build_manager(
            [self.path_a, self.path_b],
            self.slots,
            {self.path_a.path_id: self.backend_a, self.path_b.path_id: self.backend_b},
        )

    async def test_slot_two_goes_to_the_second_install_native_zero(self) -> None:
        await self.manager.open("2")

        self.assertEqual(self.backend_b.calls, [("open", "0")])
        self.assertEqual(self.backend_a.calls, [])

    async def test_slot_three_maps_to_non_contiguous_native_index(self) -> None:
        await self.manager.close("3")

        self.assertEqual(self.backend_b.calls, [("close", "2")])

    async def test_first_install_keeps_its_own_indexes(self) -> None:
        await self.manager.close("1")

        self.assertEqual(self.backend_a.calls, [("close", "1")])
        self.assertEqual(self.backend_b.calls, [])

    async def test_resolve_device_reports_real_type_and_native_index(self) -> None:
        ref = self.manager.resolve_device("3")

        assert ref is not None
        self.assertEqual(ref.emulator_type, "ldplayer")
        self.assertEqual(ref.native_index, "2")
        self.assertTrue(ref.manager_path.endswith("ldconsole.exe"))


class MergedListingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.path_a = make_path(LD_A, "主力")
        self.path_b = make_path(LD_B, "备用")
        self.slots = SlotTable()
        self.slots.sync_path(self.path_a.path_id, ["0", "1"])
        self.slots.sync_path(self.path_b.path_id, ["0"])
        self.backends = {
            self.path_a.path_id: FakeBackend(["0", "1"]),
            self.path_b.path_id: FakeBackend(["0"]),
        }
        self.manager = await build_manager(
            [self.path_a, self.path_b], self.slots, self.backends
        )

    async def test_get_info_is_keyed_by_slot(self) -> None:
        info = await self.manager.getInfo(None)

        self.assertEqual(sorted(info), ["0", "1", "2"])

    async def test_get_device_info_keeps_native_index_inside_the_row(self) -> None:
        """键是设备号，条目里的 idx 必须是原生索引——ADB 序列号按它算。"""
        devices = await self.manager.get_device_info(None)

        self.assertEqual(sorted(devices), ["0", "1", "2"])
        self.assertEqual(devices["2"].idx, 0)

    async def test_single_slot_lookup_is_also_keyed_by_slot(self) -> None:
        devices = await self.manager.get_device_info("2")

        self.assertEqual(list(devices), ["2"])
        self.assertEqual(devices["2"].idx, 0)

    async def test_one_install_failing_does_not_hide_the_other(self) -> None:
        self.backends[self.path_b.path_id].fail = True

        info = await self.manager.getInfo(None)

        self.assertEqual(sorted(info), ["0", "1"])


class UnavailableSlotTest(unittest.IsolatedAsyncioTestCase):
    """解析不到设备时必须明确报错，绝不能回退到第一台。"""

    async def asyncSetUp(self) -> None:
        self.path_a = make_path(LD_A, "主力")
        self.slots = SlotTable()
        self.slots.sync_path(self.path_a.path_id, ["0", "1"])
        self.backend = FakeBackend(["0", "1"])
        self.manager = await build_manager(
            [self.path_a], self.slots, {self.path_a.path_id: self.backend}
        )

    async def test_unknown_slot_raises(self) -> None:
        with self.assertRaises(DeviceUnavailableError):
            await self.manager.open("9")
        self.assertEqual(self.backend.calls, [])

    async def test_tombstoned_slot_raises(self) -> None:
        self.slots.tombstone_path(self.path_a.path_id)
        manager = await build_manager(
            [self.path_a], self.slots, {self.path_a.path_id: self.backend}
        )

        with self.assertRaises(DeviceUnavailableError):
            await manager.close("0")
        self.assertEqual(self.backend.calls, [])

    async def test_status_of_an_unknown_slot_is_not_found(self) -> None:
        status = await self.manager.getStatus("9")

        self.assertEqual(status, DeviceStatus.NOT_FOUND)
        self.assertEqual(self.backend.calls, [])

    async def test_resolve_device_returns_none_instead_of_guessing(self) -> None:
        self.assertIsNone(self.manager.resolve_device("9"))


class AdbPathTest(unittest.IsolatedAsyncioTestCase):
    """get_adb_path() 签名里没有索引，多安装时不能瞎猜。"""

    async def test_multiple_installs_without_a_resolved_slot_returns_none(self) -> None:
        path_a = make_path(LD_A, "主力")
        path_b = make_path(LD_B, "备用")
        slots = SlotTable()
        slots.sync_path(path_a.path_id, ["0"])
        slots.sync_path(path_b.path_id, ["0"])
        manager = await build_manager(
            [path_a, path_b],
            slots,
            {path_a.path_id: FakeBackend(["0"]), path_b.path_id: FakeBackend(["0"])},
        )

        self.assertIsNone(manager.get_adb_path())


class RejectsWrongConfigTypeTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_emulator2_config_is_rejected(self) -> None:
        config = EmulatorConfig()
        await config.load({"Info": {"Type": "ldplayer"}})

        with self.assertRaises(ValueError):
            Emulator2Manager(config)


class PathIdStabilityTest(unittest.TestCase):
    def test_path_record_id_matches_make_path_id(self) -> None:
        record = make_path(LD_A, "主力")

        self.assertEqual(record.path_id, make_path_id(LD_A))


if __name__ == "__main__":
    unittest.main()
