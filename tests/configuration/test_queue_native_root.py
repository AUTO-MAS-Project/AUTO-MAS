"""QueueConfig 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import unittest
from uuid import UUID, uuid4

from app.configuration import (
    ConfigAggregateError,
    ConfigCollection,
    ConfigEntry,
    config_manager,
)
from app.configuration.roots.queue import (
    Queue,
    QueueItem,
    Queues,
    SCRIPT_COLLECTION_NAME,
    TimeSet,
    legacy_queues_to_wire,
    queues_wire_to_legacy,
)


class _ScriptTarget(ConfigEntry):
    """QueueItem ref 测试用最小脚本目标。"""


def _legacy_queue(
    queue_uid: UUID,
    *,
    queue_item_uid: UUID | None = None,
    time_set_uid: UUID | None = None,
    script_id: str = "-",
) -> dict[str, object]:
    queue_items: dict[str, object] = {"instances": []}
    if queue_item_uid is not None:
        queue_items["instances"] = [
            {"uid": str(queue_item_uid), "type": "QueueItem"}
        ]
        queue_items[str(queue_item_uid)] = _queue_item_defaults()
        queue_items[str(queue_item_uid)]["Info"]["ScriptId"] = script_id

    time_sets: dict[str, object] = {"instances": []}
    if time_set_uid is not None:
        time_sets["instances"] = [
            {"uid": str(time_set_uid), "type": "TimeSet"}
        ]
        time_sets[str(time_set_uid)] = {
            "Info": {
                "Enabled": True,
                "Days": ["Monday", "Friday"],
                "Time": "08:30",
            }
        }

    return {
        "instances": [{"uid": str(queue_uid), "type": "QueueConfig"}],
        str(queue_uid): {
            "Info": {
                "Name": "测试队列",
                "TimeEnabled": True,
                "StartUpEnabled": False,
                "CycleEnabled": False,
                "AfterAccomplish": "NoAction",
            },
            "Data": {"LastTimedStart": "2026-07-23 08:30"},
            "SubConfigsInfo": {
                "TimeSet": time_sets,
                "QueueItem": queue_items,
            },
        },
    }


def _queue_item_defaults() -> dict[str, object]:
    return {
        "Info": {"ScriptId": "-"},
        "Schedule": {
            "Enabled": True,
            "Mode": "fixed_time",
            "Days": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
            "Time": "00:00",
            "IntervalMinutes": 480,
            "IntervalAnchor": "start",
            "NextRunAt": "2000-01-01 00:00:00",
        },
        "Data": {
            "LastCycleStartedAt": "2000-01-01 00:00:00",
            "LastCycleFinishedAt": "2000-01-01 00:00:00",
            "CycleRunId": "",
            "CycleState": "idle",
            "CycleRevision": 0,
            "CycleResult": "",
            "CycleError": "",
            "CycleUpdatedAt": "2000-01-01 00:00:00",
        },
    }


class QueueNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_nested_crud_update_and_order(self) -> None:
        scripts = ConfigCollection(_ScriptTarget, name=SCRIPT_COLLECTION_NAME)
        try:
            await scripts.activate()
            first_script = scripts.add(_ScriptTarget)
            second_script = scripts.add(_ScriptTarget)
            await scripts.commit()

            root = Queues()
            await root.activate()
            first_queue = root.add(Queue)
            second_queue = root.add(
                Queue,
                wire={"Info": {"Name": "第二队列"}},
            )
            await root.commit()

            queue = root[first_queue]
            first_item = queue.QueueItem.add(
                QueueItem,
                wire={"Info": {"ScriptId": str(first_script)}},
            )
            second_item = queue.QueueItem.add(
                QueueItem,
                wire={"Info": {"ScriptId": str(second_script)}},
            )
            await queue.QueueItem.commit()
            time_uid = queue.TimeSet.add(
                TimeSet,
                wire={
                    "Info": {
                        "Enabled": False,
                        "Days": ["Tuesday"],
                        "Time": "12:05",
                    }
                },
            )
            await queue.TimeSet.commit()

            self.assertEqual(
                list(root.keys()),
                [first_queue, second_queue],
            )
            self.assertEqual(
                list(queue.QueueItem.keys()),
                [first_item, second_item],
            )
            self.assertEqual(
                queue.QueueItem[first_item].Info.ScriptId,
                str(first_script),
            )
            self.assertEqual(queue.TimeSet[time_uid].Info.Days, ["Tuesday"])

            queue.Info.TimeEnabled = True
            await queue.commit()
            queue.QueueItem.set_order([second_item, first_item])
            await queue.QueueItem.commit()
            root.set_order([second_queue, first_queue])
            await root.commit()
            self.assertEqual(
                list(queue.QueueItem.keys()),
                [second_item, first_item],
            )
            self.assertEqual(
                list(root.keys()),
                [second_queue, first_queue],
            )

            wire = await root.to_dict(if_decrypt=False)
            rollback = queues_wire_to_legacy(wire)
            self.assertEqual(
                rollback["instances"],
                [
                    {"uid": str(second_queue), "type": "QueueConfig"},
                    {"uid": str(first_queue), "type": "QueueConfig"},
                ],
            )
            self.assertEqual(
                rollback[str(first_queue)]["SubConfigsInfo"]["QueueItem"][
                    "instances"
                ],
                [
                    {"uid": str(second_item), "type": "QueueItem"},
                    {"uid": str(first_item), "type": "QueueItem"},
                ],
            )

            queue.QueueItem.remove(second_item)
            await queue.QueueItem.commit()
            queue.TimeSet.remove(time_uid)
            await queue.TimeSet.commit()
            root.remove(second_queue)
            await root.commit()
            self.assertEqual(list(queue.QueueItem.keys()), [first_item])
            self.assertEqual(list(queue.TimeSet.keys()), [])
            self.assertEqual(list(root.keys()), [first_queue])
        finally:
            config_manager.unregister_collection(SCRIPT_COLLECTION_NAME)

    async def test_ref_orphan_uses_exact_legacy_default(self) -> None:
        scripts = ConfigCollection(_ScriptTarget, name=SCRIPT_COLLECTION_NAME)
        try:
            await scripts.activate()
            root = Queues()
            await root.activate()
            queue_uid = root.add(Queue)
            await root.commit()
            orphan = uuid4()
            item_uid = root[queue_uid].QueueItem.add(
                QueueItem,
                wire={"Info": {"ScriptId": str(orphan)}},
            )
            await root[queue_uid].QueueItem.commit()
            self.assertEqual(
                root[queue_uid].QueueItem[item_uid].Info.ScriptId,
                "-",
            )
        finally:
            config_manager.unregister_collection(SCRIPT_COLLECTION_NAME)

    async def test_runtime_types_days_and_datetime_are_strict(self) -> None:
        root = Queues()
        await root.activate()
        queue_uid = root.add(Queue)
        await root.commit()
        queue = root[queue_uid]
        time_uid = queue.TimeSet.add(TimeSet)
        await queue.TimeSet.commit()

        queue.Info.TimeEnabled = 1  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await queue.commit()
        self.assertIs(queue.Info.TimeEnabled, False)

        queue.Data.LastTimedStart = "not-a-date"
        with self.assertRaises(ConfigAggregateError):
            await queue.commit()
        self.assertEqual(queue.Data.LastTimedStart, "2000-01-01 00:00")

        queue.TimeSet[time_uid].Info.Days = ["Funday"]  # type: ignore[list-item]
        with self.assertRaises(ConfigAggregateError):
            await queue.TimeSet[time_uid].commit()
        self.assertEqual(
            queue.TimeSet[time_uid].Info.Days,
            [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
        )

    async def test_unknown_nested_field_fails_activation_atomically(self) -> None:
        queue_uid = uuid4()
        time_uid = uuid4()
        root = Queues(
            wire={
                "order": [{"uid": str(queue_uid), "type": "Queue"}],
                "data": {
                    str(queue_uid): {
                        "Info": {"Name": "坏队列"},
                        "TimeSet": {
                            "order": [
                                {"uid": str(time_uid), "type": "TimeSet"}
                            ],
                            "data": {
                                str(time_uid): {
                                    "Info": {
                                        "Time": "00:00",
                                        "Unknown": True,
                                    }
                                }
                            },
                        },
                    }
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.keys()), [])


class QueueLegacyConversionTest(unittest.TestCase):
    def test_round_trip_preserves_all_collection_orders_and_uuids(self) -> None:
        first_queue = uuid4()
        second_queue = uuid4()
        first_item = uuid4()
        second_item = uuid4()
        first_time = uuid4()
        second_time = uuid4()
        first_script = uuid4()
        second_script = uuid4()

        first_payload = _legacy_queue(
            first_queue,
            queue_item_uid=first_item,
            time_set_uid=first_time,
            script_id=str(first_script),
        )[str(first_queue)]
        second_payload = _legacy_queue(
            second_queue,
            queue_item_uid=second_item,
            time_set_uid=second_time,
            script_id=str(second_script),
        )[str(second_queue)]
        first_payload["SubConfigsInfo"]["QueueItem"]["instances"].append(
            {"uid": str(second_item), "type": "QueueItem"}
        )
        first_payload["SubConfigsInfo"]["QueueItem"][
            str(second_item)
        ] = _queue_item_defaults()
        first_payload["SubConfigsInfo"]["QueueItem"][str(second_item)][
            "Info"
        ]["ScriptId"] = str(second_script)
        legacy = {
            "instances": [
                {"uid": str(second_queue), "type": "QueueConfig"},
                {"uid": str(first_queue), "type": "QueueConfig"},
            ],
            str(first_queue): first_payload,
            str(second_queue): second_payload,
        }
        before = copy.deepcopy(legacy)

        wire = legacy_queues_to_wire(legacy)
        restored = queues_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(restored, legacy)
        self.assertEqual(
            [item["uid"] for item in wire["order"]],
            [str(second_queue), str(first_queue)],
        )
        self.assertEqual(
            [
                item["uid"]
                for item in wire["data"][str(first_queue)]["QueueItem"][
                    "order"
                ]
            ],
            [str(first_item), str(second_item)],
        )

    def test_missing_fields_use_exact_r6_defaults(self) -> None:
        queue_uid = uuid4()
        legacy = {
            "instances": [
                {"uid": str(queue_uid), "type": "QueueConfig"}
            ],
            str(queue_uid): {},
        }

        restored = queues_wire_to_legacy(
            legacy_queues_to_wire(legacy)
        )[str(queue_uid)]
        self.assertEqual(
            restored["Info"],
            {
                "Name": "新队列",
                "TimeEnabled": False,
                "StartUpEnabled": False,
                "CycleEnabled": False,
                "AfterAccomplish": "NoAction",
            },
        )
        self.assertEqual(
            restored["Data"],
            {"LastTimedStart": "2000-01-01 00:00"},
        )
        self.assertEqual(
            restored["SubConfigsInfo"],
            {
                "TimeSet": {"instances": []},
                "QueueItem": {"instances": []},
            },
        )

    def test_nested_item_defaults_match_r6(self) -> None:
        queue_uid = uuid4()
        item_uid = uuid4()
        time_uid = uuid4()
        legacy = _legacy_queue(
            queue_uid,
            queue_item_uid=item_uid,
            time_set_uid=time_uid,
        )
        legacy[str(queue_uid)]["SubConfigsInfo"]["QueueItem"][
            str(item_uid)
        ] = {}
        legacy[str(queue_uid)]["SubConfigsInfo"]["TimeSet"][
            str(time_uid)
        ] = {}

        restored = queues_wire_to_legacy(
            legacy_queues_to_wire(legacy)
        )[str(queue_uid)]["SubConfigsInfo"]
        self.assertEqual(
            restored["QueueItem"][str(item_uid)],
            _queue_item_defaults(),
        )
        self.assertEqual(
            restored["TimeSet"][str(time_uid)],
            {
                "Info": {
                    "Enabled": True,
                    "Days": [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ],
                    "Time": "00:00",
                }
            },
        )

    def test_time_set_keeps_r6_day_order_duplicates_and_empty_list(self) -> None:
        queue_uid = uuid4()
        time_uid = uuid4()
        legacy = _legacy_queue(queue_uid, time_set_uid=time_uid)
        time_info = legacy[str(queue_uid)]["SubConfigsInfo"]["TimeSet"][
            str(time_uid)
        ]["Info"]
        time_info["Days"] = ["Friday", "Monday", "Friday"]
        restored = queues_wire_to_legacy(
            legacy_queues_to_wire(legacy)
        )[str(queue_uid)]["SubConfigsInfo"]["TimeSet"][str(time_uid)]
        self.assertEqual(
            restored["Info"]["Days"],
            ["Friday", "Monday", "Friday"],
        )

        time_info["Days"] = []
        restored = queues_wire_to_legacy(
            legacy_queues_to_wire(legacy)
        )[str(queue_uid)]["SubConfigsInfo"]["TimeSet"][str(time_uid)]
        self.assertEqual(restored["Info"]["Days"], [])

    def test_unknown_or_orphan_data_fails_closed(self) -> None:
        queue_uid = uuid4()
        orphan = uuid4()
        payload = _legacy_queue(queue_uid)
        payload[str(orphan)] = {"Info": {}}
        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            legacy_queues_to_wire(payload)

        payload = _legacy_queue(queue_uid)
        payload[str(queue_uid)]["Info"]["Unknown"] = True
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_queues_to_wire(payload)

        item_uid = uuid4()
        payload = _legacy_queue(queue_uid, queue_item_uid=item_uid)
        nested = payload[str(queue_uid)]["SubConfigsInfo"]["QueueItem"]
        nested["instances"] = []
        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            legacy_queues_to_wire(payload)

    def test_duplicate_invalid_uuid_and_wrong_types_fail_closed(self) -> None:
        queue_uid = uuid4()
        duplicate = _legacy_queue(queue_uid)
        duplicate["instances"].append(
            {"uid": str(queue_uid), "type": "QueueConfig"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_queues_to_wire(duplicate)

        alias_uid = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        alias_duplicate = _legacy_queue(alias_uid)
        alias_duplicate[str(alias_uid).upper()] = copy.deepcopy(
            alias_duplicate[str(alias_uid)]
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_queues_to_wire(alias_duplicate)

        invalid_uid = {
            "instances": [{"uid": "bad", "type": "QueueConfig"}],
            "bad": {},
        }
        with self.assertRaisesRegex(ValueError, "有效 UUID"):
            legacy_queues_to_wire(invalid_uid)

        wrong_type = _legacy_queue(queue_uid)
        wrong_type["instances"][0]["type"] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 QueueConfig"):
            legacy_queues_to_wire(wrong_type)

        item_uid = uuid4()
        nested_wrong_type = _legacy_queue(
            queue_uid,
            queue_item_uid=item_uid,
        )
        nested_wrong_type[str(queue_uid)]["SubConfigsInfo"]["QueueItem"][
            "instances"
        ][0]["type"] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 QueueItem"):
            legacy_queues_to_wire(nested_wrong_type)

    def test_invalid_values_fail_closed(self) -> None:
        queue_uid = uuid4()
        item_uid = uuid4()
        time_uid = uuid4()

        payload = _legacy_queue(
            queue_uid,
            queue_item_uid=item_uid,
            time_set_uid=time_uid,
        )
        payload[str(queue_uid)]["Info"]["TimeEnabled"] = 1
        with self.assertRaisesRegex(TypeError, "布尔值"):
            legacy_queues_to_wire(payload)

        payload = _legacy_queue(queue_uid)
        payload[str(queue_uid)]["Info"]["AfterAccomplish"] = "FormatDisk"
        with self.assertRaisesRegex(ValueError, "动作集合"):
            legacy_queues_to_wire(payload)

        payload = _legacy_queue(queue_uid)
        payload[str(queue_uid)]["Data"]["LastTimedStart"] = "tomorrow"
        with self.assertRaisesRegex(ValueError, "LastTimedStart"):
            legacy_queues_to_wire(payload)

        payload = _legacy_queue(queue_uid, time_set_uid=time_uid)
        payload[str(queue_uid)]["SubConfigsInfo"]["TimeSet"][
            str(time_uid)
        ]["Info"]["Days"] = ["Funday"]
        with self.assertRaisesRegex(ValueError, "英文星期"):
            legacy_queues_to_wire(payload)

        payload = _legacy_queue(queue_uid, queue_item_uid=item_uid)
        payload[str(queue_uid)]["SubConfigsInfo"]["QueueItem"][
            str(item_uid)
        ]["Info"]["ScriptId"] = "not-a-uuid"
        with self.assertRaisesRegex(ValueError, "UUID"):
            legacy_queues_to_wire(payload)

    def test_hybrid_nested_alias_conflict_fails_closed(self) -> None:
        queue_uid = uuid4()
        payload = _legacy_queue(queue_uid)
        payload[str(queue_uid)]["QueueItem"] = {"instances": []}

        with self.assertRaisesRegex(ValueError, "别名冲突"):
            legacy_queues_to_wire(payload)

    def test_v2_missing_or_orphan_nested_data_fails_closed(self) -> None:
        queue_uid = uuid4()
        item_uid = uuid4()
        wire = legacy_queues_to_wire(_legacy_queue(queue_uid))
        wire["data"][str(queue_uid)]["QueueItem"] = {
            "order": [{"uid": str(item_uid), "type": "QueueItem"}],
            "data": {},
        }

        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            queues_wire_to_legacy(wire)

    def test_empty_root_is_valid(self) -> None:
        self.assertEqual(
            legacy_queues_to_wire({}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            queues_wire_to_legacy({"order": [], "data": {}}),
            {"instances": []},
        )
