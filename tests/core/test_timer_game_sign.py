import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.timer import _MainTimer


class GameSignTimerTest(unittest.IsolatedAsyncioTestCase):
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

        async def sign_for_startup(*, source: str) -> None:
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
            sign_for_task.assert_awaited_once_with(source="startup")

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

if __name__ == "__main__":
    unittest.main()
