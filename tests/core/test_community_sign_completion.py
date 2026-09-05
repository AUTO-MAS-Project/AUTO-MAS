import unittest

from app.core.community_sign import all_enabled_community_platforms_signed


class CommunitySignCompletionTest(unittest.TestCase):
    def test_shared_platform_requires_every_result_to_succeed(self) -> None:
        results = [
            {
                "account_uid": "account-1",
                "game": "原神",
                "platform": "米游社",
                "status": "成功",
            },
            {
                "account_uid": "account-1",
                "game": "云原神",
                "platform": "米游社",
                "status": "失败",
            },
        ]

        self.assertFalse(
            all_enabled_community_platforms_signed(
                results,
                account_uid="account-1",
                enabled_platforms=["米游社"],
            )
        )

    def test_shared_platform_is_complete_when_every_result_succeeds(self) -> None:
        results = [
            {
                "account_uid": "account-1",
                "game": "米游币任务",
                "platform": "米游社",
                "status": "已签到",
            },
            {
                "account_uid": "account-1",
                "game": "云原神",
                "platform": "米游社",
                "status": "成功",
            },
        ]

        self.assertTrue(
            all_enabled_community_platforms_signed(
                results,
                account_uid="account-1",
                enabled_platforms=["米游社"],
            )
        )


if __name__ == "__main__":
    unittest.main()
