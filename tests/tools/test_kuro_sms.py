import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.tools import kuro


PHONE = "13800138000"
ACCOUNT_ID = "account-1"


def _response(payload: dict[str, object], status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.kurobbs.com/test"),
    )


def _client(*responses: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(side_effect=list(responses))
    return client


class KuroSmsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        kuro._KURO_SMS_SESSIONS.clear()

    def tearDown(self) -> None:
        kuro._KURO_SMS_SESSIONS.clear()

    async def test_send_requires_explicit_geetest_false(self) -> None:
        client = _client(_response({"code": 200, "data": {"geeTest": True}}))

        with patch.object(kuro.httpx, "AsyncClient", return_value=client):
            with self.assertRaises(kuro.KuroSmsCaptchaRequiredError):
                await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)

        self.assertEqual(kuro._KURO_SMS_SESSIONS, {})

    async def test_send_and_login_share_device_and_consume_session(self) -> None:
        client = _client(
            _response({"code": 200, "data": {"geeTest": False}}),
            _response({"code": 200, "data": {"token": "kuro-token"}}),
        )

        with patch.object(kuro.httpx, "AsyncClient", return_value=client):
            session = await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)
            token = await kuro.login_kuro_with_sms(
                ACCOUNT_ID,
                session.session_id,
                PHONE,
                "123456",
                proxy=None,
            )

        self.assertEqual(token, "kuro-token")
        self.assertNotIn(session.session_id, kuro._KURO_SMS_SESSIONS)
        send_kwargs = client.post.await_args_list[0].kwargs
        login_kwargs = client.post.await_args_list[1].kwargs
        send_headers = send_kwargs["headers"]
        login_headers = login_kwargs["headers"]
        self.assertEqual(send_headers["devcode"], login_headers["devcode"])
        self.assertEqual(send_headers["distinct_id"], login_headers["distinct_id"])
        self.assertEqual(send_kwargs["data"]["geeTestData"], "")
        self.assertEqual(login_kwargs["data"]["code"], "123456")
        self.assertEqual(login_kwargs["data"]["devCode"], send_headers["devcode"])

    async def test_invalid_code_keeps_session_for_retry(self) -> None:
        client = _client(
            _response({"code": 200, "data": {"geeTest": False}}),
            _response({"code": -130, "msg": "验证码错误"}),
        )

        with patch.object(kuro.httpx, "AsyncClient", return_value=client):
            session = await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)
            with self.assertRaises(kuro.KuroSmsCodeError):
                await kuro.login_kuro_with_sms(
                    ACCOUNT_ID,
                    session.session_id,
                    PHONE,
                    "123456",
                    proxy=None,
                )

        self.assertIn(session.session_id, kuro._KURO_SMS_SESSIONS)

    async def test_rate_limit_is_distinguished_from_success(self) -> None:
        client = _client(_response({"code": 242, "msg": "频繁"}))

        with patch.object(kuro.httpx, "AsyncClient", return_value=client):
            with self.assertRaises(kuro.KuroSmsRateLimitError):
                await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)

        self.assertEqual(kuro._KURO_SMS_SESSIONS, {})

    async def test_session_is_removed_without_follow_up_request(self) -> None:
        client = _client(_response({"code": 200, "data": {"geeTest": False}}))

        with (
            patch.object(kuro.httpx, "AsyncClient", return_value=client),
            patch.object(kuro, "KURO_SMS_SESSION_TTL", 0),
        ):
            session = await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)
            await asyncio.sleep(0.01)

        self.assertNotIn(session.session_id, kuro._KURO_SMS_SESSIONS)

    async def test_session_cannot_be_reused_for_another_account(self) -> None:
        client = _client(_response({"code": 200, "data": {"geeTest": False}}))

        with patch.object(kuro.httpx, "AsyncClient", return_value=client):
            session = await kuro.create_kuro_sms_session(ACCOUNT_ID, PHONE, proxy=None)

        with self.assertRaises(kuro.KuroSmsSessionError):
            await kuro.login_kuro_with_sms(
                "another-account",
                session.session_id,
                PHONE,
                "123456",
                proxy=None,
            )


if __name__ == "__main__":
    unittest.main()
