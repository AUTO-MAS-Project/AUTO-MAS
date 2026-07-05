import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import AppConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig


class OkwwPluginMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_migrates_legacy_okww_config_to_plugin_storage(self) -> None:
        app_config = AppConfig()

        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = str(Path(temp_dir) / "okww")
            normalized_root_path = Path(root_path).resolve().as_posix()
            game_path = str(Path(temp_dir) / "Client.exe")
            await app_config.ScriptConfig.connect(Path(temp_dir) / "ScriptConfig.json")
            script_uid, script_config = await app_config.ScriptConfig.add(OkwwConfig)
            await script_config.set("Info", "Name", "旧 Okww")
            await script_config.set("Info", "RootPath", root_path)
            await script_config.set("Game", "Enabled", True)
            await script_config.set("Game", "LaunchBeforeTask", True)
            await script_config.set("Game", "Path", game_path)
            await script_config.set("Run", "RunTimesLimit", 3)

            user_uid, user_config = await script_config.UserData.add(OkwwUserConfig)
            await user_config.set("Info", "Name", "账号 A")
            await user_config.set("Info", "Id", "user-a")
            await user_config.set("Task", "TaskIndex", 5)
            await user_config.set("Data", "LastProxyStatus", "成功")

            await app_config._migrate_okww_scripts_to_plugin_storage()

            migrated_script = app_config.ScriptConfig[script_uid]
            self.assertIsInstance(migrated_script, PluginScriptConfig)
            self.assertEqual(migrated_script.get("Meta", "PluginTypeKey"), "Okww")
            self.assertEqual(migrated_script.UserData.order, [user_uid])

            script_payload = json.loads(migrated_script.get("PluginData", "Config"))
            self.assertEqual(script_payload["Info"]["Name"], "旧 Okww")
            self.assertEqual(script_payload["Info"]["RootPath"], normalized_root_path)
            self.assertTrue(script_payload["Game"]["Enabled"])
            self.assertNotIn("LaunchBeforeTask", script_payload["Game"])
            self.assertEqual(script_payload["Run"]["RunTimesLimit"], 3)

            migrated_user = migrated_script.UserData[user_uid]
            self.assertIsInstance(migrated_user, PluginUserConfig)
            self.assertEqual(migrated_user.get("Meta", "PluginTypeKey"), "Okww")

            user_payload = json.loads(migrated_user.get("PluginData", "Config"))
            self.assertEqual(user_payload["Info"]["Name"], "账号 A")
            self.assertEqual(user_payload["Info"]["Id"], "user-a")
            self.assertEqual(user_payload["Task"]["TaskIndex"], 5)
            self.assertEqual(user_payload["Data"]["LastProxyStatus"], "成功")


if __name__ == "__main__":
    unittest.main()
