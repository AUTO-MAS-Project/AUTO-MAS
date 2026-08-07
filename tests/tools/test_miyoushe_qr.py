import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.tools.miyoushe_qr import check_qr_status, create_qr_login


def _mock_client(response: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


class MiyousheQrTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_status_payload_is_reported_as_expired(self) -> None:
        response = httpx.Response(
            200,
            json={"retcode": 0, "data": None},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Expired")
        self.assertIn("过期", result["message"])

    async def test_non_expired_service_error_is_not_misreported_as_expired(self) -> None:
        response = httpx.Response(
            200,
            json={"retcode": -1, "message": "服务暂时不可用", "data": None},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Error")
        self.assertEqual(result["error"], "服务暂时不可用")

    async def test_non_object_create_payload_does_not_raise_none_type_error(self) -> None:
        response = httpx.Response(
            200,
            content=b"null",
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await create_qr_login()

        self.assertEqual(result["error"], "服务器返回空响应，无法创建二维码")

    async def test_v2_qr_cookies_include_legacy_auth_aliases(self) -> None:
        headers = [
            ("set-cookie", "cookie_token_v2=token-v2; Path=/"),
            ("set-cookie", "ltuid_v2=10001; Path=/"),
            ("set-cookie", "account_id_v2=10001; Path=/"),
            ("set-cookie", "ltoken_v2=ltoken-v2; Path=/"),
            ("set-cookie", "ltmid_v2=mid-v2; Path=/"),
        ]
        response = httpx.Response(
            200,
            json={"retcode": 0, "data": {"status": "Confirmed"}},
            headers=headers,
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Confirmed")
        cookie = result["cookies_str"]
        self.assertIn("cookie_token_v2=token-v2", cookie)
        self.assertIn("cookie_token=token-v2", cookie)
        self.assertIn("stuid=10001", cookie)
        self.assertIn("account_id=10001", cookie)
        self.assertIn("mid=mid-v2", cookie)

    async def test_v2_qr_cookies_can_be_read_from_confirm_payload(self) -> None:
        response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "status": "Confirmed",
                    "cookie_token_v2": "token-v2",
                    "stoken_v2": "stoken-v2",
                    "mid_v2": "mid-v2",
                    "ltuid_v2": "10001",
                },
            },
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Confirmed")
        self.assertIn("cookie_token=token-v2", result["cookies_str"])
        self.assertIn("stoken=stoken-v2", result["cookies_str"])
        self.assertIn("stuid=10001", result["cookies_str"])
        self.assertIn("mid=mid-v2", result["cookies_str"])

    async def test_nested_qr_cookie_payload_keeps_authentication_fields(self) -> None:
        response = httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {
                    "status": "Confirmed",
                    "cookies": {
                        "cookie_token_v2": "nested-token",
                        "stoken_v2": "nested-stoken",
                        "ltuid_v2": "10002",
                        "mid_v2": "nested-mid",
                    },
                },
            },
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch(
            "app.tools.miyoushe_qr.httpx.AsyncClient",
            return_value=_mock_client(response),
        ):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Confirmed")
        cookie = result["cookies_str"]
        self.assertIn("cookie_token=nested-token", cookie)
        self.assertIn("stoken=nested-stoken", cookie)
        self.assertIn("stuid=10002", cookie)
        self.assertIn("mid=nested-mid", cookie)

    async def test_confirmed_without_auth_cookie_is_rejected(self) -> None:
        response = httpx.Response(
            200,
            json={"retcode": 0, "data": {"status": "Confirmed"}},
            headers={"set-cookie": "ltuid_v2=10001; Path=/"},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch("app.tools.miyoushe_qr.httpx.AsyncClient", return_value=_mock_client(response)):
            result = await check_qr_status("ticket", "device")

        self.assertEqual(result["status"], "Error")
        self.assertIn("认证 Cookie", result["error"])

    async def test_sign_in_accepts_qr_cookie_token_v2(self) -> None:
        roles = AsyncMock(return_value=[])

        with patch("app.tools.miyoushe._get_game_roles", new=roles):
            from app.tools.miyoushe import miyoushe_sign_in

            result = await miyoushe_sign_in(
                "ltuid_v2=10001; cookie_token_v2=token-v2",
            )

        self.assertEqual(result, [])
        roles.assert_awaited_once()
        effective_cookie = roles.await_args.args[0]
        self.assertIn("cookie_token=token-v2", effective_cookie)

    async def test_sign_in_accepts_qr_stoken_v2_and_mid_v2(self) -> None:
        roles = AsyncMock(return_value=[])
        derive = AsyncMock(return_value=("derived-token", "10001"))

        with (
            patch("app.tools.miyoushe._get_game_roles", new=roles),
            patch("app.tools.miyoushe._derive_cookie_token", new=derive),
        ):
            from app.tools.miyoushe import miyoushe_sign_in

            result = await miyoushe_sign_in(
                "ltuid_v2=10001; stoken_v2=stoken-v2; mid_v2=mid-v2",
            )

        self.assertEqual(result, [])
        derive.assert_awaited_once_with("stoken-v2", "mid-v2", "10001", None)
        roles.assert_awaited_once()
        effective_cookie = roles.await_args.args[0]
        self.assertIn("cookie_token=derived-token", effective_cookie)


if __name__ == "__main__":
    unittest.main()
