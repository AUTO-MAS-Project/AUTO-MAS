import json
import unittest

from app.utils.emulator2 import PathRecord, SlotRecord, SlotTable, make_path_id


class MakePathIdTest(unittest.TestCase):
    def test_same_path_gives_same_id_regardless_of_separator_or_case(self) -> None:
        variants = [
            r"D:\leidian\LDPlayer14",
            "D:/leidian/LDPlayer14",
            "D:/leidian/LDPlayer14/",
            r"d:\LEIDIAN\ldplayer14",
        ]
        ids = {make_path_id(path) for path in variants}

        self.assertEqual(len(ids), 1)

    def test_different_paths_give_different_ids(self) -> None:
        self.assertNotEqual(
            make_path_id(r"D:\leidian\LDPlayer14"),
            make_path_id(r"E:\leidian\LDPlayer14"),
        )


class SlotAllocationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.table = SlotTable()
        self.path_a = make_path_id(r"D:\leidian\LDPlayer14")
        self.path_b = make_path_id(r"C:\Program Files\NetEase\MuMu")

    def test_first_path_gets_slots_from_zero(self) -> None:
        added = self.table.sync_path(self.path_a, ["0", "1", "2", "3"])

        self.assertEqual([record.slot for record in added], ["0", "1", "2", "3"])

    def test_second_path_continues_numbering(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1", "2", "3"])

        added = self.table.sync_path(self.path_b, ["0", "2"])

        self.assertEqual([record.slot for record in added], ["4", "5"])
        self.assertEqual([record.native_index for record in added], ["0", "2"])

    def test_non_contiguous_native_indexes_are_preserved(self) -> None:
        """MuMu 的原生索引可能是 0 和 2（中间那个被删过）。"""
        self.table.sync_path(self.path_b, ["0", "2"])

        self.assertEqual(self.table.resolve("0").native_index, "0")
        self.assertEqual(self.table.resolve("1").native_index, "2")

    def test_sync_is_idempotent(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1"])

        added = self.table.sync_path(self.path_a, ["0", "1"])

        self.assertEqual(added, [])
        self.assertEqual(len(self.table.records), 2)

    def test_new_instance_appends_without_touching_existing(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1"])

        added = self.table.sync_path(self.path_a, ["0", "1", "2"])

        self.assertEqual([record.slot for record in added], ["2"])
        self.assertEqual(self.table.resolve("0").native_index, "0")
        self.assertEqual(self.table.resolve("1").native_index, "1")

    def test_missing_native_index_does_not_change_the_table(self) -> None:
        """一次枚举失败不等于实例被删除，不能写进持久化状态。"""
        self.table.sync_path(self.path_a, ["0", "1", "2"])
        before = self.table.to_json()

        self.table.sync_path(self.path_a, ["0"])

        self.assertEqual(self.table.to_json(), before)


class SlotNeverReusedTest(unittest.TestCase):
    """移除路径后号码永不复用——否则新加的模拟器会顶掉旧脚本的绑定。"""

    def setUp(self) -> None:
        self.table = SlotTable()
        self.path_a = make_path_id(r"D:\leidian\LDPlayer14")
        self.path_b = make_path_id(r"C:\Program Files\NetEase\MuMu")

    def test_tombstoned_slots_are_not_handed_to_another_path(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1", "2", "3"])
        tombstoned = self.table.tombstone_path(self.path_a)

        added = self.table.sync_path(self.path_b, ["0", "2"])

        self.assertEqual(tombstoned, ["0", "1", "2", "3"])
        self.assertEqual([record.slot for record in added], ["4", "5"])

    def test_tombstoned_records_are_kept_not_deleted(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1"])

        self.table.tombstone_path(self.path_a)

        record = self.table.resolve("0")
        assert record is not None
        self.assertEqual(record.state, "tombstone")

    def test_readding_the_same_path_reuses_the_original_slots(self) -> None:
        self.table.sync_path(self.path_a, ["0", "1"])
        self.table.tombstone_path(self.path_a)

        revived = self.table.revive_path(self.path_a)
        added = self.table.sync_path(self.path_a, ["0", "1"])

        self.assertEqual(revived, ["0", "1"])
        self.assertEqual(added, [])
        self.assertEqual(self.table.slots_of(self.path_a), ["0", "1"])

    def test_sync_alone_does_not_revive_a_tombstone(self) -> None:
        """移除过的路径不能因为一次枚举就自己回来。"""
        self.table.sync_path(self.path_a, ["0"])
        self.table.tombstone_path(self.path_a)

        added = self.table.sync_path(self.path_a, ["0"])

        self.assertEqual(added, [])
        self.assertEqual(self.table.resolve("0").state, "tombstone")


class SlotIdentityByIndexTest(unittest.TestCase):
    """不做身份指纹：同一路径同一原生索引就是同一个设备号。"""

    def test_recreated_instance_at_the_same_index_keeps_its_slot(self) -> None:
        table = SlotTable()
        path = make_path_id(r"D:\leidian\LDPlayer14")
        table.sync_path(path, ["0", "1", "2", "3"])

        # 用户删掉 3 号又新建一个，雷电重新分配到索引 3
        table.sync_path(path, ["0", "1", "2", "3"])

        self.assertEqual(len(table.records), 4)
        self.assertEqual(table.resolve("3").native_index, "3")


class SlotPersistenceTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        table = SlotTable()
        path = make_path_id(r"D:\leidian\LDPlayer14")
        table.sync_path(path, ["0", "1"])
        table.tombstone_path(path)

        restored = SlotTable.from_json(table.to_json())

        self.assertEqual(restored.records, table.records)

    def test_corrupt_payload_falls_back_to_empty_table(self) -> None:
        for raw in ("", None, "not json", "{}", "[1, 2, 3]"):
            with self.subTest(raw=raw):
                self.assertEqual(SlotTable.from_json(raw).records, [])

    def test_entries_without_a_numeric_slot_are_dropped(self) -> None:
        raw = json.dumps([{"slot": "x", "pathId": "p", "nativeIndex": "0"}])

        self.assertEqual(SlotTable.from_json(raw).records, [])

    def test_next_slot_accounts_for_tombstones_after_reload(self) -> None:
        table = SlotTable()
        path = make_path_id(r"D:\leidian\LDPlayer14")
        table.sync_path(path, ["0", "1", "2"])
        table.tombstone_path(path)

        restored = SlotTable.from_json(table.to_json())

        self.assertEqual(restored.next_slot(), "3")


class PathRecordTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        record = PathRecord.create(
            install_path=r"D:\leidian\LDPlayer14",
            alias="主力",
            type="ldplayer",
            version="14.0.25.1",
        )

        self.assertEqual(PathRecord.from_dict(record.to_dict()), record)

    def test_path_id_is_derived_from_the_install_path(self) -> None:
        record = PathRecord.create(
            install_path=r"D:\leidian\LDPlayer14",
            alias="主力",
            type="ldplayer",
            version="14.0.25.1",
        )

        self.assertEqual(record.path_id, make_path_id("D:/leidian/LDPlayer14"))


class SlotRecordTest(unittest.TestCase):
    def test_unknown_state_falls_back_to_active(self) -> None:
        record = SlotRecord.from_dict(
            {"slot": "0", "pathId": "p", "nativeIndex": "0", "state": "wat"}
        )

        self.assertEqual(record.state, "active")


if __name__ == "__main__":
    unittest.main()
