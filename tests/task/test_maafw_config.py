import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import AppConfig
from app.models.config import GlobalConfig, MaaFWConfig, MaaFWUserConfig


def _item_count(config) -> int:
    return sum(len(names) for names in config._config_item_index.values())


class MaaFWConfigTest(unittest.TestCase):
    def test_add_script_and_round_trip(self) -> None:
        asyncio.run(self._assert_add_script_and_round_trip())

    def test_recycled_model_inventory(self) -> None:
        """回收后的 MaaFW 配置模型字段分组与数量。"""

        script = MaaFWConfig()
        script_groups = {
            group: len(names)
            for group, names in script._config_item_index.items()
        }
        self.assertEqual(
            script_groups,
            {
                "Info": 5,
                "Emulator": 2,
                "Device": 11,
                "Game": 9,
                "Update": 7,
                "Managed": 9,
                "ManagedRuntime": 5,
                "ManagedRemote": 7,
                "Run": 7,
                "Selection": 3,
            },
        )
        # 61 个回收字段 + Run.Engine + Selection.{Controller,Resource,Tasks}
        self.assertEqual(_item_count(script), 65)
        self.assertIn("Engine", script._config_item_index["Run"])
        self.assertIn("DailyOnceTasks", script._config_item_index["Run"])
        self.assertIn("WeeklyOnceTasks", script._config_item_index["Run"])
        self.assertIn("MonthlyOnceTasks", script._config_item_index["Run"])
        self.assertTrue(hasattr(script, "UserData"))

        user = MaaFWUserConfig()
        user_groups = {
            group: len(names) for group, names in user._config_item_index.items()
        }
        self.assertEqual(
            user_groups,
            {
                "Info": 13,
                "Task": 2,
                "Device": 4,
                "Data": 5,
                "Notify": 6,
            },
        )
        self.assertEqual(_item_count(user), 30)
        self.assertIn("SelectedPreset", user._config_item_index["Task"])
        self.assertIn("Account", user._config_item_index["Info"])
        self.assertIn("Password", user._config_item_index["Info"])

    def test_add_user_creates_maafw_user_config(self) -> None:
        asyncio.run(self._assert_add_user_creates_maafw_user_config())

    async def _assert_add_user_creates_maafw_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as manager_dir:
            manager_root = Path(manager_dir)
            with patch("app.core.config.Path.cwd", return_value=manager_root):
                manager = AppConfig()
                script_uid, _ = await manager.add_script("MaaFW")
                user_uid, user_config = await manager.add_user(str(script_uid))

                self.assertIsInstance(user_config, MaaFWUserConfig)
                self.assertEqual(user_config.get("Info", "Name"), "新用户")

                index, _ = await manager.get_user(str(script_uid), None)
                self.assertEqual(
                    [(entry["uid"], entry["type"]) for entry in index],
                    [(str(user_uid), "MaaFWUserConfig")],
                )

    async def _assert_add_script_and_round_trip(self) -> None:
        with (
            tempfile.TemporaryDirectory() as manager_dir,
            tempfile.TemporaryDirectory() as project_dir,
        ):
            manager_root = Path(manager_dir)
            project_root = Path(project_dir)

            with patch("app.core.config.Path.cwd", return_value=manager_root):
                manager = AppConfig()
                script_uid, script = await manager.add_script("MaaFW")

                self.assertIsInstance(script, MaaFWConfig)
                self.assertEqual(script.get("Info", "Name"), "新 MaaFW 脚本")
                self.assertEqual(script.get("Run", "Engine"), "external")
                self.assertEqual(script.get("Run", "RunTimeLimit"), 30)

                await script.update(
                    {
                        "Info": {
                            "Name": "本地 MaaFW 项目",
                            "Path": str(project_root),
                        },
                        "Game": {"LaunchMode": "DirectExe"},
                        "Update": {"Source": "MirrorChyan"},
                        "Run": {
                            "RunTimeLimit": 42,
                            "DailyOnceTasks": json.dumps(
                                ["每日签到"], ensure_ascii=False
                            ),
                        },
                        "Selection": {
                            "Controller": json.dumps(["安卓端"], ensure_ascii=False),
                            "Resource": json.dumps(["简中"], ensure_ascii=False),
                            "Tasks": json.dumps(["启动游戏"], ensure_ascii=False),
                        },
                    }
                )
                persisted = await manager.ScriptConfig.toDict(if_decrypt=False)

            restored = GlobalConfig()
            await restored.ScriptConfig.load(persisted)
            restored_script = restored.ScriptConfig[script_uid]

            self.assertIsInstance(restored_script, MaaFWConfig)
            self.assertEqual(restored_script.get("Info", "Name"), "本地 MaaFW 项目")
            self.assertEqual(
                Path(restored_script.get("Info", "Path")), project_root
            )
            self.assertEqual(restored_script.get("Run", "Engine"), "external")
            self.assertEqual(restored_script.get("Run", "RunTimeLimit"), 42)
            self.assertEqual(restored_script.get("Game", "LaunchMode"), "DirectExe")
            self.assertEqual(restored_script.get("Update", "Source"), "MirrorChyan")
            self.assertEqual(
                json.loads(restored_script.get("Run", "DailyOnceTasks")), ["每日签到"]
            )
            self.assertEqual(
                json.loads(restored_script.get("Selection", "Controller")), ["安卓端"]
            )
            self.assertEqual(
                json.loads(restored_script.get("Selection", "Resource")), ["简中"]
            )
            self.assertEqual(
                json.loads(restored_script.get("Selection", "Tasks")), ["启动游戏"]
            )


if __name__ == "__main__":
    unittest.main()
