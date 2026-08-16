import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.game_sign import (
    _all_enabled_platforms_signed,
    _run_all_sign_in,
    format_sign_results,
)
from app.utils.constants import UTC8


class GameSignCompletionTest(unittest.TestCase):
    def test_partial_platform_failure_does_not_complete_account(self) -> None:
        results = [
            {
                "account_uid": "account-1",
                "platform": "森空岛",
                "status": "成功",
            },
            {
                "account_uid": "account-1",
                "platform": "森空岛",
                "status": "失败",
            },
        ]

        self.assertFalse(
            _all_enabled_platforms_signed(
                results,
                account_uid="account-1",
                enabled_platforms=["森空岛"],
            )
        )

    def test_missing_platform_result_does_not_complete_account(self) -> None:
        results = [
            {
                "account_uid": "account-1",
                "platform": "米游社",
                "status": "已签到",
            }
        ]

        self.assertFalse(
            _all_enabled_platforms_signed(
                results,
                account_uid="account-1",
                enabled_platforms=["米游社", "库街区"],
            )
        )

    def test_all_results_complete_account(self) -> None:
        results = [
            {
                "account_uid": "account-1",
                "platform": "米游社",
                "status": "成功",
            },
            {
                "account_uid": "account-1",
                "platform": "米游社",
                "status": "已签到",
            },
            {
                "account_uid": "account-1",
                "platform": "库街区",
                "status": "成功",
            },
        ]

        self.assertTrue(
            _all_enabled_platforms_signed(
                results,
                account_uid="account-1",
                enabled_platforms=["米游社", "库街区"],
            )
        )


class GameSignCredentialReadOnlyTest(unittest.IsolatedAsyncioTestCase):
    async def test_sign_in_does_not_update_credentials(self) -> None:
        account = MagicMock()
        values = {
            ("GameSignAccount", "Name"): "测试用户",
            ("GameSignAccount", "Enabled"): True,
            ("GameSignAccount", "LastSignDate"): "2000-01-01",
            ("GameSignAccount", "MiyousheToken"): "",
            ("GameSignAccount", "KuroToken"): "",
            ("GameSignAccount", "SklandToken"): "skland-token",
        }
        account.get.side_effect = lambda group, name: values[(group, name)]
        account.set = AsyncMock()
        config = SimpleNamespace(
            ToolsConfig=SimpleNamespace(GameSign_Accounts={"account-1": account})
        )
        skland_result = {
            "arknights": {
                "成功": ["测试角色/测试角色(10001)"],
                "重复": [],
                "失败": [],
                "总计": 1,
            },
            "endfield": {"成功": [], "重复": [], "失败": [], "总计": 0},
        }

        with (
            patch("app.tools.game_sign.Config", config),
            patch(
                "app.tools.game_sign._check_system_time",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.tools.skland.skland_sign_in",
                new=AsyncMock(return_value=skland_result),
            ),
        ):
            await _run_all_sign_in(force=True)

        account.set.assert_awaited_once()
        self.assertEqual(
            account.set.await_args.args[:2],
            ("GameSignAccount", "LastSignDate"),
        )


class GameSignAutomaticAttemptTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make_account() -> MagicMock:
        account = MagicMock()
        values = {
            ("GameSignAccount", "Name"): "测试用户",
            ("GameSignAccount", "Enabled"): True,
            ("GameSignAccount", "LastSignDate"): "2000-01-01",
            ("GameSignAccount", "MiyousheToken"): "",
            ("GameSignAccount", "KuroToken"): "",
            ("GameSignAccount", "SklandToken"): "skland-token",
        }
        account.get.side_effect = lambda group, name: values[(group, name)]
        account.set = AsyncMock()
        return account

    async def test_automatic_failure_is_not_retried_same_day(self) -> None:
        account = self.make_account()
        config = SimpleNamespace(
            ToolsConfig=SimpleNamespace(GameSign_Accounts={"account-1": account})
        )
        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        with (
            patch("app.tools.game_sign.Config", config),
            patch(
                "app.tools.game_sign._check_system_time",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.tools.skland.skland_sign_in",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
        ):
            await _run_all_sign_in(force=False)

        account.set.assert_awaited_once_with("GameSignAccount", "LastSignDate", today)

    async def test_manual_failure_does_not_mark_date(self) -> None:
        account = self.make_account()
        config = SimpleNamespace(
            ToolsConfig=SimpleNamespace(GameSign_Accounts={"account-1": account})
        )

        with (
            patch("app.tools.game_sign.Config", config),
            patch(
                "app.tools.game_sign._check_system_time",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.tools.skland.skland_sign_in",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
        ):
            await _run_all_sign_in(force=True)

        account.set.assert_not_awaited()


class GameSignResultFormattingTest(unittest.TestCase):
    def test_same_alias_accounts_remain_separate_by_uid(self) -> None:
        results = [
            {
                "account": "同名用户/角色一",
                "account_uid": "account-1",
                "platform": "米游社",
                "game": "原神",
                "status": "成功",
            },
            {
                "account": "同名用户/角色二",
                "account_uid": "account-2",
                "platform": "米游社",
                "game": "崩坏：星穹铁道",
                "status": "失败",
            },
        ]

        formatted = format_sign_results(results)

        self.assertEqual(len(formatted["米游社"]), 2)
        self.assertEqual(
            {group["account_uid"] for group in formatted["米游社"]},
            {"account-1", "account-2"},
        )

    def test_multiple_roles_for_same_uid_share_one_group(self) -> None:
        results = [
            {
                "account": "角色一/角色一(10001)",
                "account_uid": "account-1",
                "platform": "森空岛",
                "game": "明日方舟",
                "status": "成功",
            },
            {
                "account": "角色二/角色二(20001)",
                "account_uid": "account-1",
                "platform": "森空岛",
                "game": "终末地",
                "status": "已签到",
            },
        ]

        formatted = format_sign_results(results)

        self.assertEqual(len(formatted["森空岛"]), 1)
        self.assertEqual(len(formatted["森空岛"][0]["games"]), 2)


if __name__ == "__main__":
    unittest.main()
