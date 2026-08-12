import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.notification import Notification, SMTP_TIMEOUT_SECONDS


class NotificationServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_push_plyer_runs_desktop_notification_in_thread(self) -> None:
        async def run_inline(send, *args, **kwargs):
            send(*args, **kwargs)

        with patch(
            "app.services.notification.Config.get",
            return_value=True,
        ), patch("app.services.notification.notification.notify") as notify, patch(
            "app.services.notification.asyncio.to_thread",
            new=AsyncMock(side_effect=run_inline),
        ) as to_thread:
            await Notification().push_plyer(
                title="签到结果",
                message="成功",
                ticker="签到结果",
                t=5,
            )

        to_thread.assert_awaited_once()
        notify.assert_called_once()

    async def test_send_mail_runs_smtp_in_thread_with_timeout(self) -> None:
        config_values = {
            ("Notify", "SMTPServerAddress"): "smtp.example.com",
            ("Notify", "AuthorizationCode"): "secret",
            ("Notify", "FromAddress"): "sender@example.com",
        }
        smtp = MagicMock()

        async def run_inline(send):
            send()

        with patch(
            "app.services.notification.Config.get",
            side_effect=lambda group, key: config_values[(group, key)],
        ), patch("app.services.notification.smtplib.SMTP_SSL") as smtp_ssl, patch(
            "app.services.notification.asyncio.to_thread",
            new=AsyncMock(side_effect=run_inline),
        ) as to_thread:
            smtp_ssl.return_value.__enter__.return_value = smtp

            await Notification().send_mail(
                mode="网页",
                title="签到结果",
                content="<p>成功</p>",
                to_address="receiver@example.com",
            )

        to_thread.assert_awaited_once()
        smtp_ssl.assert_called_once_with(
            "smtp.example.com",
            465,
            timeout=SMTP_TIMEOUT_SECONDS,
        )
        smtp.login.assert_called_once_with("sender@example.com", "secret")
        self.assertEqual(
            smtp.sendmail.call_args.args[:2],
            ("sender@example.com", "receiver@example.com"),
        )


if __name__ == "__main__":
    unittest.main()
