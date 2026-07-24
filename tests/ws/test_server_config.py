from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from main import (
    UVICORN_WS_MAX_MESSAGE_BYTES,
    UVICORN_WS_MAX_QUEUE_MESSAGES,
    UVICORN_WS_PING_INTERVAL_SECONDS,
    UVICORN_WS_PING_TIMEOUT_SECONDS,
    build_uvicorn_config,
)
from app.core.ws.protocol import DEFAULT_MAX_MESSAGE_BYTES
from app.utils.ws_limits import (
    DEFAULT_WS_MAX_MESSAGE_BYTES,
    DEFAULT_WS_QUEUE_MESSAGES,
)


class FakeConfig:
    def __init__(self, app: object, **kwargs: object) -> None:
        self.app = app
        self.kwargs = kwargs


class TestServerConfig(TestCase):
    def test_protocol_ping_is_explicit(self) -> None:
        app = object()
        config = build_uvicorn_config(SimpleNamespace(Config=FakeConfig), app)

        self.assertIs(config.app, app)
        self.assertEqual(config.kwargs["host"], "127.0.0.1")
        self.assertEqual(config.kwargs["port"], 36163)
        self.assertEqual(
            config.kwargs["ws_max_size"],
            UVICORN_WS_MAX_MESSAGE_BYTES,
        )
        self.assertEqual(
            config.kwargs["ws_max_queue"],
            UVICORN_WS_MAX_QUEUE_MESSAGES,
        )
        self.assertEqual(
            config.kwargs["ws_ping_interval"],
            UVICORN_WS_PING_INTERVAL_SECONDS,
        )
        self.assertEqual(
            config.kwargs["ws_ping_timeout"],
            UVICORN_WS_PING_TIMEOUT_SECONDS,
        )
        self.assertEqual(UVICORN_WS_MAX_MESSAGE_BYTES, DEFAULT_MAX_MESSAGE_BYTES)
        self.assertEqual(UVICORN_WS_MAX_MESSAGE_BYTES, DEFAULT_WS_MAX_MESSAGE_BYTES)
        self.assertEqual(UVICORN_WS_MAX_QUEUE_MESSAGES, DEFAULT_WS_QUEUE_MESSAGES)
        self.assertEqual(UVICORN_WS_PING_INTERVAL_SECONDS, 20.0)
        self.assertEqual(UVICORN_WS_PING_TIMEOUT_SECONDS, 20.0)
