import asyncio

from fastapi import WebSocketDisconnect

from app.api.core import connect_websocket
from app.core.config import Config


class ClosedWebSocket:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def send_json(self, data: dict) -> None:
        raise self.error


class HeartbeatDisconnectingWebSocket:
    def __init__(self) -> None:
        self.receive_count = 0

    async def accept(self) -> None:
        pass

    async def receive_json(self) -> dict:
        self.receive_count += 1
        if self.receive_count == 1:
            return {"type": "Signal", "data": {"Pong": "heartbeat"}}
        raise asyncio.TimeoutError

    async def send_json(self, data: dict) -> None:
        raise WebSocketDisconnect()


class ReplacedWebSocket:
    def __init__(self, replacement: object) -> None:
        self.replacement = replacement

    async def accept(self) -> None:
        pass

    async def receive_json(self) -> dict:
        Config.websocket = self.replacement
        raise RuntimeError('WebSocket is not connected.')


def test_disconnected_websocket_does_not_break_message_sender() -> None:
    previous_websocket = Config.websocket
    try:
        for error in (
            RuntimeError('Cannot call "send" once a close message has been sent.'),
            WebSocketDisconnect(),
        ):
            Config.websocket = ClosedWebSocket(error)
            asyncio.run(
                Config.send_websocket_message(
                    id="task-id",
                    type="Signal",
                    data={"Accomplish": "done"},
                )
            )
            assert Config.websocket is None
    finally:
        Config.websocket = previous_websocket


def test_disconnected_websocket_does_not_clear_replacement() -> None:
    previous_websocket = Config.websocket
    replacement = object()
    Config.websocket = None
    try:
        asyncio.run(connect_websocket(ReplacedWebSocket(replacement)))
        assert Config.websocket is replacement
    finally:
        Config.websocket = previous_websocket


def test_heartbeat_disconnect_clears_websocket() -> None:
    previous_websocket = Config.websocket
    Config.websocket = None
    try:
        asyncio.run(connect_websocket(HeartbeatDisconnectingWebSocket()))
        assert Config.websocket is None
    finally:
        Config.websocket = previous_websocket
