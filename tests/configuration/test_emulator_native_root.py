"""EmulatorConfig 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import unittest
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.emulator import (
    Emulator,
    Emulators,
    emulators_wire_to_legacy,
    legacy_emulators_to_wire,
)


def _legacy_emulator(
    uid: UUID,
    *,
    name: str = "测试模拟器",
    emulator_type: str = "general",
) -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": "EmulatorConfig"}],
        str(uid): {
            "Info": {
                "Name": name,
                "Type": emulator_type,
                "Path": "",
                "BossKey": "[]",
                "MaxWaitTime": 300,
                "ForceKillOnClose": True,
            }
        },
    }


class EmulatorNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_activation_crud_update_and_order(self) -> None:
        root = Emulators()
        await root.activate()

        first = root.add(Emulator)
        second = root.add(
            Emulator,
            wire={"Info": {"Name": "雷电", "Type": "ldplayer"}},
        )
        await root.commit()

        self.assertEqual(list(root.keys()), [first, second])
        self.assertEqual(root[first].Info.Name, "新模拟器")
        self.assertEqual(root[second].Info.Type, "ldplayer")

        root[first].Info.Name = "MuMu"
        root[first].Info.Type = "mumu"
        await root[first].commit()
        root.set_order([second, first])
        await root.commit()
        self.assertEqual(list(root.keys()), [second, first])
        self.assertEqual(root[first].Info.Name, "MuMu")

        root.remove(second)
        await root.commit()
        self.assertEqual(list(root.keys()), [first])

    async def test_native_dynamic_field_and_mapping_access(self) -> None:
        root = Emulators()
        await root.activate()
        uid = root.add(Emulator)
        await root.commit()

        self.assertEqual(list(root.items()), [(uid, root[uid])])
        self.assertEqual(root[uid].get("Info", "Name"), "新模拟器")

        await root[uid].set("Info", "Name", "原生 facade")

        self.assertEqual(root[uid].Info.Name, "原生 facade")
        self.assertEqual(
            (await root[uid].toDict())["Info"]["Name"],
            "原生 facade",
        )
        with self.assertRaises(ValueError):
            await root[uid].toDict(regenerate_uuids=True)
        with self.assertRaises(ConfigAggregateError):
            await root[uid].set_many(
                {
                    "Info": {
                        "Name": "不应部分提交",
                        "MaxWaitTime": 0,
                    }
                }
            )
        self.assertEqual(root[uid].Info.Name, "原生 facade")
        self.assertEqual(root[uid].Info.MaxWaitTime, 300)
        with self.assertRaises(AttributeError):
            root[uid].get("Info", "Missing")
        with self.assertRaises(TypeError):
            root[uid].get("model_fields_set", "Name")

    async def test_unknown_field_fails_activation_atomically(self) -> None:
        uid = uuid4()
        root = Emulators(
            wire={
                "order": [{"uid": str(uid), "type": "Emulator"}],
                "data": {
                    str(uid): {
                        "Info": {
                            "Name": "测试",
                            "Unknown": "must-fail",
                        }
                    }
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.keys()), [])

    async def test_strict_runtime_types_and_bounds(self) -> None:
        root = Emulators()
        await root.activate()
        uid = root.add(Emulator)
        await root.commit()

        root[uid].Info.MaxWaitTime = 0
        with self.assertRaises(ConfigAggregateError):
            await root[uid].commit()
        self.assertEqual(root[uid].Info.MaxWaitTime, 300)

        root[uid].Info.ForceKillOnClose = 1  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root[uid].commit()
        self.assertIs(root[uid].Info.ForceKillOnClose, True)


class EmulatorLegacyConversionTest(unittest.TestCase):
    def test_round_trip_preserves_order_uuid_and_values(self) -> None:
        first = uuid4()
        second = uuid4()
        legacy = {
            "instances": [
                {"uid": str(second), "type": "EmulatorConfig"},
                {"uid": str(first), "type": "EmulatorConfig"},
            ],
            str(first): _legacy_emulator(
                first,
                name="MuMu",
                emulator_type="mumu",
            )[str(first)],
            str(second): _legacy_emulator(
                second,
                name="雷电",
                emulator_type="ldplayer",
            )[str(second)],
        }
        before = copy.deepcopy(legacy)

        wire = legacy_emulators_to_wire(legacy)
        restored = emulators_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(restored, legacy)
        self.assertEqual(
            [item["uid"] for item in wire["order"]],
            [str(second), str(first)],
        )
        self.assertTrue(
            all(item["type"] == "Emulator" for item in wire["order"])
        )

    def test_missing_fields_use_exact_r6_defaults(self) -> None:
        uid = uuid4()
        legacy = {
            "instances": [{"uid": str(uid), "type": "EmulatorConfig"}],
            str(uid): {"Info": {"Name": "只提供名称"}},
        }

        restored = emulators_wire_to_legacy(
            legacy_emulators_to_wire(legacy)
        )
        self.assertEqual(
            restored[str(uid)]["Info"],
            {
                "Name": "只提供名称",
                "Type": "general",
                "Path": "",
                "BossKey": "[ ]",
                "MaxWaitTime": 300,
                "ForceKillOnClose": True,
            },
        )

    def test_legacy_data_aliases_are_migrated(self) -> None:
        uid = uuid4()
        legacy = {
            "instances": [{"uid": str(uid), "type": "EmulatorConfig"}],
            str(uid): {
                "Info": {
                    "Name": "旧模拟器",
                    "Path": "C:/offline/emulator.exe",
                    "ForceKillOnClose": False,
                },
                "Data": {
                    "Type": "mumu",
                    "BossKey": '["ctrl", "q"]',
                    "MaxWaitTime": 777,
                },
            },
        }

        wire = legacy_emulators_to_wire(legacy)
        info = wire["data"][str(uid)]["Info"]
        self.assertEqual(info["Type"], "mumu")
        self.assertEqual(info["BossKey"], '["ctrl", "q"]')
        self.assertEqual(info["MaxWaitTime"], 777)
        self.assertEqual(info["Path"], "C:/offline/emulator.exe")
        self.assertNotIn(
            "Data",
            emulators_wire_to_legacy(wire)[str(uid)],
        )

    def test_conflicting_current_and_legacy_alias_fails_closed(self) -> None:
        uid = uuid4()
        legacy = _legacy_emulator(uid)
        legacy[str(uid)]["Data"] = {"Type": "mumu"}

        with self.assertRaisesRegex(ValueError, "冲突"):
            legacy_emulators_to_wire(legacy)

    def test_unknown_or_orphan_data_fails_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        payload = _legacy_emulator(uid)
        payload[str(orphan)] = {"Info": {}}
        with self.assertRaisesRegex(ValueError, "孤儿或未知"):
            legacy_emulators_to_wire(payload)

        payload = _legacy_emulator(uid)
        payload[str(uid)]["Info"]["Unknown"] = True
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_emulators_to_wire(payload)

    def test_duplicate_invalid_uid_type_and_value_fail_closed(self) -> None:
        uid = uuid4()
        duplicate = _legacy_emulator(uid)
        duplicate["instances"].append(
            {"uid": str(uid), "type": "EmulatorConfig"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_emulators_to_wire(duplicate)

        invalid_uid = {
            "instances": [{"uid": "not-a-uuid", "type": "EmulatorConfig"}],
            "not-a-uuid": {"Info": {}},
        }
        with self.assertRaisesRegex(ValueError, "有效 UUID"):
            legacy_emulators_to_wire(invalid_uid)

        invalid_type = _legacy_emulator(uid)
        invalid_type["instances"][0]["type"] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 EmulatorConfig"):
            legacy_emulators_to_wire(invalid_type)

        invalid_value = _legacy_emulator(uid)
        invalid_value[str(uid)]["Info"]["MaxWaitTime"] = True
        with self.assertRaisesRegex(ValueError, "1..9999"):
            legacy_emulators_to_wire(invalid_value)

    def test_empty_legacy_root_is_valid(self) -> None:
        self.assertEqual(
            legacy_emulators_to_wire({}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            emulators_wire_to_legacy({"order": [], "data": {}}),
            {"instances": []},
        )
