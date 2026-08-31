import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.tools.miyoushe_qr import (
    _check_game_token_qr_status,
    _game_token_qr_data,
    _has_complete_qr_credential,
    check_qr_status,
    exchange_stoken,
)


class _FakeAsyncClient:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, *args, **kwargs) -> httpx.Response:
        return self.responses.pop(0)


class MiyousheQrContractTest(unittest.IsolatedAsyncioTestCase):
    def test_accepts_confirmed_game_token_qr_host(self) -> None:
        result = _game_token_qr_data(
            {
                "url": (
                    "https://user.mihoyo.com/qr_code_in_game.html"
                    "?app_id=2&ticket=qr-ticket"
                )
            }
        )

        self.assertEqual(
            result,
            (
                "https://user.mihoyo.com/qr_code_in_game.html"
                "?app_id=2&ticket=qr-ticket",
                "qr-ticket",
            ),
        )
        self.assertIsNone(
            _game_token_qr_data(
                {
                    "url": (
                        "https://example.com/qr_code_in_game.html"
                        "?ticket=qr-ticket"
                    )
                }
            )
        )

    def test_complete_credential_requires_stoken_v2_and_mid(self) -> None:
        self.assertFalse(
            _has_complete_qr_credential(
                {"cookie_token_v2": "cookie", "account_id_v2": "100"}
            )
        )
        self.assertTrue(
            _has_complete_qr_credential(
                {"stoken_v2": "v2_stoken", "account_mid_v2": "mid"}
            )
        )

    async def test_passport_confirmation_rejects_incomplete_credential(self) -> None:
        response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "status": "Confirmed",
                    "cookies": {
                        "cookie_token_v2": "v2_cookie",
                        "account_id_v2": "100",
                    },
                },
            },
            request=httpx.Request("POST", "https://passport.invalid"),
        )
        with (
            patch(
                "app.tools.miyoushe_qr.httpx.AsyncClient",
                return_value=_FakeAsyncClient(response),
            ),
            patch(
                "app.tools.miyoushe_qr._supplement_stoken",
                new=AsyncMock(),
            ),
        ):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Error")
        self.assertIn("stoken_v2", result["error"])
        self.assertNotIn("重新生成", result["error"])
        self.assertNotIn("cookies_str", result)

    async def test_passport_confirmation_supplements_v1_and_keeps_cookie_fields(
        self,
    ) -> None:
        long_stoken = "v2_" + "s" * 2048 + ".CAE="
        response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "status": "Confirmed",
                    "cookies": {
                        "stoken": "v1_stoken",
                        "login_ticket": "one-time-ticket",
                        "account_id_v2": "100",
                        "account_mid_v2": "mid",
                        "future_cookie_field": "keep",
                    },
                },
            },
            request=httpx.Request("POST", "https://passport.invalid"),
        )

        async def supplement(cookie_parts: dict[str, str], proxy=None) -> None:
            cookie_parts["stoken_v2"] = long_stoken

        with (
            patch(
                "app.tools.miyoushe_qr.httpx.AsyncClient",
                return_value=_FakeAsyncClient(response),
            ),
            patch(
                "app.tools.miyoushe_qr._supplement_stoken",
                new=AsyncMock(side_effect=supplement),
            ) as supplement_mock,
        ):
            result = await check_qr_status("ticket", "device")

        supplement_mock.assert_awaited_once()
        self.assertEqual(result["status"], "Confirmed")
        self.assertIn(f"stoken_v2={long_stoken}", result["cookies_str"])
        self.assertIn("future_cookie_field=keep", result["cookies_str"])
        self.assertNotIn("login_ticket", result["cookies_str"])

    async def test_game_token_confirmation_returns_full_v2_credential(self) -> None:
        response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "stat": "Confirmed",
                    "payload": {
                        "raw": json.dumps({"uid": "100", "token": "once"})
                    },
                },
            },
            request=httpx.Request("POST", "https://sdk.invalid"),
        )
        with (
            patch(
                "app.tools.miyoushe_qr.httpx.AsyncClient",
                return_value=_FakeAsyncClient(response),
            ),
            patch(
                "app.tools.miyoushe_qr.exchange_stoken",
                new=AsyncMock(
                    return_value={
                        "cookies_str": (
                            "custom_field=keep; stoken=v2_stoken; "
                            "account_mid_v2=mid; account_id_v2=100"
                        )
                    }
                ),
            ),
        ):
            result = await _check_game_token_qr_status(
                "qr-ticket", "device"
            )

        self.assertEqual(result["status"], "Confirmed")
        self.assertIn("stoken_v2=v2_stoken", result["cookies_str"])
        self.assertIn("mid=mid", result["cookies_str"])
        self.assertIn("custom_field=keep", result["cookies_str"])

    async def test_game_token_exchange_preserves_long_stoken_v2(self) -> None:
        long_stoken = "v2_" + "x" * 4096 + ".CAE="
        stoken_response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "token": {"token": long_stoken},
                    "user_info": {"mid": "mid-value"},
                },
            },
            request=httpx.Request("POST", "https://session.invalid"),
        )
        cookie_response = httpx.Response(
            200,
            json={"retcode": -1, "data": None},
            request=httpx.Request("POST", "https://cookie.invalid"),
        )
        with patch(
            "app.tools.miyoushe_qr.httpx.AsyncClient",
            return_value=_FakeAsyncClient(stoken_response, cookie_response),
        ):
            result = await exchange_stoken("one-time-game-token", "100")

        parts = dict(
            item.split("=", 1)
            for item in result["cookies_str"].split("; ")
        )
        self.assertEqual(parts["stoken_v2"], long_stoken)
        self.assertEqual(parts["stoken"], long_stoken)
        self.assertEqual(parts["mid"], "mid-value")


if __name__ == "__main__":
    unittest.main()
