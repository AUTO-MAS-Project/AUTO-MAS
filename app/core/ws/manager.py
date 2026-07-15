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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

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
        self._connect_hooks: List[ConnectHook] = []
        self._hook_tasks: Set[asyncio.Task] = set()

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

        old_websocket = self._websocket
        self._websocket = websocket
        if old_websocket is not None:
            logger.warning("已存在主连接，旧连接将被新连接替换")
            with suppress(Exception):
                await old_websocket.close(code=1000, reason="被新连接替换")

        logger.info(f"主 WebSocket 已连接: {websocket.client}")
        self._run_connect_hooks()

        try:
            await self._receive_loop(websocket)
        finally:
            # 断开清理仅针对当前连接，避免被替换的旧连接清掉新连接
            if self._websocket is websocket:
                self._websocket = None
                logger.warning("主 WebSocket 已断开，等待前端重新连接")

    async def send(self, message: Dict[str, Any]) -> bool:
        """向主连接发送 JSON 消息。

        Args:
            message (Dict[str, Any]): 消息体。

        Returns:
            bool: 发送是否成功；未连接或发送异常时返回 False。
        """
        websocket = self._websocket
        if websocket is None:
            return False
        try:
            async with self._send_lock:
                await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"主 WebSocket 发送失败: {type(e).__name__}: {e}")
            return False

    async def close(self, code: int = 1000, reason: str = "正常关闭") -> None:
        """主动关闭主连接。"""
        websocket = self._websocket
        if websocket is None:
            return
        self._websocket = None
        with suppress(Exception):
            await websocket.close(code=code, reason=reason)

    async def _receive_loop(self, websocket: WebSocket) -> None:
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

            envelope = parse_envelope(raw)
            if envelope is not None:
                Dispatcher.dispatch(envelope)

    def _run_connect_hooks(self) -> None:
        """以持有的后台任务运行连接建立回调。"""
        for hook in self._connect_hooks:
            task = asyncio.create_task(hook())
            self._hook_tasks.add(task)

            def _on_done(done_task: asyncio.Task) -> None:
                self._hook_tasks.discard(done_task)
                if done_task.cancelled():
                    return
                exc = done_task.exception()
                if exc is not None:
                    logger.error(f"连接回调执行异常: {type(exc).__name__}: {exc}")

            task.add_done_callback(_on_done)


MainConnection = _MainConnectionManager()
