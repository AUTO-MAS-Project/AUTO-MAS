"""Local-only handshake authentication for privileged WebSocket routes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import urlsplit

AUTH_SUBPROTOCOL_PREFIX = "auto-mas-auth."
_AUTH_PURPOSE = b"AUTO-MAS/main-websocket/v2"


def create_auth_token(owner_token: str) -> str:
    """Create a process-scoped WS secret without exposing the ownership token."""

    normalized = str(owner_token or "").strip()
    if normalized:
        return hmac.new(
            normalized.encode("utf-8"),
            _AUTH_PURPOSE,
            hashlib.sha256,
        ).hexdigest()
    return secrets.token_hex(32)


def build_auth_subprotocol(auth_token: str) -> str:
    return f"{AUTH_SUBPROTOCOL_PREFIX}{auth_token}"


def is_loopback_host(host: str | None) -> bool:
    normalized = str(host or "").strip().lower()
    if normalized in {"localhost", "testclient"}:
        # ``testclient`` is Starlette's in-process transport address.
        return True
    if not normalized:
        return False
    try:
        address = ipaddress.ip_address(normalized.split("%", 1)[0])
        if address.is_loopback:
            return True
        mapped = getattr(address, "ipv4_mapped", None)
        return mapped is not None and mapped.is_loopback
    except ValueError:
        return False


def is_trusted_origin(origin: str | None) -> bool:
    """Allow Electron/file origins and loopback development frontends only."""

    if origin is None:
        # Native local probes (Electron main process/TestClient) omit Origin.
        return True
    normalized = origin.strip().lower()
    if normalized in {"", "null"} or normalized.startswith("file:"):
        return True
    parsed = urlsplit(normalized)
    return parsed.scheme in {"http", "https"} and is_loopback_host(parsed.hostname)


def is_trusted_local_peer(client_host: str | None, origin: str | None) -> bool:
    return is_loopback_host(client_host) and is_trusted_origin(origin)


def select_authenticated_subprotocol(
    offered_header: str | None,
    expected_token: str,
) -> str | None:
    """Return the matching protocol to echo during accept, otherwise reject."""

    expected = build_auth_subprotocol(expected_token)
    for offered in str(offered_header or "").split(","):
        candidate = offered.strip()
        if candidate and hmac.compare_digest(candidate, expected):
            return candidate
    return None


def authenticate_websocket_subprotocol(
    websocket: object,
    expected_token: str,
) -> str | None:
    """Authenticate a loopback WebSocket request and return its protocol echo."""

    client = getattr(websocket, "client", None)
    client_host = getattr(client, "host", None)
    headers = getattr(websocket, "headers", {})
    origin = headers.get("origin") if hasattr(headers, "get") else None
    if not is_trusted_local_peer(client_host, origin):
        return None
    offered = (
        headers.get("sec-websocket-protocol")
        if hasattr(headers, "get")
        else None
    )
    return select_authenticated_subprotocol(offered, expected_token)
