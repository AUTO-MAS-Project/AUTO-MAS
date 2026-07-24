"""Process-local HTTP security for the AUTO-MAS loopback API."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.ws.security import is_loopback_host

HTTP_AUTH_HEADER = "X-AUTO-MAS-Auth-Token"
HTTP_AUTH_HEADER_BYTES = HTTP_AUTH_HEADER.lower().encode("ascii")
UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# ``null`` is Electron's production file-origin serialization.  It is safe for
# authenticated API calls, but never sufficient to obtain the secret itself.
LOCAL_CORS_ORIGINS = ("null",)
LOCAL_CORS_ORIGIN_REGEX = (
    r"(?i)^(?:file:(?://.*)?|https?://(?:localhost|127(?:\.\d{1,3}){3}|\[::1\])"
    r"(?::\d{1,5})?)$"
)


def is_trusted_http_bootstrap_peer(
    client_host: str | None,
    origin: str | None,
) -> bool:
    """Allow token bootstrap only to native clients or loopback web origins.

    A sandboxed remote page can deliberately serialize its origin as ``null``.
    Electron renderers therefore receive the token through the preload IPC
    bridge instead of reading it directly from the HTTP metadata response.
    """

    if not is_loopback_host(client_host):
        return False
    if origin is None:
        return True

    normalized = origin.strip().lower()
    if not normalized:
        return False
    return is_trusted_http_origin(normalized, allow_file_origin=False)


def is_trusted_http_origin(
    origin: str | None,
    *,
    allow_file_origin: bool = True,
) -> bool:
    """Validate the complete serialized Origin, not only its hostname."""

    if origin is None:
        return True
    normalized = origin.strip().lower()
    if normalized == "null":
        return allow_file_origin
    if normalized.startswith("file:"):
        return allow_file_origin
    if not normalized:
        return False

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not is_loopback_host(parsed.hostname):
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    try:
        parsed.port
    except ValueError:
        return False
    return True


class LocalHTTPSecurityMiddleware:
    """Reject non-local origins and authenticate every state-changing request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_token_provider: Callable[[], str],
    ) -> None:
        self.app = app
        self.auth_token_provider = auth_token_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", ()))
        raw_origin = headers.get(b"origin")
        origin = raw_origin.decode("latin-1") if raw_origin is not None else None
        client = scope.get("client")
        client_host = client[0] if client else None

        if not is_loopback_host(client_host) or not is_trusted_http_origin(origin):
            await self._reject(
                scope,
                receive,
                send,
                status_code=403,
                detail="HTTP requests are limited to trusted local origins",
            )
            return

        method = str(scope.get("method", "GET")).upper()
        if method in UNSAFE_HTTP_METHODS:
            supplied_token = headers.get(HTTP_AUTH_HEADER_BYTES, b"").decode(
                "latin-1"
            )
            expected_token = str(self.auth_token_provider() or "")
            if not expected_token or not hmac.compare_digest(
                supplied_token,
                expected_token,
            ):
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=401,
                    detail="Missing or invalid AUTO-MAS HTTP authentication token",
                )
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(
            {"detail": detail},
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


def configure_local_http_security(
    app: FastAPI,
    *,
    auth_token_provider: Callable[[], str],
) -> None:
    """Install strict local CORS plus enforcement for actual HTTP requests."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_CORS_ORIGINS),
        allow_origin_regex=LOCAL_CORS_ORIGIN_REGEX,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Authorization",
            "Cache-Control",
            "Content-Language",
            "Content-Type",
            "Pragma",
            "Range",
            "X-Requested-With",
            HTTP_AUTH_HEADER,
        ],
    )
    # Added after CORS so this middleware is outermost and rejects malicious
    # preflight requests before Starlette can return a permissive response.
    app.add_middleware(
        LocalHTTPSecurityMiddleware,
        auth_token_provider=auth_token_provider,
    )
