#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
import asyncio
from contextlib import suppress
from typing import Awaitable, Callable, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import JsonValue

from .dispatcher import Dispatcher
from .protocol import parse_envelope
from app.utils.logger import get_logger

logger = get_logger("WS连接管理器")

ConnectHook = Callable[[], Awaitable[None]]


class _MainConnectionManager:
    """主 WebSocket 连接管理器，全应用唯一持有前端主连接。

    - 同一时间仅存在一条主连接，新连接到来时替换并关闭旧连接
    - 接收循环运行在 FastAPI 路由协程内，断开清理按连接实例判定，仅执行一次
    - 底层心跳依赖 WebSocket 协议层 ping/pong（uvicorn ws_ping_interval/ws_ping_timeout）
    """

    def __init__(self) -> None:
        self._websocket: Optional[WebSocket] = None
        self._send_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()
        self._closing = False
        self._generation = 0
        self._connect_hooks: List[ConnectHook] = []
        self._hook_tasks: Set[asyncio.Task[None]] = set()
        self._hook_task_owners: Dict[asyncio.Task[None], int] = {}

    @property
    def is_connected(self) -> bool:
        """当前是否存在主连接"""
        return self._websocket is not None

    def on_connect(self, hook: ConnectHook) -> None:
        """注册连接建立回调，应用启动时注册一次，每次主连接建立后触发。

        Args:
            hook (ConnectHook): 无参异步回调。
        """
        self._connect_hooks.append(hook)

    async def serve(self, websocket: WebSocket) -> None:
        """接管一条主连接：accept、替换旧连接、运行接收循环直至断开。

        Args:
            websocket (WebSocket): FastAPI 路由传入的连接对象。
        """
        await websocket.accept()

        reject_new_connection = False
        generation: int | None = None
        async with self._connection_lock:
            if self._closing:
                reject_new_connection = True
                old_websocket = None
            else:
                self._generation += 1
                generation = self._generation
                old_websocket = self._websocket
                self._websocket = websocket
                # 每代连接使用独立发送锁，旧连接的阻塞发送不能卡住新连接。
                self._send_lock = asyncio.Lock()

        if reject_new_connection:
            logger.info("主 WebSocket 正在关闭，拒绝新连接")
            with suppress(Exception):
                await websocket.close(code=1001, reason="后端正在关闭")
            return

        assert generation is not None

        if old_websocket is not None:
            logger.warning("已存在主连接，旧连接将被新连接替换")
            with suppress(Exception):
                await old_websocket.close(code=1000, reason="被新连接替换")

        logger.info(f"主 WebSocket 已连接: {websocket.client}")
        async with self._connection_lock:
            if not self._closing and self._websocket is websocket:
                self._run_connect_hooks(generation)

        try:
            await self._receive_loop(websocket, generation)
        finally:
            # 断开清理仅针对当前连接，避免被替换的旧连接清掉新连接
            async with self._connection_lock:
                if self._websocket is websocket:
                    self._websocket = None
                    logger.warning("主 WebSocket 已断开，等待前端重新连接")
            await self._cancel_hook_tasks_for(generation)
            await Dispatcher.cancel_owner(generation)

    async def send(self, message: Dict[str, JsonValue]) -> bool:
        """向主连接发送 JSON 消息。

        Args:
            message (Dict[str, JsonValue]): 消息体。

        Returns:
            bool: 发送是否成功；未连接或发送异常时返回 False。
        """
        websocket = self._websocket
        if websocket is None:
            return False
        send_lock = self._send_lock
        try:
            async with send_lock:
                if self._websocket is not websocket or self._send_lock is not send_lock:
                    return False
                await websocket.send_json(message)
                return self._websocket is websocket and self._send_lock is send_lock
        except Exception as e:
            logger.warning(f"主 WebSocket 发送失败: {type(e).__name__}: {e}")
            return False

    async def begin_shutdown(self) -> None:
        """进入终态关闭阶段，拒绝新连接与新连接回调。

        当前主连接保持可用，供 teardown 完成后发送 backend.shutdown.ready；
        实际连接关闭仍由服务器退出流程负责。
        """

        async with self._connection_lock:
            self._closing = True

    async def wait_until_disconnected(
        self, timeout: float = 10.0, poll_interval: float = 0.05
    ) -> bool:
        """等待当前前端主会话真正断开。

        用于会结束前端会话的系统电源操作：先发布关闭请求，再以主连接断开
        作为 renderer 已执行最终退出流程的可观测边界。连接被新连接替换时仍
        视为在线，必须等最新连接断开；超时返回 False，不创建常驻轮询任务。
        """

        if self._websocket is None:
            return True

        async def _wait() -> None:
            while self._websocket is not None:
                await asyncio.sleep(poll_interval)

        try:
            await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def cancel_hook_tasks(self) -> None:
        """取消并等待所有在途连接建立回调任务。

        关闭流程中在业务 teardown 前调用，确保 start_startup_queue 等回调
        不会与后端清理并发执行。
        """
        await self.begin_shutdown()
        await self._cancel_hook_tasks_for(None)

    async def _cancel_hook_tasks_for(self, generation: int | None) -> None:
        """取消并等待指定连接代次的 hook；None 表示关闭时清理全部。"""

        tasks = [
            task
            for task in self._hook_tasks
            if generation is None or self._hook_task_owners.get(task) == generation
        ]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for task in tasks:
            self._hook_tasks.discard(task)
            self._hook_task_owners.pop(task, None)

    async def _receive_loop(self, websocket: WebSocket, generation: int) -> None:
        """接收循环：解析统一信封并交给 Dispatcher，非法消息丢弃。"""
        while True:
            try:
                raw = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as e:
                logger.warning(f"入站消息解析失败: {e}")
                continue
            except Exception as e:
                logger.warning(f"主 WebSocket 接收异常: {type(e).__name__}: {e}")
                break

            if self._websocket is not websocket:
                logger.debug("旧主连接收到替换后的尾帧，已丢弃")
                break

            envelope = parse_envelope(raw)
            if envelope is not None:
                Dispatcher.dispatch(envelope, owner=generation)

    def _run_connect_hooks(self, generation: int) -> None:
        """以持有的后台任务运行连接建立回调。"""
        if self._closing:
            return

        for hook in self._connect_hooks:
            task = asyncio.create_task(hook())
            self._hook_tasks.add(task)
            self._hook_task_owners[task] = generation

            def _on_done(done_task: asyncio.Task[None]) -> None:
                self._hook_tasks.discard(done_task)
                self._hook_task_owners.pop(done_task, None)
                if done_task.cancelled():
                    return
                exc = done_task.exception()
                if exc is not None:
                    logger.error(f"连接回调执行异常: {type(exc).__name__}: {exc}")

            task.add_done_callback(_on_done)


MainConnection = _MainConnectionManager()
