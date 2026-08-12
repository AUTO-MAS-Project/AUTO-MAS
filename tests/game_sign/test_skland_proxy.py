import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.tools.skland import _create_skland_client, skland_sign_in


class SklandHttpClientTest(unittest.TestCase):
    def test_default_client_ignores_environment_proxy(self) -> None:
        with patch("app.tools.skland.httpx.AsyncClient") as client:
            _create_skland_client()

        client.assert_called_once_with(proxy=None, trust_env=False)

    def test_explicit_proxy_does_not_enable_environment_proxy(self) -> None:
        with patch("app.tools.skland.httpx.AsyncClient") as client:
            _create_skland_client("http://127.0.0.1:7890")

        client.assert_called_once_with(
            proxy="http://127.0.0.1:7890",
            trust_env=False,
        )


class SklandConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_sign_in_calls_are_serialized_across_callers(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def run_once(*args: object, **kwargs: object) -> dict:
            started.set()
            await release.wait()
            return {"status": "ok"}

        with patch(
            "app.tools.skland._run_skland_sign_in",
            new=AsyncMock(side_effect=run_once),
        ) as run_sign:
            first = asyncio.create_task(skland_sign_in("first"))
            await started.wait()
            second = asyncio.create_task(skland_sign_in("second"))
            await asyncio.sleep(0)

            self.assertEqual(run_sign.await_count, 1)
            release.set()
            self.assertEqual(await first, {"status": "ok"})
            self.assertEqual(await second, {"status": "ok"})

        self.assertEqual(run_sign.await_count, 2)


if __name__ == "__main__":
    unittest.main()
