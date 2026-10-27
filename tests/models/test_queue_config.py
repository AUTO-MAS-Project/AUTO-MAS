import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models.config import QueueConfig
from app.utils import io as _utils_io
from tests.config_support import activate_config


class QueueConfigStartupModeMigrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "QueueConfig.yaml"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_config(self, data: dict) -> None:
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def read_config(self) -> dict:
        return _utils_io.read_dict_file(self.config_path)

    async def test_load_migrates_enabled_legacy_startup_setting(self) -> None:
        self.write_config({"Info": {"StartUpEnabled": True}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Info.StartUpMode, "Always")
        persisted_info = self.read_config()["Info"]
        self.assertEqual(persisted_info["StartUpMode"], "Always")
        self.assertNotIn("StartUpEnabled", persisted_info)

    async def test_load_migrates_disabled_legacy_startup_setting(self) -> None:
        self.write_config({"Info": {"StartUpEnabled": False}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Info.StartUpMode, "Never")
        persisted_info = self.read_config()["Info"]
        self.assertEqual(persisted_info["StartUpMode"], "Never")
        self.assertNotIn("StartUpEnabled", persisted_info)

    async def test_load_prefers_current_startup_mode_over_legacy_setting(self) -> None:
        self.write_config(
            {"Info": {"StartUpEnabled": True, "StartUpMode": "DailyFirst"}}
        )
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Info.StartUpMode, "DailyFirst")
        persisted_info = self.read_config()["Info"]
        self.assertEqual(persisted_info["StartUpMode"], "DailyFirst")
        self.assertNotIn("StartUpEnabled", persisted_info)
