import unittest

from app.services.notification import (
    PLYER_MESSAGE_LIMIT,
    PLYER_TITLE_LIMIT,
    clip_notify_text,
)


class ClipNotifyTextTest(unittest.TestCase):
    def test_keeps_text_within_limit(self):
        text = "任务已完成"

        self.assertEqual(clip_notify_text(text, PLYER_TITLE_LIMIT), text)

    def test_keeps_text_exactly_at_limit(self):
        text = "标" * PLYER_TITLE_LIMIT

        self.assertEqual(clip_notify_text(text, PLYER_TITLE_LIMIT), text)

    def test_clips_text_over_limit(self):
        text = "正" * (PLYER_MESSAGE_LIMIT + 100)

        result = clip_notify_text(text, PLYER_MESSAGE_LIMIT)

        self.assertEqual(len(result), PLYER_MESSAGE_LIMIT)
        self.assertTrue(result.endswith("…"))

    def test_limits_leave_room_for_terminator(self):
        """NOTIFYICONDATA 的 szInfoTitle 为 64、szInfo 为 256，需各留一位空字符。"""

        self.assertEqual(PLYER_TITLE_LIMIT, 63)
        self.assertEqual(PLYER_MESSAGE_LIMIT, 255)


if __name__ == "__main__":
    unittest.main()
