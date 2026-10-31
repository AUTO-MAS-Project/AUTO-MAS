import unittest

from app.tools.common.community.providers import skland as _tool_skland


class SklandResponseTest(unittest.TestCase):
    def test_code_10001_means_already_signed(self) -> None:
        self.assertTrue(
            _tool_skland.is_skland_already_signed(
                {"code": 10001, "message": "attendance already completed"}
            )
        )

    def test_duplicate_message_remains_compatible(self) -> None:
        self.assertTrue(
            _tool_skland.is_skland_already_signed(
                {"code": 1, "message": "请勿重复签到！"}
            )
        )

    def test_english_duplicate_message_remains_compatible(self) -> None:
        self.assertTrue(
            _tool_skland.is_skland_already_signed(
                {"code": 1, "message": "Please do not sign in again!"}
            )
        )


if __name__ == "__main__":
    unittest.main()
