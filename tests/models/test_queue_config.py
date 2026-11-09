import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError

from app.config import ConfigCollection, config_manager
from app.models.config import GeneralConfig, QueueConfig
from app.utils import io as _utils_io
from app.utils.contracts.power import PowerSignal
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

    async def test_legacy_disabled_items_are_removed_only_from_cycle_queues(
        self,
    ) -> None:
        ids = [str(uuid4()) for _ in range(4)]
        scripts = ConfigCollection[GeneralConfig].build([GeneralConfig])
        await scripts.activate()
        references = patch.dict(config_manager._collections, {"ScriptConfig": scripts})
        references.start()
        self.addCleanup(references.stop)
        payload = {
            "QueueItem": {
                "order": [{"uid": uid, "type": "QueueItem"} for uid in ids],
                "data": {
                    ids[0]: {"Info": {"ScriptId": "-"}, "Schedule": {"Enabled": True}},
                    ids[1]: {"Info": {"ScriptId": "-"}, "Schedule": {"Enabled": False}},
                    ids[2]: {
                        "Info": {"ScriptId": "-"},
                        "Schedule": {"Days": ["Monday"]},
                    },
                    ids[3]: {"Info": {"ScriptId": "-"}, "Schedule": {"Enabled": False}},
                },
            }
        }
        for cycle in (True, False):
            with self.subTest(cycle=cycle):
                self.config_path = (
                    Path(self.temporary_directory.name) / f"QueueConfig-{cycle}.yaml"
                )
                self.write_config({**payload, "Info": {"CycleEnabled": cycle}})
                config = QueueConfig()
                await activate_config(config, self.config_path)
                expected = [ids[0], ids[2]] if cycle else ids
                self.assertEqual(
                    [str(uid) for uid in config.QueueItem.keys()], expected
                )
                self.assertEqual(config.Info.CycleEnabled, cycle)
                persisted = self.read_config()["QueueItem"]
                self.assertEqual([item["uid"] for item in persisted["order"]], expected)
                self.assertEqual(set(persisted["data"]), set(expected))
                # 再加载已迁移文件不应继续删除条目。
                reloaded = QueueConfig()
                await activate_config(reloaded, self.config_path)
                self.assertEqual(
                    [str(uid) for uid in reloaded.QueueItem.keys()], expected
                )

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

    async def test_load_discards_removed_clock_and_preserves_timed_clock(self) -> None:
        common = "2026-11-06T10:05:00+08:00"
        timed = "2026-11-06T10:00:00+08:00"
        self.write_config({"Data": {"LastStartTime": common, "LastTimedStart": timed}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Data.LastTimedStart, datetime.fromisoformat(timed))
        persisted = self.read_config()["Data"]
        self.assertIn("LastTimedStart", persisted)
        self.assertNotIn("LastStartTime", persisted)
        self.assertNotIn("LastStartTime", config.Data.model_dump())

    async def test_load_does_not_infer_timed_success_from_common_clock(self) -> None:
        self.write_config({"Data": {"LastStartTime": "2026-11-06T10:05:00+08:00"}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Data.LastTimedStart.year, 2000)
        self.assertEqual(config.Data.LastStartupTime.year, 2000)
        self.assertIsNone(config.Cycle.LastRunAt)

    async def test_load_power_action_as_enum_and_persists_original_value(self) -> None:
        self.write_config({"Info": {"AfterAccomplish": "ShutdownForce"}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertIs(config.Info.AfterAccomplish, PowerSignal.SHUTDOWN_FORCE)
        self.assertEqual(self.read_config()["Info"]["AfterAccomplish"], "ShutdownForce")

    async def test_zero_queue_countdown_migrates_to_one_minute_but_updates_reject_zero(
        self,
    ) -> None:
        from app.api.queue import QueueUpdateIn

        self.write_config({"Info": {"AfterAccomplishDelay": 0}})
        config = QueueConfig()
        await activate_config(config, self.config_path)
        self.assertEqual(config.Info.AfterAccomplishDelay, 1)
        self.assertEqual(self.read_config()["Info"]["AfterAccomplishDelay"], 1)
        with self.assertRaises(ValidationError):
            QueueUpdateIn.model_validate(
                {
                    "queueId": "queue",
                    "data": {"Info": {"AfterAccomplishDelay": 0}},
                }
            )
