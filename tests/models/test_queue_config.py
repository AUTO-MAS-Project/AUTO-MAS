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

    async def test_legacy_queue_profile_migrates_once_without_losing_items_or_clocks(
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
        common = "2026-11-06T10:05:00+08:00"
        timed = "2026-11-06T10:00:00+08:00"
        for cycle, info, expected_mode, timed_clock in (
            (True, {"StartUpEnabled": True}, "Always", timed),
            (False, {"StartUpEnabled": False}, "Never", None),
            (
                True,
                {"StartUpEnabled": True, "StartUpMode": "DailyFirst"},
                "DailyFirst",
                timed,
            ),
        ):
            with self.subTest(cycle=cycle, mode=expected_mode):
                self.config_path = (
                    Path(self.temporary_directory.name)
                    / f"QueueConfig-{expected_mode}.yaml"
                )
                data = {"LastStartTime": common}
                if timed_clock is not None:
                    data["LastTimedStart"] = timed_clock
                self.write_config(
                    {
                        **payload,
                        "Info": {
                            **info,
                            "CycleEnabled": cycle,
                            "AfterAccomplish": "ShutdownForce",
                            "AfterAccomplishDelay": 0,
                        },
                        "Data": data,
                    }
                )
                config = QueueConfig()
                await activate_config(config, self.config_path)
                expected = [ids[0], ids[2]] if cycle else ids
                self.assertEqual(
                    [str(uid) for uid in config.QueueItem.keys()], expected
                )
                self.assertEqual(config.Info.CycleEnabled, cycle)
                self.assertEqual(config.Info.StartUpMode, expected_mode)
                self.assertEqual(config.Info.AfterAccomplishDelay, 1)
                self.assertIs(config.Info.AfterAccomplish, PowerSignal.SHUTDOWN_FORCE)
                expected_time = (
                    datetime.fromisoformat(timed_clock) if timed_clock else None
                )
                if expected_time is not None:
                    self.assertEqual(config.Data.LastTimedStart, expected_time)
                else:
                    self.assertEqual(config.Data.LastTimedStart.year, 2000)
                self.assertEqual(config.Data.LastStartupTime.year, 2000)
                self.assertIsNone(config.Cycle.LastRunAt)
                persisted = self.read_config()
                self.assertEqual(
                    [item["uid"] for item in persisted["QueueItem"]["order"]], expected
                )
                self.assertEqual(set(persisted["QueueItem"]["data"]), set(expected))
                self.assertEqual(persisted["Info"]["StartUpMode"], expected_mode)
                self.assertNotIn("StartUpEnabled", persisted["Info"])
                self.assertNotIn("LastStartTime", persisted["Data"])
                self.assertNotIn("LastStartTime", config.Data.model_dump())
                self.assertIn("LastTimedStart", persisted["Data"])
                self.assertEqual(persisted["Info"]["AfterAccomplish"], "ShutdownForce")
                self.assertEqual(persisted["Info"]["AfterAccomplishDelay"], 1)
                # 再加载已迁移文件不应继续删除条目。
                reloaded = QueueConfig()
                await activate_config(reloaded, self.config_path)
                self.assertEqual(
                    [str(uid) for uid in reloaded.QueueItem.keys()], expected
                )
                self.assertEqual(reloaded.Info.StartUpMode, expected_mode)
                self.assertEqual(
                    reloaded.Data.LastTimedStart, config.Data.LastTimedStart
                )
                self.assertEqual(reloaded.Info.AfterAccomplishDelay, 1)
        from app.api.queue import QueueUpdateIn

        with self.assertRaises(ValidationError):
            QueueUpdateIn.model_validate(
                {
                    "queueId": "queue",
                    "data": {"Info": {"AfterAccomplishDelay": 0}},
                }
            )
