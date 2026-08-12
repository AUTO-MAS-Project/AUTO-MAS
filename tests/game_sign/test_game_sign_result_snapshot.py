import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.config import (
    AppConfig,
    GAME_SIGN_RESULT_FILENAME,
    _load_game_sign_result_snapshot,
    _save_game_sign_result_snapshot,
)


class GameSignResultSnapshotTest(unittest.TestCase):
    def test_current_day_snapshot_is_restored(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        result = {
            "森空岛": [
                {
                    "account_uid": "account-1",
                    "games": [{"game": "明日方舟", "status": "成功"}],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / GAME_SIGN_RESULT_FILENAME
            _save_game_sign_result_snapshot(path, result, result_date=today)

            restored = _load_game_sign_result_snapshot(path, result_date=today)

        self.assertEqual(restored, result)

    def test_previous_day_snapshot_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / GAME_SIGN_RESULT_FILENAME
            _save_game_sign_result_snapshot(
                path,
                {"米游社": [{"account_uid": "account-1"}]},
                result_date="2000-01-01",
            )

            restored = _load_game_sign_result_snapshot(
                path,
                result_date=datetime.now().strftime("%Y-%m-%d"),
            )

        self.assertEqual(restored, {})


class GameSignResultStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_update_persists_and_broadcasts_result(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        formatted = {
            "森空岛": [
                {
                    "account_uid": "account-1",
                    "games": [
                        {"game": "明日方舟", "status": "成功"},
                        {"game": "终末地", "status": "失败"},
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config = object.__new__(AppConfig)
            config.config_path = Path(temp_dir)
            config.ToolsConfig = SimpleNamespace(_game_sign_result_data={})
            config._game_sign_result_date = today
            config.send_websocket_message = AsyncMock()

            await AppConfig.update_game_sign_results(config, formatted)

            payload = json.loads(
                (Path(temp_dir) / GAME_SIGN_RESULT_FILENAME).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(payload, {"date": today, "result": formatted})
        config.send_websocket_message.assert_awaited_once()
        message = config.send_websocket_message.await_args.kwargs
        self.assertEqual(message["id"], "GameSign")
        self.assertEqual(message["type"], "Update")
        self.assertEqual(json.loads(message["data"]["Result"]), formatted)

    async def test_update_discards_previous_day_memory(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        formatted = {"库街区": [{"account_uid": "account-new", "games": []}]}

        with tempfile.TemporaryDirectory() as temp_dir:
            config = object.__new__(AppConfig)
            config.config_path = Path(temp_dir)
            config.ToolsConfig = SimpleNamespace(
                _game_sign_result_data={
                    "米游社": [{"account_uid": "account-old", "games": []}]
                }
            )
            config._game_sign_result_date = "2000-01-01"
            config.send_websocket_message = AsyncMock()

            await AppConfig.update_game_sign_results(config, formatted)

        self.assertEqual(config.ToolsConfig._game_sign_result_data, formatted)
        self.assertEqual(config._game_sign_result_date, today)

    async def test_clear_account_updates_snapshot(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as temp_dir:
            tools_file = Path(temp_dir) / "ToolsConfig.json"
            config = object.__new__(AppConfig)
            config.ToolsConfig = SimpleNamespace(
                file=tools_file,
                _game_sign_result_data={
                    "米游社": [
                        {"account_uid": "account-1"},
                        {"account_uid": "account-2"},
                    ],
                    "森空岛": [{"account_uid": "account-1"}],
                },
            )
            config._game_sign_result_date = today

            AppConfig._clear_game_sign_account_results(config, "account-1")

            payload = json.loads(
                tools_file.with_name(GAME_SIGN_RESULT_FILENAME).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(
            config.ToolsConfig._game_sign_result_data,
            {"米游社": [{"account_uid": "account-2"}]},
        )
        self.assertEqual(payload["result"], config.ToolsConfig._game_sign_result_data)


if __name__ == "__main__":
    unittest.main()
