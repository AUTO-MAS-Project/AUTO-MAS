import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.miyoushe import _do_sign


class MiyousheRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_refreshed_cookie_is_sent_on_retry(self) -> None:
        expired_response = MagicMock()
        expired_response.text = '{"retcode": -100}'
        expired_response.json.return_value = {
            "retcode": -100,
            "message": "登录失效",
        }
        success_response = MagicMock()
        success_response.text = '{"retcode": 0}'
        success_response.json.return_value = {"retcode": 0, "data": {}}

        client = MagicMock()
        client.post = AsyncMock(
            side_effect=[expired_response, success_response]
        )
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.tools.miyoushe.httpx.AsyncClient",
            return_value=client_context,
        ), patch(
            "app.tools.miyoushe.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await _do_sign(
                "stuid=10001; cookie_token=expired; cookie_token_v2=fresh",
                {
                    "act_id": "activity",
                    "sign_url": "https://example.com/sign",
                    "name": "原神",
                },
                "cn_gf01",
                "20001",
                account="测试账号/角色(20001)",
            )

        self.assertEqual(result["status"], "成功")
        self.assertEqual(client.post.await_count, 2)
        retry_cookies = client.post.await_args_list[1].kwargs["cookies"]
        self.assertEqual(retry_cookies["cookie_token"], "fresh")


if __name__ == "__main__":
    unittest.main()
