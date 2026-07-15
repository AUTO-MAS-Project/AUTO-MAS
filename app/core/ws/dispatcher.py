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


import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Set, Tuple, Union

from app.models.schema import WSEnvelope
from app.utils.logger import get_logger

logger = get_logger("WS分发器")

Handler = Callable[[WSEnvelope], Union[Awaitable[Any], Any]]


class _WSDispatcher:
    """按 (id, type) 分发主连接入站消息。

    - 处理器由后端模块注册/注销，同一 (id, type) 可注册多个，按注册顺序调用
    - 未找到处理器的消息记录低级别日志后直接丢弃，不缓存
    - 异步处理器以持有的后台任务运行，单个处理器异常不影响其他处理器
    """

    def __init__(self) -> None:
        self._handlers: Dict[Tuple[str, str], List[Handler]] = {}
        self._tasks: Set[asyncio.Task] = set()

    def register(self, id: str, type: str, handler: Handler) -> Callable[[], None]:
        """注册消息处理器。

        Args:
            id (str): 路由 ID。
            type (str): 消息类别。
            handler (Handler): 同步或异步处理器，入参为 WSEnvelope。

        Returns:
            Callable[[], None]: 幂等的注销函数。
        """
        key = (id, type)
        self._handlers.setdefault(key, []).append(handler)

        def _unregister() -> None:
            self.unregister(id, type, handler)

        return _unregister

    def unregister(self, id: str, type: str, handler: Handler) -> None:
        """注销消息处理器，重复注销安全。"""
        key = (id, type)
        handlers = self._handlers.get(key)
        if handlers is None or handler not in handlers:
            return
        handlers.remove(handler)
        if not handlers:
            del self._handlers[key]

    def dispatch(self, envelope: WSEnvelope) -> None:
        """分发一条入站消息给所有匹配处理器。"""
        handlers = list(self._handlers.get((envelope.id, envelope.type), ()))
        if not handlers:
            logger.debug(f"无处理器，丢弃入站消息: id={envelope.id}, type={envelope.type}")
            return
        for handler in handlers:
            self._invoke(handler, envelope)

    async def shutdown(self) -> None:
        """取消并等待所有在途处理器任务。"""
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def _invoke(self, handler: Handler, envelope: WSEnvelope) -> None:
        """调用处理器并隔离异常，协程结果放入持有的后台任务。"""
        try:
            result = handler(envelope)
        except Exception as e:
            logger.error(f"处理器执行异常({envelope.id}/{envelope.type}): {type(e).__name__}: {e}")
            return

        if not asyncio.iscoroutine(result):
            return

        task = asyncio.create_task(result)
        self._tasks.add(task)

        def _on_done(done_task: asyncio.Task) -> None:
            self._tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                logger.error(
                    f"处理器任务异常({envelope.id}/{envelope.type}): {type(exc).__name__}: {exc}"
                )

        task.add_done_callback(_on_done)


Dispatcher = _WSDispatcher()
