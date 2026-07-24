"""按稳定 ``(id, type)`` 信封分发主 WebSocket 入站消息。"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.models.schema import WSEnvelope
from app.utils import get_logger

from . import protocol

logger = get_logger("WS分发器")

Handler = Callable[[WSEnvelope], Awaitable[Any] | Any]
CommandHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
SnapshotHandler = Callable[[WSEnvelope], Awaitable[dict[str, Any]] | dict[str, Any]]


class WSDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], list[Handler]] = {}
        self._command_handlers: dict[str, CommandHandler] = {}
        self._snapshot_handler: SnapshotHandler | None = None
        self._closed = False

    def reopen(self) -> None:
        self._closed = False

    def register(self, id: str, type: str, handler: Handler) -> Callable[[], None]:
        key = (id, type)
        self._handlers.setdefault(key, []).append(handler)

        def unregister() -> None:
            self.unregister(id, type, handler)

        return unregister

    def unregister(self, id: str, type: str, handler: Handler) -> None:
        key = (id, type)
        handlers = self._handlers.get(key)
        if handlers is None:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return
        if not handlers:
            self._handlers.pop(key, None)

    def subscribe(
        self,
        type: str,
        handler: Handler,
        *,
        id: str = "",
    ) -> Callable[[], None]:
        """兼容 Experimental Alpha 的事件订阅方法。"""

        return self.register(id, type, handler)

    def unsubscribe(self, type: str, handler: Handler, *, id: str = "") -> None:
        self.unregister(id, type, handler)

    def register_command(self, endpoint: str, handler: CommandHandler) -> None:
        self._command_handlers[endpoint] = handler

    def unregister_command(self, endpoint: str) -> None:
        self._command_handlers.pop(endpoint, None)

    def set_snapshot_handler(self, handler: SnapshotHandler | None) -> None:
        self._snapshot_handler = handler

    async def dispatch(self, envelope: WSEnvelope) -> WSEnvelope | None:
        if self._closed:
            return None

        if envelope.type == protocol.COMMAND:
            return await self._handle_command(envelope)

        if envelope.type == protocol.SNAPSHOT_REQUEST:
            return await self._handle_snapshot_request(envelope)

        handlers = list(self._handlers.get((envelope.id, envelope.type), ()))
        # 允许注册空 id 的 type 级兼容处理器。
        if envelope.id:
            handlers.extend(self._handlers.get(("", envelope.type), ()))

        for handler in handlers:
            try:
                result = handler(envelope)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning(
                    f"WS handler 异常: id={envelope.id}, type={envelope.type}, "
                    f"error={type(exc).__name__}: {exc}"
                )
        return None

    async def shutdown(self) -> None:
        self._closed = True

    async def _handle_command(self, envelope: WSEnvelope) -> WSEnvelope:
        endpoint = str(envelope.data.get("endpoint", ""))
        params = envelope.data.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        handler = self._command_handlers.get(endpoint)
        try:
            if handler is None:
                from app.api.ws_command import execute_ws_command

                result = await execute_ws_command(endpoint, params)
            else:
                result = await handler(endpoint, params)
                if not isinstance(result, dict):
                    result = {"success": True, "data": result, "code": 200}
                elif not {"success", "code"}.intersection(result):
                    result = {"success": True, "data": result, "code": 200}
        except Exception as exc:
            logger.error(f"WS 命令执行失败: endpoint={endpoint}, error={exc}")
            result = {
                "success": False,
                "data": None,
                "code": 500,
                "message": f"{type(exc).__name__}: {exc}",
            }

        return WSEnvelope(
            id=protocol.ID_CLIENT,
            type=protocol.COMMAND_RESPONSE,
            data={
                "endpoint": endpoint,
                "request_id": envelope.id,
                **result,
            },
        )

    async def _handle_snapshot_request(self, envelope: WSEnvelope) -> WSEnvelope:
        payload: dict[str, Any] = {}
        if self._snapshot_handler is not None:
            result = self._snapshot_handler(envelope)
            payload = await result if asyncio.iscoroutine(result) else result
        return WSEnvelope(
            id=envelope.id or protocol.ID_MAIN,
            type=protocol.SNAPSHOT_RESPONSE,
            data=payload,
        )


ws_dispatcher = WSDispatcher()
Dispatcher = ws_dispatcher
