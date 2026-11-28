import unittest

from app.models.config import GlobalConfig


class HistoryVideoStorageLimitMigrationTest(unittest.TestCase):
    def test_legacy_replay_limit_populates_history_limit(self) -> None:
        setting = GlobalConfig.model_validate(
            {"Replay": {"VideoStorageLimitMiB": 2048}}
        )

        self.assertEqual(setting.History.VideoStorageLimitMiB, 2048)
        self.assertEqual(setting.Replay.VideoStorageLimitMiB, 2048)
        self.assertEqual(
            setting.model_dump(context={"audience": "persist"})["Replay"][
                "VideoStorageLimitMiB"
            ],
            2048,
        )

    def test_explicit_history_limit_takes_precedence(self) -> None:
        setting = GlobalConfig.model_validate(
            {
                "History": {"VideoStorageLimitMiB": 4096},
                "Replay": {"VideoStorageLimitMiB": 2048},
            }
        )

        self.assertEqual(setting.History.VideoStorageLimitMiB, 4096)
        self.assertEqual(setting.Replay.VideoStorageLimitMiB, 2048)
