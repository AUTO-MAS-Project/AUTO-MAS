# getStage 双视图与活动关意图的回归测试。
# 背景：_stage_drop_entry 曾因缩进错误让材质关/玉关隐式返回 None，
# 且当时全仓无 getStage 覆盖，靠人工探针才定位——本文件锁住这条链路。

import json
import unittest
from datetime import datetime, timedelta

from app.models.config import ActivityStageIntentValidator, GlobalConfig
from app.task.MAA.AutoProxy import _resolve_activity_stage


def _fmt(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S")


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
                            {"Display": "SR-5", "Value": "SR-5", "Drop": "搓玉效率0.91"},
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
            _stage_data(datetime.now())
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
        now = datetime.now()
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
            any(
                option["value"] == "SSReopen-SR"
                for option in self.stage["ALL"]
            )
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

    def test_resolver_keeps_legacy_jade_index_farming_jade(self) -> None:
        # 旧版按 MAA 列表位置计号，末位 SR-5 是玉关；迁移出的 last:2 越界，
        # 该位置确为玉关时按搓玉解析，旧序号用户不会整期不注入
        self.assertEqual(
            _resolve_activity_stage(self.stage["Info"], "last:2"),
            ("SR-5", "搓玉 → SR-5（旧序号迁移）"),
        )
        # 末位不是玉关时保持越界，不复活旧版位置回退
        plain = [
            {"Value": "PA-8", "RawDrop": "30063", "DropName": "晶体元件"},
            {"Value": "PA-7", "RawDrop": "31015", "DropName": "聚酸酯组"},
        ]
        code, _ = _resolve_activity_stage(plain, "last:3")
        self.assertIsNone(code)


class ActivityStageIntentValidatorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActivityStageIntentValidator()

    def test_accepts_valid_intents_and_empty(self) -> None:
        for value in ("", "jade", "last:1", "last:9999"):
            self.assertTrue(self.validator.validate(value), value)

    def test_normalizes_legacy_index_to_last_n(self) -> None:
        for raw, expect in ((3, "last:3"), (2.0, "last:2"), (" 2 ", "last:2")):
            self.assertEqual(self.validator.correct(raw), expect, raw)

    def test_neutralizes_invalid_values_including_legacy_mat(self) -> None:
        for raw in ("mat:30023", "bogus", "last:0", "last:10000", 0, True, None, "²"):
            self.assertEqual(self.validator.correct(raw), "", repr(raw))


if __name__ == "__main__":
    unittest.main()
