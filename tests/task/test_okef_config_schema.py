import json
import sys
import tempfile
import unittest
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_SOURCE = _WORKSPACE_ROOT / "plugins" / "ok_script_adapter" / "src"
if str(_PLUGIN_SOURCE) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SOURCE))

from ok_script_adapter.okef_config_schema import (
    build_fields_for_config,
    get_config_info_from_dir,
)


class OkefConfigSchemaTest(unittest.TestCase):
    def test_daily_fields_keep_account_settings_and_gift_target_select(self) -> None:
        fields = build_fields_for_config(
            "DailyTask.json",
            {
                "多账户模式": True,
                "多账户独立配置": False,
                "账号列表": "账号 A\n账号 B",
                "⭐买物资": True,
                "优先送礼对象": "庄方宜",
                "配置选择": "⭐⭐⭐ 默认",
            },
            {},
        )
        fields_by_name = {field["name"]: field for field in fields}

        self.assertNotIn("配置选择", fields_by_name)
        self.assertEqual(fields_by_name["多账户模式"]["section"], "多账户模式")
        self.assertEqual(fields_by_name["账号列表"]["section"], "多账户模式")
        self.assertEqual(fields_by_name["账号列表"]["type"], "textarea")
        self.assertLess(
            fields_by_name["⭐买物资"]["sectionPriority"],
            fields_by_name["多账户模式"]["sectionPriority"],
        )

        gift_target = fields_by_name["优先送礼对象"]
        self.assertEqual(gift_target["type"], "select")
        self.assertEqual(gift_target["section"], "⭐送礼")
        self.assertIn("庄方宜", gift_target["options"])
        self.assertIn("秋栗", gift_target["options"])

    def test_config_list_uses_native_names_and_skips_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "BattleTask.json").write_text(
                json.dumps({"⭐刷体力": True}, ensure_ascii=False),
                encoding="utf-8",
            )
            (config_dir / "DemoDrawTask.json").write_text(
                json.dumps({"最多重开次数": 2}, ensure_ascii=False),
                encoding="utf-8",
            )
            (config_dir / "YingTuoTask.json").write_text("{}", encoding="utf-8")

            configs = get_config_info_from_dir(config_dir)

        config_names = {item["filename"]: item["displayName"] for item in configs}
        self.assertEqual(config_names["BattleTask.json"], "刷体力")
        self.assertEqual(config_names["DemoDrawTask.json"], "演算抽牌")
        self.assertNotIn("YingTuoTask.json", config_names)
