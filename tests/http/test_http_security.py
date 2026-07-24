from __future__ import annotations

from unittest import TestCase

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.http_security import (
    HTTP_AUTH_HEADER,
    configure_local_http_security,
    is_trusted_http_bootstrap_peer,
)


AUTH_TOKEN = "a" * 64


def create_test_app() -> FastAPI:
    app = FastAPI()
    configure_local_http_security(
        app,
        auth_token_provider=lambda: AUTH_TOKEN,
    )

    @app.get("/api/state")
    async def read_state() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/state")
    async def mutate_state() -> dict[str, bool]:
        return {"changed": True}

    return app


class TestLocalHTTPSecurity(TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_test_app())

    def tearDown(self) -> None:
        self.client.close()

    def test_rejects_malicious_origin_preflight(self) -> None:
        response = self.client.options(
            "/api/state",
            headers={
                "Origin": "https://attacker.invalid",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": HTTP_AUTH_HEADER,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_rejects_malicious_origin_actual_post_even_with_token(self) -> None:
        response = self.client.post(
            "/api/state",
            headers={
                "Origin": "https://attacker.invalid",
                HTTP_AUTH_HEADER: AUTH_TOKEN,
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_rejects_trusted_origin_without_token(self) -> None:
        response = self.client.post(
            "/api/state",
            headers={"Origin": "http://localhost:5173"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("authentication token", response.json()["detail"])

    def test_allows_authenticated_electron_null_origin(self) -> None:
        response = self.client.post(
            "/api/state",
            headers={"Origin": "null", HTTP_AUTH_HEADER: AUTH_TOKEN},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"changed": True})
        self.assertEqual(response.headers["access-control-allow-origin"], "null")

    def test_allows_loopback_vite_preflight_and_authenticated_post(self) -> None:
        origin = "http://127.0.0.1:5173"
        preflight = self.client.options(
            "/api/state",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": HTTP_AUTH_HEADER,
            },
        )
        actual = self.client.post(
            "/api/state",
            headers={"Origin": origin, HTTP_AUTH_HEADER: AUTH_TOKEN},
        )

        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], origin)
        self.assertEqual(actual.status_code, 200)
        self.assertEqual(actual.headers["access-control-allow-origin"], origin)

    def test_safe_local_get_does_not_require_token(self) -> None:
        response = self.client.get(
            "/api/state",
            headers={"Origin": "http://localhost:5173"},
        )

        self.assertEqual(response.status_code, 200)


class TestHTTPTokenBootstrapBoundary(TestCase):
    def test_native_and_loopback_web_clients_can_bootstrap(self) -> None:
        self.assertTrue(is_trusted_http_bootstrap_peer("127.0.0.1", None))
        self.assertTrue(
            is_trusted_http_bootstrap_peer(
                "127.0.0.1",
                "http://localhost:5173",
            )
        )

    def test_file_and_null_origins_must_use_electron_ipc(self) -> None:
        self.assertFalse(is_trusted_http_bootstrap_peer("127.0.0.1", "null"))
        self.assertFalse(is_trusted_http_bootstrap_peer("127.0.0.1", "file:///app"))

    def test_non_loopback_peer_cannot_bootstrap(self) -> None:
        self.assertFalse(is_trusted_http_bootstrap_peer("192.0.2.10", None))
