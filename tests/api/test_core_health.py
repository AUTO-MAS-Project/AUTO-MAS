import unittest
from unittest.mock import patch

from app.api.core import get_health, router
from app.core import Config


class CoreHealthApiTest(unittest.IsolatedAsyncioTestCase):
    def test_health_route_is_registered(self) -> None:
        route = next(
            (route for route in router.routes if route.path == "/api/core/health"),
            None,
        )

        self.assertIsNotNone(route)
        self.assertIn("GET", route.methods)

    async def test_managed_health_echoes_runtime_identity(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AUTO_MAS_SUPERVISED": "1",
                "AUTO_MAS_RUNTIME_PROTOCOL": "1",
                "AUTO_MAS_EXPECTED_VERSION": "v9.9.9-alpha.1",
                "AUTO_MAS_EXPECTED_COMMIT": "0123456789abcdef0123456789abcdef01234567",
            },
            clear=True,
        ):
            response = await get_health()

        self.assertTrue(response.ready)
        self.assertEqual(response.backgroundStatus, "ready")
        self.assertIsNone(response.backgroundError)
        self.assertEqual(response.protocol, 1)
        self.assertEqual(response.version, "v9.9.9-alpha.1")
        self.assertEqual(
            response.commit,
            "0123456789abcdef0123456789abcdef01234567",
        )

    async def test_development_health_uses_backend_identity(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AUTO_MAS_SUPERVISED": "1",
                "AUTO_MAS_RUNTIME_PROTOCOL": "1",
            },
            clear=True,
        ):
            response = await get_health()

        self.assertEqual(response.protocol, 1)
        self.assertEqual(response.version, Config.VERSION)
        self.assertEqual(response.commit, "")

    async def test_unsupervised_health_ignores_expected_identity(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AUTO_MAS_RUNTIME_PROTOCOL": "999",
                "AUTO_MAS_EXPECTED_VERSION": "v0.0.0-forged",
                "AUTO_MAS_EXPECTED_COMMIT": "f" * 40,
            },
            clear=True,
        ):
            response = await get_health()

        self.assertEqual(response.protocol, 1)
        self.assertEqual(response.version, Config.VERSION)
        self.assertEqual(response.commit, "")


if __name__ == "__main__":
    unittest.main()
