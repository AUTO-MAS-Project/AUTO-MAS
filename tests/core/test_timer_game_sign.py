import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.timer import _MainTimer


class GameSignTimerTest(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_sign_does_not_read_legacy_window_fields(self) -> None:
        timer = _MainTimer()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            "Enabled": True,
            "LastSignDate": "2000-01-01",
            "MiyousheToken": "miyoushe-token",
            "KuroToken": "",
            "SklandToken": "",
        }[key]
        execute = AsyncMock()

        with patch("app.core.timer.Config") as config, patch.object(
            timer, "_execute_game_sign", new=execute
        ):
            config.ToolsConfig.get.side_effect = lambda group, key: {
                "Enabled": True,
                "ScheduledRun": True,
            }[key]
            config.ToolsConfig.GameSign_Accounts = {"account-1": account}

            await timer.check_game_sign(check_time=datetime(2026, 7, 29, 8, 0))

        execute.assert_awaited_once_with()
        requested_keys = [call.args[1] for call in config.ToolsConfig.get.call_args_list]
        self.assertNotIn("WindowStart", requested_keys)
        self.assertNotIn("WindowEnd", requested_keys)
        self.assertNotIn("ScheduledTime", requested_keys)

    async def test_scheduled_sign_ignores_accounts_without_credentials(self) -> None:
        timer = _MainTimer()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            "Enabled": True,
            "LastSignDate": "2000-01-01",
            "MiyousheToken": "",
            "KuroToken": "",
            "SklandToken": "",
        }[key]
        execute = AsyncMock()

        with patch("app.core.timer.Config") as config, patch.object(
            timer, "_execute_game_sign", new=execute
        ):
            config.ToolsConfig.get.side_effect = lambda group, key: {
                "Enabled": True,
                "ScheduledRun": True,
            }[key]
            config.ToolsConfig.GameSign_Accounts = {"account-1": account}

            await timer.check_game_sign(check_time=datetime(2026, 7, 29, 8, 0))

        execute.assert_not_awaited()

    async def test_empty_results_do_not_mark_pending_account_complete(self) -> None:
        timer = _MainTimer()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            "Enabled": True,
            "LastSignDate": "2000-01-01",
            "MiyousheToken": "miyoushe-token",
            "KuroToken": "",
            "SklandToken": "",
        }[key]

        with patch("app.core.timer.Config") as config, patch(
            "app.tools.game_sign.run_all_sign_in", new=AsyncMock(return_value=[])
        ):
            config.ToolsConfig.GameSign_Accounts = {"account-1": account}
            config.ToolsConfig.get.return_value = False
            config.ToolsConfig.set = AsyncMock()

            await timer._execute_game_sign()

        config.ToolsConfig.set.assert_not_awaited()

    async def test_startup_sign_is_dispatched_once(self) -> None:
        timer = _MainTimer()
        started = asyncio.Event()
        release = asyncio.Event()

        async def sign_for_startup() -> None:
            started.set()
            await release.wait()

        with patch("app.core.timer.Config") as config, patch.object(
            timer,
            "try_game_sign_for_task",
            new=AsyncMock(side_effect=sign_for_startup),
        ) as sign_for_task:
            config.ToolsConfig.get.side_effect = lambda group, key: {
                "Enabled": True,
                "RunOnStartup": True,
                "AutoStart": False,
            }[key]

            timer.schedule_game_sign_for_startup()
            task = timer.game_sign_task
            self.assertIsNotNone(task)
            await started.wait()

            timer.schedule_game_sign_for_startup()
            sign_for_task.assert_awaited_once_with()

            release.set()
            await task
            await asyncio.sleep(0)

        self.assertIsNone(timer.game_sign_task)

    async def test_legacy_auto_start_does_not_dispatch_startup_sign(self) -> None:
        timer = _MainTimer()

        with patch("app.core.timer.Config") as config, patch.object(
            timer, "try_game_sign_for_task", new_callable=AsyncMock
        ) as sign_for_task:
            config.ToolsConfig.get.side_effect = lambda group, key: {
                "Enabled": True,
                "RunOnStartup": False,
                "AutoStart": True,
            }[key]

            timer.schedule_game_sign_for_startup()

        sign_for_task.assert_not_awaited()
        self.assertIsNone(timer.game_sign_task)

    async def test_background_check_is_guarded_without_blocking_dispatch(self) -> None:
        timer = _MainTimer()
        started = asyncio.Event()
        release = asyncio.Event()
        check_time = datetime(2026, 7, 29, 8, 0, 0)

        async def check(*, check_time: datetime | None = None) -> None:
            started.set()
            await release.wait()

        with patch("app.core.timer.Config") as config, patch(
            "app.core.timer.datetime"
        ) as mocked_datetime, patch.object(
            timer,
            "check_game_sign",
            new=AsyncMock(side_effect=check),
        ) as check_game_sign:
            config.ToolsConfig.get.return_value = True
            mocked_datetime.now.return_value = check_time

            timer._schedule_game_sign_check()
            task = timer.game_sign_task
            self.assertIsNotNone(task)
            await started.wait()

            timer._schedule_game_sign_check()
            check_game_sign.assert_awaited_once_with(check_time=check_time)

            release.set()
            await task
            await asyncio.sleep(0)

        self.assertIsNone(timer.game_sign_task)

    async def test_non_boundary_second_dispatches_once_per_minute(self) -> None:
        timer = _MainTimer()
        check_time = datetime(2026, 7, 29, 8, 0, 1)

        with patch("app.core.timer.Config") as config, patch(
            "app.core.timer.datetime"
        ) as mocked_datetime, patch.object(
            timer,
            "check_game_sign",
            new_callable=AsyncMock,
        ) as check_game_sign:
            config.ToolsConfig.get.return_value = True
            mocked_datetime.now.return_value = check_time

            timer._schedule_game_sign_check()
            task = timer.game_sign_task
            self.assertIsNotNone(task)
            await task
            timer._schedule_game_sign_check()

        check_game_sign.assert_awaited_once_with(check_time=check_time)
        self.assertIsNone(timer.game_sign_task)

    async def test_task_trigger_uses_same_background_guard(self) -> None:
        timer = _MainTimer()
        started = asyncio.Event()
        release = asyncio.Event()

        async def sign_for_task() -> None:
            started.set()
            await release.wait()

        with patch("app.core.timer.Config") as config, patch.object(
            timer,
            "try_game_sign_for_task",
            new=AsyncMock(side_effect=sign_for_task),
        ) as try_game_sign:
            config.ToolsConfig.get.return_value = True
            timer.schedule_game_sign_for_task()
            task = timer.game_sign_task
            self.assertIsNotNone(task)
            await started.wait()

            timer.schedule_game_sign_for_task()
            try_game_sign.assert_awaited_once_with()

            release.set()
            await task
            await asyncio.sleep(0)

        self.assertIsNone(timer.game_sign_task)


if __name__ == "__main__":
    unittest.main()
