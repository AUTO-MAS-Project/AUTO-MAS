import asyncio
import hashlib
import hmac
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.tools.cloud_genshin import (
    CloudGenshinBusinessError,
    CloudGenshinUnavailableError,
    _prepare_cloud_genshin_credential,
    build_cloud_genshin_combo_token,
    calculate_cloud_genshin_gain,
    cloud_genshin_sign_in,
    format_cloud_genshin_duration,
    parse_cloud_genshin_free_time,
    validate_cloud_genshin_token,
)


class CloudGenshinContractTest(unittest.TestCase):
    @staticmethod
    def _web_login_client(payload: dict[str, object]) -> AsyncMock:
        client = AsyncMock()
        client.request.return_value = httpx.Response(
            200,
            json=payload,
            request=httpx.Request("POST", "https://hk4e-sdk.mihoyo.com/test"),
        )
        return client

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

    def test_builds_signed_combo_token_from_web_login_result(self) -> None:
        combo_token = "combo-token-" + "x" * 20
        open_id = "100000001"
        signature = hmac.new(
            b"d0d3a7342df2026a70f650b907800111",
            (
                "app_id=4&channel_id=1"
                f"&combo_token={combo_token}&open_id={open_id}"
            ).encode(),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(
            build_cloud_genshin_combo_token(combo_token, open_id),
            (
                f"ai=4;ci=1;oi={open_id};ct={combo_token};"
                f"si={signature};bi=hk4e_cn"
            ),
        )

    def test_historical_full_token_does_not_call_web_login(self) -> None:
        client = AsyncMock()
        token = "ai=4;ci=1;oi=100;ct=legacy-token;si=signature;bi=hk4e_cn"

        result = asyncio.run(_prepare_cloud_genshin_credential(client, token))

        self.assertEqual(result, (token, False, ""))
        client.request.assert_not_awaited()

    def test_miyoushe_cookie_is_exchanged_without_persisting_combo_token(self) -> None:
        client = self._web_login_client(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "combo_token": "combo-token-" + "x" * 20,
                },
            }
        )
        cookie = (
            "stuid=100000001; cookie_token=cookie-token; "
            "stoken_v2=v2-token; mid=mid-value"
        )

        with patch(
            "app.tools.cloud_genshin.build_cloud_genshin_combo_token",
            return_value="signed-token",
        ) as build:
            token, from_miyoushe_cookie, device_id = asyncio.run(
                _prepare_cloud_genshin_credential(client, cookie)
            )

        self.assertEqual(token, "signed-token")
        self.assertTrue(from_miyoushe_cookie)
        self.assertTrue(device_id)
        build.assert_called_once_with("combo-token-" + "x" * 20, "100000001")
        request_kwargs = client.request.await_args.kwargs
        self.assertEqual(
            request_kwargs["json"],
            {"app_id": 4, "channel_id": 1},
        )
        self.assertEqual(request_kwargs["cookies"]["cookie_token"], "cookie-token")

    def test_web_login_auth_expiry_is_not_treated_as_unavailable_cloud_game(
        self,
    ) -> None:
        client = self._web_login_client(
            {
                "retcode": -100,
                "message": "登录失效",
            }
        )
        cookie = "stuid=100000001; cookie_token=cookie-token"

        with self.assertRaisesRegex(ValueError, "凭据已失效"):
            asyncio.run(_prepare_cloud_genshin_credential(client, cookie))

    def test_other_web_login_business_rejection_skips_optional_cloud_game(
        self,
    ) -> None:
        client = self._web_login_client(
            {
                "retcode": -1,
                "message": "account unavailable",
            }
        )
        cookie = "stuid=100000001; cookie_token=cookie-token"

        with self.assertRaises(CloudGenshinUnavailableError):
            asyncio.run(_prepare_cloud_genshin_credential(client, cookie))

    def test_optional_cloud_wallet_business_error_is_a_completed_skip(self) -> None:
        with (
            patch(
                "app.tools.cloud_genshin._prepare_cloud_genshin_credential",
                new=AsyncMock(return_value=("signed-token", True, "device")),
            ),
            patch(
                "app.tools.cloud_genshin._query_free_time",
                new=AsyncMock(side_effect=CloudGenshinBusinessError("not available")),
            ),
        ):
            result = asyncio.run(
                cloud_genshin_sign_in(
                    "stuid=100000001; cookie_token=cookie-token",
                    account_name="用户 1",
                    account_uid="account-1",
                    proxy=None,
                )
            )

        self.assertEqual(result[0]["status"], "跳过")
        self.assertTrue(result[0]["_completed"])
        self.assertTrue(result[0]["_notification_only"])


if __name__ == "__main__":
    unittest.main()
