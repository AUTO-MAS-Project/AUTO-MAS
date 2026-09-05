import unittest

from app.tools.community_notify import (
    detect_community_notification_format,
    format_community_notification,
    format_community_task_summary,
)
from app.tools.game_sign_notify import format_game_sign_notification


class CommunityNotificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.results = [
            {
                "account": "旅行者",
                "account_uid": "account-1",
                "game": "原神",
                "platform": "米游社",
                "status": "失败",
                "reason": "凭据失效",
            },
            {
                "account": "开拓者",
                "account_uid": "account-1",
                "game": "星穹铁道",
                "platform": "米游社",
                "status": "成功",
                "reason": "",
            },
        ]

    def test_markdown_is_detected_and_keeps_failure_reason(self) -> None:
        content = format_community_notification(self.results)

        self.assertEqual(
            detect_community_notification_format(content), "markdown"
        )
        self.assertIn("### ❌米游社(1/2):", content)
        self.assertIn("签到失败-凭据失效", content)

    def test_plain_text_and_legacy_entry_share_structured_result(self) -> None:
        plain_text = format_community_notification(
            self.results,
            output_format="text",
        )

        self.assertEqual(detect_community_notification_format(plain_text), "text")
        self.assertEqual(format_game_sign_notification(self.results), format_community_notification(self.results))
        self.assertIn("米游社-旅行者 原神 签到失败-凭据失效", format_community_task_summary(self.results))


if __name__ == "__main__":
    unittest.main()
