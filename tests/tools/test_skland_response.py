import unittest

from app.tools.skland_response import is_skland_already_signed


class SklandResponseTest(unittest.TestCase):
    def test_code_10001_means_already_signed(self) -> None:
        self.assertTrue(
            is_skland_already_signed(
                {"code": 10001, "message": "attendance already completed"}
            )
        )

    def test_duplicate_message_remains_compatible(self) -> None:
        self.assertTrue(
            is_skland_already_signed({"code": 1, "message": "请勿重复签到！"})
        )


if __name__ == "__main__":
    unittest.main()
