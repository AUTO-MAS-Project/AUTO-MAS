import ctypes
import unittest

from app.services.notification import (
    PLYER_MESSAGE_LIMIT,
    PLYER_TITLE_LIMIT,
    clip_notify_text,
)

EMOJI = "\U0001f600"  # 非 BMP：1 个码位 = 2 个 UTF-16 代码单元


def utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def fits_fixed_field(text: str, limit: int) -> bool:
    """模拟 plyer 把字符串写入 NOTIFYICONDATA 定长字段（含结尾空字符）。"""

    try:
        field = (ctypes.c_wchar * (limit + 1))()
        field.value = text
    except ValueError:
        return False
    return True


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

        self.assertEqual(utf16_units(result), PLYER_MESSAGE_LIMIT)
        self.assertTrue(result.endswith("…"))

    def test_clips_non_bmp_by_utf16_units(self):
        """emoji 占 1 个码位却要 2 个代码单元，按码位截断会溢出。"""

        text = EMOJI * PLYER_TITLE_LIMIT

        result = clip_notify_text(text, PLYER_TITLE_LIMIT)

        self.assertLessEqual(utf16_units(result), PLYER_TITLE_LIMIT)

    def test_clipped_non_bmp_has_no_broken_surrogate(self):
        """截断点落在代理对中间时不应留下半个代理对。"""

        text = EMOJI * 100

        result = clip_notify_text(text, PLYER_TITLE_LIMIT)

        self.assertEqual(result.encode("utf-16-le").decode("utf-16-le"), result)

    def test_results_fit_the_fixed_width_field(self):
        for label, text in (
            ("纯 BMP", "正" * 500),
            ("纯 emoji", EMOJI * 500),
            ("混排", EMOJI * 40 + "正" * 500),
            ("恰好满", "正" * PLYER_MESSAGE_LIMIT),
        ):
            with self.subTest(label):
                clipped = clip_notify_text(text, PLYER_MESSAGE_LIMIT)
                self.assertTrue(fits_fixed_field(clipped, PLYER_MESSAGE_LIMIT))

    def test_limits_leave_room_for_terminator(self):
        """NOTIFYICONDATA 的 szInfoTitle 为 64、szInfo 为 256，需各留一位空字符。"""

        self.assertEqual(PLYER_TITLE_LIMIT, 63)
        self.assertEqual(PLYER_MESSAGE_LIMIT, 255)


if __name__ == "__main__":
    unittest.main()
