import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.tools.skland import prepare_skland_session_credential
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

    def test_english_duplicate_message_remains_compatible(self) -> None:
        self.assertTrue(
            is_skland_already_signed(
                {"code": 1, "message": "Please do not sign in again!"}
            )
        )


class SklandSessionTest(unittest.TestCase):
    def test_incomplete_cached_credential_reauthorizes_with_oauth(self) -> None:
        client = AsyncMock()

        with patch(
            "app.tools.skland._get_grant_code",
            new=AsyncMock(return_value="grant-code"),
        ) as get_grant_code, patch(
            "app.tools.skland._get_cred_by_code",
            new=AsyncMock(
                return_value={
                    "token": "new-sign-token",
                    "cred": "new-cred",
                    "userId": "user-id",
                }
            ),
        ):
            credential = asyncio.run(
                prepare_skland_session_credential(
                    client,
                    {
                        "oauthToken": "oauth-token",
                        "cred": "incomplete-cached-cred",
                    },
                    "device-id",
                )
            )

        get_grant_code.assert_awaited_once_with(
            client,
            "oauth-token",
            "device-id",
        )
        self.assertEqual(credential["token"], "new-sign-token")
        self.assertEqual(credential["cred"], "new-cred")


if __name__ == "__main__":
    unittest.main()
