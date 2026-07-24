"""单条主 WebSocket 连接的生命周期封装。"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any

from app.utils import get_logger
from app.utils.ws_limits import (
    DEFAULT_WS_QUEUE_MESSAGES,
    DEFAULT_WS_SEND_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger("WS生命周期")


class ConnectionState(StrEnum):
    CONNECTING = auto()
    CONNECTED = auto()
    CLOSING = auto()
    CLOSED = auto()


@dataclass(slots=True)
class _OutboundItem:
    data: dict[str, Any]
    completion: asyncio.Future[bool]


class WSConnection:
    """持有一个 FastAPI WebSocket，并通过有界队列串行化所有发送。"""

    def __init__(
        self,
        websocket: "WebSocket",
        *,
        owner_token: str | None = None,
        backend_pid: int | None = None,
        max_outbound_queue_size: int = DEFAULT_WS_QUEUE_MESSAGES,
        send_timeout: float = DEFAULT_WS_SEND_TIMEOUT_SECONDS,
    ) -> None:
        self._websocket = websocket
        self._owner_token = owner_token
        self._backend_pid = backend_pid
        self._state = ConnectionState.CONNECTING
        self._send_timeout = max(0.001, float(send_timeout))
        self._outbound_queue: asyncio.Queue[_OutboundItem] = asyncio.Queue(
            maxsize=max(1, int(max_outbound_queue_size))
        )
        self._writer_task: asyncio.Task[None] | None = None
        self._close_lock = asyncio.Lock()
        self._connected_at = 0.0

    @property
    def websocket(self) -> "WebSocket":
        return self._websocket

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def owner_token(self) -> str | None:
        return self._owner_token

    @property
    def backend_pid(self) -> int | None:
        return self._backend_pid

    @property
    def connected_at(self) -> float:
        return self._connected_at

    @property
    def outbound_queue_size(self) -> int:
        return self._outbound_queue.qsize()

    async def accept(self, *, subprotocol: str | None = None) -> None:
        await self._websocket.accept(subprotocol=subprotocol)
        self._state = ConnectionState.CONNECTED
        self._connected_at = time.monotonic()
        self._writer_task = asyncio.create_task(self._send_loop())

    async def send_json(self, data: dict[str, Any]) -> bool:
        """排队并发送 JSON；队列满或超时时返回 ``False``。"""

        if not self.is_connected:
            return False

        completion: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        item = _OutboundItem(data=data, completion=completion)
        try:
            self._outbound_queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning(
                "主 WebSocket 出站队列已满，拒绝继续积压: "
                f"limit={self._outbound_queue.maxsize}"
            )
            return False

        try:
            return await asyncio.wait_for(
                completion,
                timeout=self._send_timeout,
            )
        except TimeoutError:
            logger.warning(
                f"主 WebSocket 发送超时: timeout={self._send_timeout:.3f}s"
            )
            return False

    async def receive_json(self) -> Any:
        return await self._websocket.receive_json()

    async def close(self, code: int = 1000, reason: str = "正常关闭") -> None:
        async with self._close_lock:
            if self._state == ConnectionState.CLOSED:
                return
            self._state = ConnectionState.CLOSING

            writer_task = self._writer_task
            self._writer_task = None
            if writer_task is not None and writer_task is not asyncio.current_task():
                writer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await writer_task

            self._fail_queued_sends()
            try:
                with suppress(Exception):
                    await self._websocket.close(code=code, reason=reason)
            finally:
                self._state = ConnectionState.CLOSED

    async def _send_loop(self) -> None:
        while self.is_connected:
            item = await self._outbound_queue.get()
            try:
                if item.completion.cancelled() or not self.is_connected:
                    if not item.completion.done():
                        item.completion.set_result(False)
                    continue

                try:
                    await self._websocket.send_json(item.data)
                except Exception as exc:
                    logger.warning(
                        f"主 WebSocket 发送失败: {type(exc).__name__}: {exc}"
                    )
                    if not item.completion.done():
                        item.completion.set_result(False)
                    # writer 已退出；队列内剩余待发消息不应等待 send_timeout，
                    # 立即解析为 False，避免 close 之前的无界等待。
                    self._fail_queued_sends()
                    await self.close(code=1011, reason="发送失败")
                    return

                if not item.completion.done():
                    item.completion.set_result(True)
            except asyncio.CancelledError:
                if not item.completion.done():
                    item.completion.set_result(False)
                raise
            finally:
                self._outbound_queue.task_done()

    def _fail_queued_sends(self) -> None:
        while True:
            try:
                item = self._outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not item.completion.done():
                item.completion.set_result(False)
            self._outbound_queue.task_done()
