import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import AppConfig
from app.models.config import GlobalConfig, MaaFWConfig


class MaaFWConfigTest(unittest.TestCase):
    def test_add_script_and_round_trip(self) -> None:
        asyncio.run(self._assert_add_script_and_round_trip())

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
                        "Run": {"RunTimeLimit": 42},
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
