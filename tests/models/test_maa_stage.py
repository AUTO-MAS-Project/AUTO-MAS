# getStage 双视图与活动关意图的回归测试。
# 背景：_stage_drop_entry 曾因缩进错误让材质关/玉关隐式返回 None，
# 且当时全仓无 getStage 覆盖，靠人工探针才定位——本文件锁住这条链路。

import json
import unittest
from datetime import datetime, timedelta, timezone

from app.models.config import (
    ActivityStageIntentValidator,
    GlobalConfig,
    MaaUserConfig,
)
from app.task.MAA.AutoProxy import _resolve_activity_stage

UTC8 = timezone(timedelta(hours=8))


def _fmt(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S")


def _now_utc8() -> datetime:
    """按活动时区（+8）取当前时刻。

    getStage 用活动自带的 TimeZone 把时间串还原成绝对时刻，夹具若按本机时区
    生成，窗口就跟着机器漂移（UTC 机器上活动会被判成未开始），结果取决于跑测
    试的机器。
    """

    return datetime.now(tz=UTC8)


def _stage_data(now: datetime) -> str:
    return json.dumps(
        {
            "Official": {
                "sideStoryStage": {
                    "sr": {
                        "Activity": {
                            "StageName": "测试活动",
                            "Tip": "",
                            "UtcStartTime": _fmt(now - timedelta(hours=2)),
                            "UtcExpireTime": _fmt(now + timedelta(hours=2)),
                            "TimeZone": 8,
                        },
                        "Stages": [
                            {"Display": "SR-8", "Value": "SR-8", "Drop": "30031"},
                            {
                                "Display": "SR-5",
                                "Value": "SR-5",
                                "Drop": "搓玉效率0.91",
                            },
                            {
                                "Display": "SSReopen-SR",
                                "Value": "SSReopen-SR",
                                "Drop": "代理1~8关",
                            },
                        ],
                    },
                    "at": {
                        "Activity": {
                            "StageName": "下期活动",
                            "Tip": "",
                            "UtcStartTime": _fmt(now + timedelta(days=2)),
                            "UtcExpireTime": _fmt(now + timedelta(days=12)),
                            "TimeZone": 8,
                        },
                        "Stages": [
                            {"Display": "AT-8", "Value": "AT-8", "Drop": "31015"},
                            {
                                "Display": "SSReopen-AT",
                                "Value": "SSReopen-AT",
                                "Drop": "代理1~8关",
                            },
                        ],
                    },
                }
            }
        },
        ensure_ascii=False,
    )


class GetStageDualViewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config = GlobalConfig()
        self.config._config_item_index["Data"]["StageData"].setValue(
            _stage_data(_now_utc8())
        )
        self.stage = json.loads(self.config.get("Data", "Stage"))["Official"]

    def test_info_entries_are_complete_dicts(self) -> None:
        info = self.stage["Info"]
        self.assertEqual([entry["Value"] for entry in info], ["SR-8", "SR-5"])
        for entry in info:
            self.assertIsInstance(entry, dict)
            self.assertEqual(
                set(entry),
                {"Display", "Value", "RawDrop", "Drop", "DropName", "Activity"},
            )
        self.assertEqual(info[0]["Drop"], "30031")
        # 玉关归一 30012，RawDrop 保留原始文本供搓玉检测
        self.assertEqual(info[1]["Drop"], "30012")
        self.assertEqual(info[1]["RawDrop"], "搓玉效率0.91")

    def test_preview_contains_only_future_activity(self) -> None:
        preview = self.stage["Preview"]
        self.assertEqual([entry["Value"] for entry in preview], ["AT-8"])
        self.assertEqual(preview[0]["Activity"]["StageName"], "下期活动")

    def test_preview_keeps_only_the_nearest_of_several_future_activities(self) -> None:
        # 多期都未开始时只取最近一期：槽位、banner 与文案都是「下期」单数口径
        now = _now_utc8()
        data = json.loads(_stage_data(now))
        data["Official"]["sideStoryStage"]["later"] = {
            "Activity": {
                "StageName": "再下期活动",
                "Tip": "",
                "UtcStartTime": _fmt(now + timedelta(days=8)),
                "UtcExpireTime": _fmt(now + timedelta(days=16)),
                "TimeZone": 8,
            },
            "Stages": [{"Display": "ZZ-8", "Value": "ZZ-8", "Drop": "31015"}],
        }
        self.config._config_item_index["Data"]["StageData"].setValue(
            json.dumps(data, ensure_ascii=False)
        )
        preview = json.loads(self.config.get("Data", "Stage"))["Official"]["Preview"]
        self.assertEqual([entry["Value"] for entry in preview], ["AT-8"])
        self.assertEqual(preview[0]["Activity"]["StageName"], "下期活动")

    def test_ssreopen_stays_out_of_slots(self) -> None:
        for entry in self.stage["Info"] + self.stage["Preview"]:
            self.assertNotIn("SSReopen", entry["Value"])
        self.assertTrue(
            any(option["value"] == "SSReopen-SR" for option in self.stage["ALL"])
        )

    def test_resolver_anchors_on_stage_number(self) -> None:
        info = self.stage["Info"]
        self.assertEqual(_resolve_activity_stage(info, "jade"), ("SR-5", "搓玉 → SR-5"))
        self.assertEqual(
            _resolve_activity_stage(info, "last:1"), ("SR-8", "倒1 → SR-8 · 酯原料")
        )
        code, _ = _resolve_activity_stage(info, "last:3")
        self.assertIsNone(code)
        code, _ = _resolve_activity_stage([], "last:1")
        self.assertIsNone(code)

    def test_resolver_keeps_legacy_index_on_the_same_list_position(self) -> None:
        # 旧版按 MAA 列表位置计号、末位 SR-5 是玉关；如实迁成 pos:N 后按位置取，
        # 与「倒数名次」各按各的口径，旧用户照旧能刷到当时选的关
        self.assertEqual(
            _resolve_activity_stage(self.stage["Info"], "pos:1"),
            ("SR-8", "旧版第1关 → SR-8 · 酯原料"),
        )
        self.assertEqual(
            _resolve_activity_stage(self.stage["Info"], "pos:2"),
            ("SR-5", "旧版第2关 → SR-5 · 搓玉效率0.91"),
        )
        # 越界不回退首关
        code, reason = _resolve_activity_stage(self.stage["Info"], "pos:3")
        self.assertIsNone(code)
        self.assertEqual(reason, "旧版序号第3关超出本期范围")

    def test_new_style_last_intent_is_not_read_as_legacy(self) -> None:
        # 同一期选的「倒2」（2 个材料关 + 玉关时的末位材料关），下期只剩 1 个
        # 材料关时不再被旧值兜底认领去刷玉关，而是如实判越界并提示
        code, reason = _resolve_activity_stage(self.stage["Info"], "last:2")
        self.assertIsNone(code)
        self.assertEqual(reason, "倒数第2关超出本期范围")


class ActivityStageIntentValidatorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActivityStageIntentValidator()

    def test_accepts_valid_intents_and_empty(self) -> None:
        for value in ("", "jade", "last:1", "last:9999", "pos:1", "pos:9999"):
            self.assertTrue(self.validator.validate(value), value)

    def test_normalizes_legacy_index_to_pos_n(self) -> None:
        # 旧序号原义是 MAA 列表位置，如实迁成 pos:N（不是近似成 last:N）
        for raw, expect in ((3, "pos:3"), (2.0, "pos:2"), (" 2 ", "pos:2")):
            self.assertEqual(self.validator.correct(raw), expect, raw)

    def test_neutralizes_invalid_values_including_legacy_mat(self) -> None:
        for raw in (
            "mat:30023",
            "bogus",
            "last:0",
            "last:10000",
            "pos:0",
            0,
            True,
            None,
            "²",
        ):
            self.assertEqual(self.validator.correct(raw), "", repr(raw))


class ActivityStageIntentMigrationTestCase(unittest.IsolatedAsyncioTestCase):
    """旧序号 → 意图的迁移与总开关联动（配置加载期）。"""

    async def _load_task(self, task: dict) -> str:
        config = MaaUserConfig()
        await config.load({"Task": task})
        return config.get("Task", "ActivityStageIntent")

    async def test_default_index_with_switch_off_stays_unassigned(self) -> None:
        # v5.4.0 起旧字段默认 1 且照常落盘：开关没开时它只是默认值，迁成
        # pos:1 会把没碰过活动关的用户全算成已指派
        for task in (
            {"IfActivityFirst": False, "ActivityStageIndex": 1},
            {"ActivityStageIndex": 1},
            {"IfActivityFirst": False, "ActivityStageIndex": "1"},
        ):
            self.assertEqual(await self._load_task(task), "", task)

    async def test_index_migrates_when_switch_is_on(self) -> None:
        self.assertEqual(
            await self._load_task({"IfActivityFirst": True, "ActivityStageIndex": 1}),
            "pos:1",
        )

    async def test_deliberate_index_migrates_even_with_switch_off(self) -> None:
        # 非默认序号是用户真选过的，开关关着也保留，别把选择丢掉
        self.assertEqual(
            await self._load_task({"IfActivityFirst": False, "ActivityStageIndex": 3}),
            "pos:3",
        )

    async def test_existing_intent_is_never_overwritten(self) -> None:
        self.assertEqual(
            await self._load_task(
                {
                    "IfActivityFirst": False,
                    "ActivityStageIndex": 3,
                    "ActivityStageIntent": "last:2",
                }
            ),
            "last:2",
        )


if __name__ == "__main__":
    unittest.main()
