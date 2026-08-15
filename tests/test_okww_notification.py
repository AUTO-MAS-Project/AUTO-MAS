import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.core import Config
from app.models.config import OkwwUserConfig
from app.services import Notify
from app.task.Okww.tools.notify import push_notification


class OkwwNotificationTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_statistics_notification_uses_user_channels(self) -> None:
        user_config = OkwwUserConfig()
        user_config.Notify_Enabled.setValue(True)
        user_config.Notify_IfSendStatistic.setValue(True)
        user_config.Notify_IfSendMail.setValue(True)
        user_config.Notify_ToAddress.setValue("user@example.com")

        template = Mock()
        template.render.return_value = "<html>统计</html>"
        notify_env = Mock()
        notify_env.get_template.return_value = template

        with (
            patch.object(Config, "notify_env", notify_env),
            patch.object(Notify, "send_mail", new_callable=AsyncMock) as send_mail,
        ):
            await push_notification(
                "统计信息",
                "OK-WW 统计",
                {
                    "user_info": "测试用户",
                    "start_time": "2026-08-15 10:00:00",
                    "end_time": "2026-08-15 10:10:00",
                    "user_result": "代理任务全部完成",
                },
                user_config,
            )

        send_mail.assert_awaited_once_with(
            "网页",
            "OK-WW 统计",
            "<html>统计</html>",
            "user@example.com",
        )
