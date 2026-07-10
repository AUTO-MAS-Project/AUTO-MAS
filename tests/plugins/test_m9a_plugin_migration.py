import json
import sys
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
for plugin_name in (
    "automas_maafw_agent_env",
    "automas_maafw_interface",
    "automas_maafw_project_update",
    "automas_maafw_runner",
    "automas_script_maafw",
    "automas_script_maafw_pack_m9a",
):
    sys.path.insert(0, str(REPO_ROOT / "plugins" / plugin_name / "src"))

from automas_script_maafw.adapter import MaaFWAdapterHooks
from automas_script_maafw_pack_m9a.migration import migrate_legacy_m9a_config
from automas_script_maafw_pack_m9a.schema import M9A_SCRIPT_GROUPS, M9A_USER_GROUPS
from app.models.config import M9AConfig
from app.plugins import ScriptAdapterDefinition


class M9APluginMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_config_migrates_to_new_maafw_runner_shape(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            (project_path / "interface.json").write_text(
                json.dumps(_interface_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            user_id = uuid.uuid4()
            legacy = M9AConfig()
            await legacy.load(
                {
                    "Info": {"Name": "旧 M9A", "Path": str(project_path)},
                    "Emulator": {"Id": "-", "Index": "-"},
                    "Run": {
                        "ProxyTimesLimit": 2,
                        "RunTimesLimit": 4,
                        "RunTimeLimit": 20,
                        "IfAutoUpdateAfterQueue": True,
                        "IfPsychubeDailyOnce": True,
                        "IfSleepDreamMonthlyOnce": True,
                    },
                    "SubConfigsInfo": {
                        "UserData": {
                            "instances": [
                                {"uid": str(user_id), "type": "M9AUserConfig"}
                            ],
                            str(user_id): {
                                "Info": {
                                    "Name": "账号一",
                                    "Status": True,
                                    "RemainedDay": -1,
                                    "Resource": "官服",
                                    "Account": "account-1",
                                },
                                "Task": {
                                    "Queue": json.dumps(
                                        [
                                            {
                                                "name": "每日心相（意志解析）",
                                                "options": [
                                                    {"name": "模式", "index": 1}
                                                ],
                                            },
                                            {"name": "领取奖励", "options": []},
                                            {"name": "关闭游戏", "options": []},
                                        ],
                                        ensure_ascii=False,
                                    )
                                },
                                "Data": {
                                    "LastProxyDate": "2026-07-10",
                                    "ProxyTimes": 1,
                                    "IfPassCheck": True,
                                    "LastPsychubeDate": "2026-07-10",
                                    "LastLimboMonth": "2026-07",
                                    "LastLucidscapeMonth": "2026-06",
                                },
                            },
                        }
                    },
                }
            )
            provider = _build_provider()

            migrated = await migrate_legacy_m9a_config(legacy, provider)

        self.assertIsInstance(migrated, provider.script_config_class)
        self.assertEqual(migrated.get("Info", "Name"), "旧 M9A")
        self.assertTrue(migrated.get("Update", "IfAutoUpdate"))
        self.assertEqual(
            json.loads(migrated.get("Run", "DailyOnceTasks")),
            ["每日心相（意志解析）"],
        )
        self.assertEqual(
            json.loads(migrated.get("Run", "MonthlyOnceTasks")),
            ["自动深眠", "自动醒梦"],
        )

        self.assertEqual(list(migrated.UserData.keys()), [user_id])
        user = migrated.UserData[user_id]
        self.assertEqual(user.get("Info", "Resource"), "official")
        self.assertEqual(user.get("Info", "Controller"), "adb")
        snapshot = json.loads(user.get("Task", "TaskSnapshot"))
        self.assertEqual(
            snapshot["taskOrder"][:2],
            ["每日心相（意志解析）", "领取奖励"],
        )
        self.assertTrue(snapshot["taskChecked"]["每日心相（意志解析）"])
        self.assertFalse(snapshot["taskChecked"]["关闭游戏"])
        self.assertEqual(
            snapshot["taskOptions"]["每日心相（意志解析）"]["模式"],
            "困难",
        )
        period_records = json.loads(user.get("Data", "PeriodTaskRecords"))
        self.assertEqual(
            period_records["daily"]["每日心相（意志解析）"],
            "2026-07-10",
        )
        self.assertEqual(period_records["monthly"]["自动深眠"], "2026-07")
        self.assertEqual(period_records["monthly"]["自动醒梦"], "2026-06")


def _build_provider():
    return ScriptAdapterDefinition(
        type_key="M9A",
        display_name="M9A",
        hooks_factory=MaaFWAdapterHooks,
        script_groups=M9A_SCRIPT_GROUPS,
        user_groups=M9A_USER_GROUPS,
        script_class_name="M9APluginConfig",
        user_class_name="M9APluginUserConfig",
        module="automas_script_maafw.schema",
        legacy_config_class_name="M9AConfig",
        legacy_user_config_class_name="M9AUserConfig",
    ).build_provider()


def _interface_payload() -> dict:
    return {
        "interface_version": 2,
        "name": "m9a",
        "label": "M9A",
        "controller": [{"name": "adb", "type": "Adb"}],
        "resource": [
            {
                "name": "official",
                "label": "官服",
                "path": ["resource"],
                "controller": ["adb"],
            }
        ],
        "task": [
            {
                "name": "每日心相（意志解析）",
                "entry": "Psychube",
                "option": ["模式"],
            },
            {"name": "自动深眠", "entry": "Limbo"},
            {"name": "自动醒梦", "entry": "Lucidscape"},
            {"name": "领取奖励", "entry": "Award"},
            {"name": "关闭游戏", "entry": "Close1999"},
        ],
        "option": {
            "模式": {
                "type": "select",
                "cases": [{"name": "普通"}, {"name": "困难"}],
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
