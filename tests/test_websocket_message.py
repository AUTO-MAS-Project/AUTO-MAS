import asyncio

from app.api.core import connect_websocket
from app.core.config import Config


class ClosedWebSocket:
    async def send_json(self, data: dict) -> None:
        raise RuntimeError('Cannot call "send" once a close message has been sent.')


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
    Config.websocket = ClosedWebSocket()
    try:
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
