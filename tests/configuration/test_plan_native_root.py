"""PlanConfig 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import unittest
from typing import Any
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.plan import (
    MaaPlan,
    PLAN_GROUPS,
    Plans,
    legacy_plans_to_wire,
    plans_wire_to_legacy,
)


def _plan_group(**overrides: object) -> dict[str, object]:
    group: dict[str, object] = {
        "MedicineNumb": 0,
        "SeriesNumb": "0",
        "Stage": "-",
        "Stage_1": "-",
        "Stage_2": "-",
        "Stage_3": "-",
        "Stage_Remain": "-",
    }
    group.update(overrides)
    return group


def _plan_entry(
    *,
    name: str = "新 MAA 计划表",
    mode: str = "ALL",
) -> dict[str, object]:
    entry: dict[str, object] = {
        "Info": {
            "Name": name,
            "Mode": mode,
        }
    }
    for group_name in PLAN_GROUPS:
        entry[group_name] = _plan_group()
    return entry


def _legacy_plan(
    uid: UUID,
    *,
    name: str = "新 MAA 计划表",
    mode: str = "ALL",
) -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": "MaaPlanConfig"}],
        str(uid): _plan_entry(name=name, mode=mode),
    }


class PlanNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_activation_crud_update_and_order(self) -> None:
        root = Plans()
        await root.activate()

        first = root.add(MaaPlan)
        second = root.add(
            MaaPlan,
            wire={
                "Info": {"Name": "周计划", "Mode": "Weekly"},
                "Monday": {
                    "MedicineNumb": 2,
                    "SeriesNumb": "6",
                    "Stage": "1-7",
                },
            },
        )
        await root.commit()

        self.assertEqual(list(root.keys()), [first, second])
        self.assertEqual(root[first].Info.Name, "新 MAA 计划表")
        self.assertEqual(root[second].Info.Name, "周计划")
        self.assertEqual(
            root[second].get_current_info("Stage", weekday="Monday"),
            "1-7",
        )
        self.assertEqual(
            root[second].get_current_info("MedicineNumb", weekday="Monday"),
            2,
        )
        self.assertEqual(
            root[second].get_current_info("Stage", weekday="Tuesday"),
            "-",
        )

        root[first].Info.Name = "全局计划"
        root[first].ALL.Stage = "CE-6"
        await root[first].commit()
        self.assertEqual(
            root[first].get_current_info("Stage", weekday="not-used"),
            "CE-6",
        )

        root.set_order([second, first])
        await root.commit()
        self.assertEqual(list(root.keys()), [second, first])

        root.remove(second)
        await root.commit()
        self.assertEqual(list(root.keys()), [first])

    async def test_weekly_helper_rejects_unknown_weekday(self) -> None:
        root = Plans()
        await root.activate()
        uid = root.add(
            MaaPlan,
            wire={"Info": {"Mode": "Weekly"}},
        )
        await root.commit()

        with self.assertRaisesRegex(ValueError, "calendar.day_name"):
            root[uid].get_current_group(weekday="星期一")
        with self.assertRaisesRegex(KeyError, "未知 MAA 计划字段"):
            root[uid].get_current_info(  # type: ignore[arg-type]
                "Unknown",
                weekday="Monday",
            )

    async def test_unknown_field_fails_activation_atomically(self) -> None:
        uid = uuid4()
        root = Plans(
            wire={
                "order": [{"uid": str(uid), "type": "MaaPlan"}],
                "data": {
                    str(uid): {
                        "Info": {
                            "Name": "测试计划",
                            "Unknown": "must-fail",
                        }
                    }
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.keys()), [])

    async def test_strict_runtime_types_options_and_bounds(self) -> None:
        root = Plans()
        await root.activate()
        uid = root.add(MaaPlan)
        await root.commit()

        root[uid].ALL.MedicineNumb = 10000
        with self.assertRaises(ConfigAggregateError):
            await root[uid].commit()
        self.assertEqual(root[uid].ALL.MedicineNumb, 0)

        root[uid].Monday.SeriesNumb = "8"  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root[uid].commit()
        self.assertEqual(root[uid].Monday.SeriesNumb, "0")

        root[uid].Tuesday.Stage = 7  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root[uid].commit()
        self.assertEqual(root[uid].Tuesday.Stage, "-")


class PlanLegacyConversionTest(unittest.TestCase):
    def test_real_r6_shape_round_trip_preserves_order_uuid_and_values(
        self,
    ) -> None:
        first = uuid4()
        second = uuid4()
        first_entry = _plan_entry(name="日常计划", mode="Weekly")
        second_entry = _plan_entry(name="全局计划")
        cast_monday = first_entry["Monday"]
        assert isinstance(cast_monday, dict)
        cast_monday.update(
            {
                "MedicineNumb": 3,
                "SeriesNumb": "-1",
                "Stage": "1-7",
                "Stage_1": "CE-6",
                "Stage_Remain": "AP-5",
            }
        )
        cast_all = second_entry["ALL"]
        assert isinstance(cast_all, dict)
        cast_all["Stage"] = "LS-6"
        legacy: dict[str, Any] = {
            "instances": [
                {"uid": str(second), "type": "MaaPlanConfig"},
                {"uid": str(first), "type": "MaaPlanConfig"},
            ],
            str(first): first_entry,
            str(second): second_entry,
        }
        before = copy.deepcopy(legacy)

        wire = legacy_plans_to_wire(legacy)
        restored = plans_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(restored, legacy)
        self.assertEqual(
            [item["uid"] for item in wire["order"]],
            [str(second), str(first)],
        )
        self.assertTrue(
            all(item["type"] == "MaaPlan" for item in wire["order"])
        )

    def test_missing_known_fields_use_exact_r6_defaults(self) -> None:
        uid = uuid4()
        legacy = {
            "instances": [{"uid": str(uid), "type": "MaaPlanConfig"}],
            str(uid): {
                "Info": {"Name": "只提供名称"},
                "Monday": {"Stage": "1-7"},
            },
        }

        restored = plans_wire_to_legacy(legacy_plans_to_wire(legacy))
        entry = restored[str(uid)]

        self.assertEqual(
            entry["Info"],
            {"Name": "只提供名称", "Mode": "ALL"},
        )
        self.assertEqual(
            entry["ALL"],
            _plan_group(),
        )
        self.assertEqual(
            entry["Monday"],
            _plan_group(Stage="1-7"),
        )
        self.assertEqual(
            set(entry),
            {"Info", *PLAN_GROUPS},
        )

    def test_empty_legacy_and_wire_roots_are_valid(self) -> None:
        self.assertEqual(
            legacy_plans_to_wire({}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            legacy_plans_to_wire({"instances": []}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            plans_wire_to_legacy({}),
            {"instances": []},
        )
        self.assertEqual(
            plans_wire_to_legacy({"order": [], "data": {}}),
            {"instances": []},
        )

    def test_unknown_or_orphan_data_fails_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        payload = _legacy_plan(uid)
        payload[str(orphan)] = _plan_entry()
        with self.assertRaisesRegex(ValueError, "孤儿或未知"):
            legacy_plans_to_wire(payload)

        payload = _legacy_plan(uid)
        entry = payload[str(uid)]
        assert isinstance(entry, dict)
        entry["UnknownGroup"] = {}
        with self.assertRaisesRegex(ValueError, "UnknownGroup"):
            legacy_plans_to_wire(payload)

        payload = _legacy_plan(uid)
        entry = payload[str(uid)]
        assert isinstance(entry, dict)
        info = entry["Info"]
        assert isinstance(info, dict)
        info["Unknown"] = True
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_plans_to_wire(payload)

        payload = _legacy_plan(uid)
        entry = payload[str(uid)]
        assert isinstance(entry, dict)
        monday = entry["Monday"]
        assert isinstance(monday, dict)
        monday["Unknown"] = True
        with self.assertRaisesRegex(ValueError, "Monday.Unknown"):
            legacy_plans_to_wire(payload)

    def test_duplicate_invalid_uid_and_type_fail_closed(self) -> None:
        uid = uuid4()
        duplicate = _legacy_plan(uid)
        instances = duplicate["instances"]
        assert isinstance(instances, list)
        instances.append({"uid": str(uid), "type": "MaaPlanConfig"})
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_plans_to_wire(duplicate)

        invalid_uid = {
            "instances": [{"uid": "not-a-uuid", "type": "MaaPlanConfig"}],
            "not-a-uuid": _plan_entry(),
        }
        with self.assertRaisesRegex(ValueError, "有效 UUID"):
            legacy_plans_to_wire(invalid_uid)

        invalid_type = _legacy_plan(uid)
        instances = invalid_type["instances"]
        assert isinstance(instances, list)
        item = instances[0]
        assert isinstance(item, dict)
        item["type"] = "OtherPlan"
        with self.assertRaisesRegex(ValueError, "仅允许 MaaPlanConfig"):
            legacy_plans_to_wire(invalid_type)

    def test_invalid_legacy_values_fail_closed(self) -> None:
        uid = uuid4()
        cases = [
            ("Info", "Mode", "Daily", "Mode"),
            ("ALL", "MedicineNumb", True, "0..9999"),
            ("Monday", "MedicineNumb", 10000, "0..9999"),
            ("Tuesday", "SeriesNumb", 6, "SeriesNumb"),
            ("Wednesday", "SeriesNumb", "8", "SeriesNumb"),
            ("Thursday", "Stage", 1, "Stage"),
        ]
        for group_name, field_name, value, error in cases:
            with self.subTest(group=group_name, field=field_name):
                payload = _legacy_plan(uid)
                entry = payload[str(uid)]
                assert isinstance(entry, dict)
                group = entry[group_name]
                assert isinstance(group, dict)
                group[field_name] = value
                with self.assertRaisesRegex(
                    (TypeError, ValueError),
                    error,
                ):
                    legacy_plans_to_wire(payload)

    def test_v2_unknown_orphan_duplicate_and_wrong_type_fail_closed(
        self,
    ) -> None:
        uid = uuid4()
        orphan = uuid4()
        with self.assertRaisesRegex(ValueError, "缺失或孤儿 uid"):
            plans_wire_to_legacy(
                {
                    "order": [{"uid": str(uid), "type": "MaaPlan"}],
                    "data": {
                        str(uid): _plan_entry(),
                        str(orphan): _plan_entry(),
                    },
                }
            )

        with self.assertRaisesRegex(ValueError, "重复 uid"):
            plans_wire_to_legacy(
                {
                    "order": [
                        {"uid": str(uid), "type": "MaaPlan"},
                        {"uid": str(uid), "type": "MaaPlan"},
                    ],
                    "data": {str(uid): _plan_entry()},
                }
            )

        with self.assertRaisesRegex(ValueError, "仅允许 MaaPlan"):
            plans_wire_to_legacy(
                {
                    "order": [{"uid": str(uid), "type": "MaaPlanConfig"}],
                    "data": {str(uid): _plan_entry()},
                }
            )

        invalid_entry = _plan_entry()
        monday = invalid_entry["Monday"]
        assert isinstance(monday, dict)
        monday["MedicineNumb"] = False
        with self.assertRaisesRegex(ValueError, "0..9999"):
            plans_wire_to_legacy(
                {
                    "order": [{"uid": str(uid), "type": "MaaPlan"}],
                    "data": {str(uid): invalid_entry},
                }
            )

        payload = {
            "order": [{"uid": str(uid), "type": "MaaPlan"}],
            "data": {str(uid): _plan_entry()},
            "unknown": True,
        }
        with self.assertRaisesRegex(ValueError, "unknown"):
            plans_wire_to_legacy(payload)
