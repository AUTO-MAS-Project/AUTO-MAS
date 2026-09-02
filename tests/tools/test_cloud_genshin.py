import unittest

from app.tools.cloud_genshin import (
    calculate_cloud_genshin_gain,
    format_cloud_genshin_duration,
    parse_cloud_genshin_free_time,
    validate_cloud_genshin_token,
)


class CloudGenshinContractTest(unittest.TestCase):
    def test_reads_only_nested_free_time_seconds(self) -> None:
        self.assertEqual(
            parse_cloud_genshin_free_time(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {
                        "free_time": {"free_time": 3661},
                        "total_time": 9999,
                    },
                }
            ),
            3661,
        )

    def test_rejects_generic_or_missing_duration_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "free_time"):
            parse_cloud_genshin_free_time(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {"total_time": 3661},
                }
            )

    def test_duration_format_and_non_increasing_reward_boundary(self) -> None:
        self.assertEqual(format_cloud_genshin_duration(3661), "1 小时 1 分钟 1 秒")
        self.assertEqual(calculate_cloud_genshin_gain(120, 180), 60)
        self.assertEqual(calculate_cloud_genshin_gain(180, 120), 0)

    def test_token_validation_does_not_accept_control_or_short_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_cloud_genshin_token("too-short")
        with self.assertRaises(ValueError):
            validate_cloud_genshin_token("x" * 30 + "\n")


if __name__ == "__main__":
    unittest.main()
