import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.tools import manual_game_sign
from app.tools import game_sign
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    format_game_sign_notification,
    format_game_sign_task_summary,
    push_game_sign_notification,
)


def make_results() -> list[dict]:
    return [
        {
            "account": "<同名用户>/米游社",
            "account_uid": "uid-1",
            "game": "<原神>",
            "platform": "米游社",
            "status": "成功",
            "reward": "<奖励>",
            "reason": "",
        },
        {
            "account": "<同名用户>/库街区",
            "account_uid": "uid-2",
            "game": "鸣潮",
            "platform": "库街区",
            "status": "失败",
            "reward": "",
            "reason": "<远程错误>",
        },
    ]


class GameSignNotificationTest(unittest.IsolatedAsyncioTestCase):
    async def test_platform_template_and_html_are_escaped(self) -> None:
        config_values = {
            ("Notify", "IfSendMail"): True,
            ("Notify", "ToAddress"): "receiver@example.com",
            ("Notify", "IfServerChan"): False,
            ("Notify", "IfKoishiSupport"): False,
        }

        with patch("app.tools.game_sign_notify.Config") as config, patch(
            "app.tools.game_sign_notify.Notify"
        ) as notify, patch(
            "app.tools.game_sign_notify.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            config.get.side_effect = lambda group, key: config_values[(group, key)]
            config.Notify_CustomWebhooks.items.return_value = []
            notify.push_plyer = AsyncMock()
            notify.send_mail = AsyncMock(
                side_effect=[RuntimeError("temporary failure"), None]
            )

            failed_channels = await push_game_sign_notification(make_results())

        self.assertEqual(failed_channels, [])
        self.assertEqual(notify.send_mail.await_count, 2)
        sleep.assert_awaited_once()

        plain_text = notify.push_plyer.await_args.kwargs["message"]
        html_content = notify.send_mail.await_args.kwargs["content"]
        self.assertIn("社区签到通知：", plain_text)
        self.assertIn("❌森空岛（0/0）：", plain_text)
        self.assertIn("✅米游社（1/1）：", plain_text)
        self.assertIn("❌库街区（0/1）：", plain_text)
        self.assertIn("<同名用户>/米游社 <原神> 签到成功", plain_text)
        self.assertIn("<同名用户>/库街区 鸣潮 签到失败-<远程错误>", plain_text)
        self.assertIn("&lt;同名用户&gt;/米游社 &lt;原神&gt; 签到成功", html_content)
        self.assertIn("&lt;远程错误&gt;", html_content)
        self.assertNotIn("<同名用户>/", html_content)

    def test_skland_identity_and_task_summary_match_template(self) -> None:
        results = [
            {
                "account": "Lance#8787/Lance#8787(10001)",
                "account_uid": "uid-1",
                "game": "明日方舟",
                "platform": "森空岛",
                "status": "已签到",
            },
            {
                "account": "EmberKnight/EmberKnight(20001)",
                "account_uid": "uid-1",
                "game": "终末地",
                "platform": "森空岛",
                "status": "成功",
            },
        ]

        notification = format_game_sign_notification(results)
        summary = format_game_sign_task_summary(results)

        self.assertIn("- 明日方舟(Lance#8787):已签", notification)
        self.assertIn("- 终末地(EmberKnight):签到成功", notification)
        self.assertEqual(
            summary,
            "签到情况：森空岛-明日方舟(Lance#8787):已签丨终末地(EmberKnight):签到成功",
        )

    def test_generic_failure_reason_is_not_duplicated(self) -> None:
        result = {
            "account": "Lance#8787/Lance#8787(10001)",
            "account_uid": "uid-1",
            "game": "明日方舟",
            "platform": "森空岛",
            "status": "失败",
            "reason": "签到失败",
        }

        notification = format_game_sign_notification([result])

        self.assertIn("明日方舟(Lance#8787):签到失败", notification)
        self.assertNotIn("签到失败-签到失败", notification)

    def test_platform_order_matches_notification_template(self) -> None:
        results = [
            {
                "account": "用户/用户(1)",
                "account_uid": "uid-kuro",
                "game": "鸣潮",
                "platform": "库街区",
                "status": "成功",
            },
            {
                "account": "用户/用户(2)",
                "account_uid": "uid-miyoushe",
                "game": "原神",
                "platform": "米游社",
                "status": "成功",
            },
            {
                "account": "Lance#8787/Lance#8787(3)",
                "account_uid": "uid-skland",
                "game": "明日方舟",
                "platform": "森空岛",
                "status": "成功",
            },
        ]

        notification = format_game_sign_notification(results)

        self.assertLess(notification.index("森空岛"), notification.index("米游社"))
        self.assertLess(notification.index("米游社"), notification.index("库街区"))

    def test_task_summary_orders_platforms_like_notification_template(self) -> None:
        results = [
            {
                "account": "用户/用户(1)",
                "account_uid": "uid-kuro",
                "game": "鸣潮",
                "platform": "库街区",
                "status": "成功",
            },
            {
                "account": "用户/用户(2)",
                "account_uid": "uid-miyoushe",
                "game": "原神",
                "platform": "米游社",
                "status": "成功",
            },
            {
                "account": "Lance#8787/Lance#8787(3)",
                "account_uid": "uid-skland",
                "game": "明日方舟",
                "platform": "森空岛",
                "status": "成功",
            },
        ]

        summary = format_game_sign_task_summary(results)

        self.assertLess(summary.index("森空岛"), summary.index("米游社"))
        self.assertLess(summary.index("米游社"), summary.index("库街区"))

    def test_empty_platform_is_rendered_as_zero_of_zero(self) -> None:
        result = {
            "account": "用户",
            "account_uid": "uid-1",
            "platform": "库街区",
            "status": "失败",
            "_notification_only": True,
        }

        notification = format_game_sign_notification([result])
        self.assertIn("❌库街区（0/0）：", notification)
        self.assertIn("- 失败", notification)

    def test_task_summary_is_consumed_once(self) -> None:
        task_info = type(
            "TaskInfo",
            (),
            {
                "game_sign_results": [
                    {
                        "account": "用户/用户(1)",
                        "account_uid": "uid-1",
                        "game": "原神",
                        "platform": "米游社",
                        "status": "成功",
                    }
                ],
                "game_sign_summary_consumed": False,
            },
        )()

        with patch("app.tools.game_sign_notify.Config") as config:
            config.ToolsConfig.get.return_value = True
            config.get.return_value = "任何时刻"
            first = append_task_game_sign_summary(
                task_info, "任务结果", uncompleted_count=0
            )
            second = append_task_game_sign_summary(
                task_info, "任务结果", uncompleted_count=0
            )

        self.assertIn("签到情况：米游社-用户/用户(1) 原神 签到成功", first)
        self.assertEqual(second, "任务结果")

    def test_task_summary_waits_for_a_report_selected_by_failure_policy(self) -> None:
        task_info = type(
            "TaskInfo",
            (),
            {
                "game_sign_results": [
                    {
                        "account": "用户/用户(1)",
                        "account_uid": "uid-1",
                        "game": "原神",
                        "platform": "米游社",
                        "status": "成功",
                    }
                ],
                "game_sign_summary_consumed": False,
            },
        )()

        with patch("app.tools.game_sign_notify.Config") as config:
            config.ToolsConfig.get.return_value = True
            config.get.return_value = "仅失败时"
            successful_report = append_task_game_sign_summary(
                task_info, "成功任务", uncompleted_count=0
            )
            failed_report = append_task_game_sign_summary(
                task_info, "失败任务", uncompleted_count=1
            )

        self.assertEqual(successful_report, "成功任务")
        self.assertIn("签到情况：", failed_report)
        self.assertTrue(task_info.game_sign_summary_consumed)

    def test_task_summary_respects_game_sign_notification_toggle(self) -> None:
        task_info = type(
            "TaskInfo",
            (),
            {
                "game_sign_results": [{"platform": "森空岛", "status": "成功"}],
                "game_sign_summary_consumed": False,
            },
        )()

        with patch("app.tools.game_sign_notify.Config") as config:
            config.ToolsConfig.get.return_value = False
            config.get.return_value = "任何时刻"
            report = append_task_game_sign_summary(
                task_info, "任务结果", uncompleted_count=1
            )

        self.assertEqual(report, "任务结果")
        self.assertFalse(task_info.game_sign_summary_consumed)

    async def test_failed_channel_is_returned_after_retry(self) -> None:
        config_values = {
            ("Notify", "IfSendMail"): True,
            ("Notify", "ToAddress"): "receiver@example.com",
            ("Notify", "IfServerChan"): False,
            ("Notify", "IfKoishiSupport"): False,
        }

        with patch("app.tools.game_sign_notify.Config") as config, patch(
            "app.tools.game_sign_notify.Notify"
        ) as notify, patch(
            "app.tools.game_sign_notify.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            config.get.side_effect = lambda group, key: config_values[(group, key)]
            config.Notify_CustomWebhooks.items.return_value = []
            notify.push_plyer = AsyncMock()
            notify.send_mail = AsyncMock(side_effect=RuntimeError("offline"))

            failed_channels = await push_game_sign_notification(make_results())

        self.assertEqual(failed_channels, ["邮件"])
        self.assertEqual(notify.send_mail.await_count, 2)

    async def test_false_channel_result_is_retried_and_reported(self) -> None:
        config_values = {
            ("Notify", "IfSendMail"): False,
            ("Notify", "IfServerChan"): False,
            ("Notify", "IfKoishiSupport"): True,
        }

        with patch("app.tools.game_sign_notify.Config") as config, patch(
            "app.tools.game_sign_notify.Notify"
        ) as notify, patch(
            "app.tools.game_sign_notify.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            config.get.side_effect = lambda group, key: config_values[(group, key)]
            config.Notify_CustomWebhooks.items.return_value = []
            notify.push_plyer = AsyncMock()
            notify.send_koishi = AsyncMock(return_value=False)

            failed_channels = await push_game_sign_notification(make_results())

        self.assertEqual(failed_channels, ["Koishi"])
        self.assertEqual(notify.send_koishi.await_count, 2)


class GameSignConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_run_is_rejected(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def run_once(force: bool) -> list[dict]:
            started.set()
            await release.wait()
            return [{"status": "成功"}]

        with patch.object(game_sign, "_run_all_sign_in", side_effect=run_once):
            first_run = asyncio.create_task(game_sign.run_all_sign_in(force=False))
            await started.wait()
            try:
                with self.assertRaisesRegex(
                    game_sign.GameSignInProgressError,
                    "正在执行",
                ):
                    await game_sign.run_all_sign_in(force=True)
            finally:
                release.set()

            self.assertEqual(await first_run, [{"status": "成功"}])


class ManualGameSignTest(unittest.IsolatedAsyncioTestCase):
    async def test_manual_sign_reports_automatic_sign_conflict(self) -> None:
        from app.tools.game_sign import GameSignInProgressError

        with patch(
            "app.tools.game_sign.run_all_sign_in",
            new=AsyncMock(side_effect=GameSignInProgressError("自动签到正在执行")),
        ):
            response = await manual_game_sign()

        self.assertEqual(response.code, 409)
        self.assertEqual(response.status, "error")
        self.assertIn("自动签到正在执行", response.message)

    async def test_manual_sign_sends_notification_and_reports_partial_failure(
        self,
    ) -> None:
        tools_config = MagicMock()
        tools_config._game_sign_result_data = {}
        tools_config.GameSign_Accounts = {}
        tools_config.get.return_value = True
        tools_config.set = AsyncMock()
        results = make_results()

        with patch("app.api.tools.Config") as config, patch(
            "app.tools.game_sign.run_all_sign_in",
            new=AsyncMock(return_value=results),
        ), patch(
            "app.tools.game_sign.format_sign_results",
            return_value={"formatted": []},
        ), patch(
            "app.tools.game_sign.merge_sign_results",
            return_value={"merged": []},
        ), patch(
            "app.tools.game_sign_notify.push_game_sign_notification",
            new=AsyncMock(return_value=["邮件"]),
        ) as push_notification:
            config.ToolsConfig = tools_config

            response = await manual_game_sign()

        self.assertEqual(response.code, 200)
        self.assertEqual(response.status, "warning")
        self.assertIn("邮件", response.message)
        push_notification.assert_awaited_once_with(results)


if __name__ == "__main__":
    unittest.main()
