import unittest
from unittest.mock import patch

from app.tools.skland import _create_skland_client


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


if __name__ == "__main__":
    unittest.main()
