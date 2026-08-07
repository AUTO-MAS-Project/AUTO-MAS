import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.tools import manual_game_sign
from app.tools import game_sign
from app.tools.game_sign_notify import push_game_sign_notification


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
    async def test_same_alias_is_not_merged_and_html_is_escaped(self) -> None:
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
        self.assertEqual(plain_text.count("No.<同名用户>:"), 2)
        self.assertIn("共 2 个账号", plain_text)
        self.assertEqual(html_content.count("No.&lt;同名用户&gt;:"), 2)
        self.assertIn("&lt;原神&gt;", html_content)
        self.assertIn("&lt;奖励&gt;", html_content)
        self.assertIn("&lt;远程错误&gt;", html_content)
        self.assertNotIn("<同名用户>", html_content)

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
