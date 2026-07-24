"""全应用唯一的主 WebSocket 连接管理器。"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import WebSocketDisconnect

from app.utils import get_logger
from app.utils.ws_limits import (
    DEFAULT_WS_MAX_MESSAGE_BYTES,
    DEFAULT_WS_QUEUE_MESSAGES,
    DEFAULT_WS_SEND_TIMEOUT_SECONDS,
)

from . import protocol
from .lifecycle import WSConnection
from .security import (
    authenticate_websocket_subprotocol,
    create_auth_token,
)

if TYPE_CHECKING:
    from fastapi import WebSocket

    from .dispatcher import WSDispatcher

logger = get_logger("WS连接管理器")

ConnectHook = Callable[[], Awaitable[None]]
DisconnectHook = Callable[[], Awaitable[None] | None]


class WSManager:
    """持有主连接、处理替换竞态并运行统一接收循环。"""

    def __init__(
        self,
        *,
        sync_config_compat: bool = True,
        auth_token: str | None = None,
        max_inflight_messages: int = DEFAULT_WS_QUEUE_MESSAGES,
        max_outbound_queue_size: int = DEFAULT_WS_QUEUE_MESSAGES,
        send_timeout: float = DEFAULT_WS_SEND_TIMEOUT_SECONDS,
        max_message_bytes: int = DEFAULT_WS_MAX_MESSAGE_BYTES,
    ) -> None:
        self._connection: WSConnection | None = None
        self._connection_lock = asyncio.Lock()
        self._connect_hooks: list[ConnectHook] = []
        self._disconnect_hooks: list[DisconnectHook] = []
        self._hook_tasks: set[asyncio.Task] = set()
        self._dispatcher: "WSDispatcher | None" = None
        self._backend_pid = os.getpid()
        self._owner_token = str(os.getenv("AUTO_MAS_BACKEND_OWNER_TOKEN", "")).strip()
        self._auth_token_is_explicit = auth_token is not None
        self._auth_token = auth_token or create_auth_token(self._owner_token)
        self._inflight_messages: dict[WSConnection, set[asyncio.Task[None]]] = {}
        self._dispatch_lock = asyncio.Lock()
        self._max_inflight_messages = max(1, int(max_inflight_messages))
        self._max_outbound_queue_size = max(1, int(max_outbound_queue_size))
        self._send_timeout = max(0.001, float(send_timeout))
        self._max_message_bytes = max(1, int(max_message_bytes))
        self._sync_config_compat = sync_config_compat

    @property
    def connection(self) -> WSConnection | None:
        return self._connection

    @property
    def is_connected(self) -> bool:
        connection = self._connection
        return connection is not None and connection.is_connected

    @property
    def backend_pid(self) -> int:
        return self._backend_pid

    @property
    def owner_token(self) -> str:
        return self._owner_token

    @property
    def auth_token(self) -> str:
        return self._auth_token

    def set_owner_token(self, token: str) -> None:
        self._owner_token = str(token or "")
        if not self._auth_token_is_explicit:
            self._auth_token = create_auth_token(self._owner_token)

    def set_dispatcher(self, dispatcher: "WSDispatcher") -> None:
        self._dispatcher = dispatcher

    def on_connect(self, hook: ConnectHook) -> Callable[[], None]:
        self._connect_hooks.append(hook)

        def unregister() -> None:
            with suppress(ValueError):
                self._connect_hooks.remove(hook)

        return unregister

    def on_disconnect(self, hook: DisconnectHook) -> Callable[[], None]:
        self._disconnect_hooks.append(hook)

        def unregister() -> None:
            with suppress(ValueError):
                self._disconnect_hooks.remove(hook)

        return unregister

    async def serve(self, websocket: "WebSocket") -> None:
        """接管连接；新连接原子替换旧连接，旧协程不得清掉新连接。"""

        selected_subprotocol = self._authenticate(websocket)
        if selected_subprotocol is None:
            logger.warning("拒绝未通过本地握手认证的主 WebSocket 连接")
            await websocket.close(code=1008, reason="authentication required")
            return

        connection = WSConnection(
            websocket,
            owner_token=self._owner_token or None,
            backend_pid=self._backend_pid,
            max_outbound_queue_size=self._max_outbound_queue_size,
            send_timeout=self._send_timeout,
        )
        await connection.accept(subprotocol=selected_subprotocol)

        async with self._connection_lock:
            old_connection = self._connection
            self._connection = connection
            self._set_config_compat(connected=True)

        if old_connection is not None and old_connection is not connection:
            logger.warning("已有主连接，新连接将替换旧连接")
            await old_connection.close(
                code=protocol.CONNECTION_REPLACED_CLOSE_CODE,
                reason=protocol.CONNECTION_REPLACED_CLOSE_REASON,
            )

        # 关闭旧连接期间可能已有更新连接再次接管；被更新的中间连接不得
        # 触发快照/启动队列 hook，也无需进入接收循环。
        if not self._is_current(connection):
            return

        logger.info("主 WebSocket 已连接")
        self._run_connect_hooks(connection)

        try:
            await self._receive_loop(connection)
        finally:
            # 被替换的旧 serve 协程只能清理自己，不能清掉当前新连接。
            detached = await self._detach_if_current(connection)
            await connection.close(code=1000, reason="连接结束")
            if detached:
                logger.warning("主 WebSocket 已断开，等待前端重新连接")

    async def send_json(self, data: dict[str, Any]) -> bool:
        """向当前主连接发送 JSON，返回是否成功。"""

        connection = self._connection
        if connection is None:
            return False
        return await self._send_to_connection(connection, data)

    async def _send_to_connection(
        self,
        connection: WSConnection,
        data: dict[str, Any],
    ) -> bool:
        """只向指定来源连接发送，绝不在竞态中改投当前新连接。"""

        try:
            message_size = protocol.message_size_bytes(data)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "主 WebSocket 出站消息无法 JSON 序列化，已关闭来源连接: "
                f"{type(exc).__name__}: {exc}"
            )
            await self._detach_if_current(connection)
            await connection.close(code=1011, reason="invalid outbound message")
            return False

        if message_size > self._max_message_bytes:
            logger.warning(
                "主 WebSocket 出站消息超过上限，已关闭来源连接: "
                f"limit={self._max_message_bytes}"
            )
            await self._detach_if_current(connection)
            await connection.close(
                code=protocol.MESSAGE_TOO_BIG_CLOSE_CODE,
                reason=protocol.MESSAGE_TOO_BIG_CLOSE_REASON,
            )
            return False

        sent = await connection.send_json(data)
        if not sent:
            detached = await self._detach_if_current(connection)
            if detached:
                await connection.close(code=1011, reason="发送失败")
        return sent

    async def close_connection(
        self,
        code: int = 1000,
        reason: str = "正常关闭",
    ) -> None:
        connection = self._connection
        if connection is None:
            return
        detached = await self._detach_if_current(connection)
        await connection.close(code=code, reason=reason)
        if detached:
            logger.info(f"主 WebSocket 已关闭: {reason}")

    async def close(self, code: int = 1000, reason: str = "正常关闭") -> None:
        """兼容旧 ``Config.websocket.close``。"""

        await self.close_connection(code=code, reason=reason)

    async def cancel_hook_tasks(self) -> None:
        tasks = [task for task in self._hook_tasks if not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._hook_tasks.clear()

    async def shutdown(self) -> None:
        await self.cancel_hook_tasks()
        await self.close_connection(code=1001, reason="服务关闭")
        # A cancelled ``asyncio.to_thread(subprocess.run)`` does not stop the
        # child process. Drain accepted commands so plugin/runtime mutations
        # finish their invalidate/discover/publish tail before shutdown exits.
        await self._drain_all_inflight()

    async def _receive_loop(self, connection: WSConnection) -> None:
        while connection.is_connected:
            try:
                raw = await connection.receive_json()
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as exc:
                logger.warning(f"主 WebSocket JSON 解析失败: {exc}")
                continue
            except Exception as exc:
                logger.debug(f"主 WebSocket 接收结束: {type(exc).__name__}: {exc}")
                break

            try:
                message_size = protocol.message_size_bytes(raw)
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "主 WebSocket 入站消息无法按 JSON 计量，已丢弃: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if message_size > self._max_message_bytes:
                logger.warning(
                    "主 WebSocket 入站消息超过上限，已关闭连接: "
                    f"limit={self._max_message_bytes}"
                )
                await connection.close(
                    code=protocol.MESSAGE_TOO_BIG_CLOSE_CODE,
                    reason=protocol.MESSAGE_TOO_BIG_CLOSE_REASON,
                )
                break

            envelope = protocol.parse_envelope(raw)
            if envelope is None:
                continue

            # close 无法保证已在 receive_json 内取出的旧消息立即消失；替换后
            # 的旧连接消息不能再进入业务分发。
            if not self._is_current(connection):
                break

            signal_data = envelope.data if envelope.type == "Signal" else {}
            if "Ping" in signal_data:
                await self._send_to_connection(
                    connection,
                    protocol.build_message(
                        protocol.ID_MAIN,
                        "Signal",
                        {
                            "Pong": signal_data["Ping"],
                            **(
                                {"connectionId": signal_data["connectionId"]}
                                if "connectionId" in signal_data
                                else {}
                            ),
                        },
                    )
                )

            # Heartbeat has already been answered. Business dispatch is bounded and
            # tracked so a slow command/subscriber cannot stall the receive loop.
            if not self._schedule_inbound(connection, envelope):
                logger.warning("主 WebSocket 入站任务已达上限，拒绝新的业务消息")
                if envelope.type == protocol.COMMAND:
                    await self._send_overloaded_response(connection, envelope)

    def _authenticate(self, websocket: "WebSocket") -> str | None:
        return authenticate_websocket_subprotocol(
            websocket,
            self._auth_token,
        )

    def _schedule_inbound(
        self,
        connection: WSConnection,
        envelope: Any,
    ) -> bool:
        active_count = sum(len(tasks) for tasks in self._inflight_messages.values())
        if active_count >= self._max_inflight_messages:
            return False

        task = asyncio.create_task(self._dispatch_inbound(connection, envelope))
        connection_tasks = self._inflight_messages.setdefault(connection, set())
        connection_tasks.add(task)

        def on_done(done_task: asyncio.Task[None]) -> None:
            tasks = self._inflight_messages.get(connection)
            if tasks is not None:
                tasks.discard(done_task)
                if not tasks:
                    self._inflight_messages.pop(connection, None)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                logger.error(
                    "主 WebSocket 入站任务异常: "
                    f"{type(exc).__name__}: {exc}"
                )

        task.add_done_callback(on_done)
        return True

    async def _dispatch_inbound(self, connection: WSConnection, envelope: Any) -> None:
        async with self._dispatch_lock:
            if not self._is_current(connection):
                return

            from app.core.broadcast import Broadcast

            await Broadcast.put(envelope.model_dump())
            if not self._is_current(connection):
                return

            response = None
            if self._dispatcher is not None:
                response = await self._dispatcher.dispatch(envelope)
            if response is not None and self._is_current(connection):
                await self._send_to_connection(connection, response.model_dump())

    async def _send_overloaded_response(
        self,
        connection: WSConnection,
        envelope: Any,
    ) -> None:
        endpoint = str(envelope.data.get("endpoint", ""))
        await self._send_to_connection(
            connection,
            protocol.build_message(
                protocol.ID_CLIENT,
                protocol.COMMAND_RESPONSE,
                {
                    "endpoint": endpoint,
                    "request_id": envelope.id,
                    "success": False,
                    "data": None,
                    "code": 429,
                    "message": "too many pending WebSocket operations",
                },
            ),
        )

    async def _drain_all_inflight(self) -> None:
        current = asyncio.current_task()
        tasks = [
            task
            for connection_tasks in self._inflight_messages.values()
            for task in connection_tasks
            if task is not current and not task.done()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _is_current(self, connection: WSConnection) -> bool:
        return self._connection is connection and connection.is_connected

    async def _detach_if_current(self, connection: WSConnection) -> bool:
        async with self._connection_lock:
            if self._connection is not connection:
                return False
            self._connection = None
            self._set_config_compat(connected=False)

        await self._fire_disconnect_hooks()
        return True

    def _set_config_compat(self, *, connected: bool) -> None:
        if not self._sync_config_compat:
            return
        try:
            from app.core import Config

            if connected:
                Config.websocket = self
                Config._websocket_missing_logged = False
            elif Config.websocket is self:
                Config.websocket = None
        except Exception as exc:
            logger.debug(f"同步 Config.websocket 兼容门面失败: {exc}")

    def _run_connect_hooks(self, connection: WSConnection) -> None:
        for hook in tuple(self._connect_hooks):
            async def run_if_current(
                current_hook: ConnectHook = hook,
            ) -> None:
                if not self._is_current(connection):
                    return
                await current_hook()

            task = asyncio.create_task(run_if_current())
            self._hook_tasks.add(task)

            def on_done(done_task: asyncio.Task) -> None:
                self._hook_tasks.discard(done_task)
                if done_task.cancelled():
                    return
                exc = done_task.exception()
                if exc is not None:
                    logger.error(f"主连接 hook 异常: {type(exc).__name__}: {exc}")

            task.add_done_callback(on_done)

    async def _fire_disconnect_hooks(self) -> None:
        for hook in tuple(self._disconnect_hooks):
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning(f"主连接断开 hook 异常: {type(exc).__name__}: {exc}")


ws_manager = WSManager()
MainConnection = ws_manager
