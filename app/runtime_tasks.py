"""应用级短生命周期后台任务所有权。

仅用于原本需要 fire-and-forget 的短任务。长期服务仍由各自组件持有；进程关闭时
本注册表会拒绝新任务，并取消、等待全部在途任务，避免 teardown 后继续访问资源。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar


logger = logging.getLogger("AUTO-MAS运行时后台任务")
T = TypeVar("T")


class OwnedTaskRegistry:
    """持有 fire-and-forget 任务并提供幂等 shutdown。"""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closing = False

    def spawn(
        self, coroutine: Coroutine[Any, Any, T], *, name: str
    ) -> asyncio.Task[T] | None:
        """创建并持有任务；关闭开始后拒绝新任务并关闭协程对象。"""

        if self._closing:
            coroutine.close()
            logger.debug("后台任务注册表已关闭，拒绝新任务: %s", name)
            return None

        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)

        def _on_done(done_task: asyncio.Task[Any]) -> None:
            self._tasks.discard(done_task)
            if done_task.cancelled():
                return
            try:
                error = done_task.exception()
            except asyncio.CancelledError:
                return
            if error is not None:
                logger.error(
                    "后台任务 %s 执行失败: %s: %s",
                    done_task.get_name(),
                    type(error).__name__,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

        task.add_done_callback(_on_done)
        return task

    async def shutdown(self) -> None:
        """取消并等待全部在途任务；幂等。"""

        self._closing = True
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


RuntimeTasks = OwnedTaskRegistry()


__all__ = ["OwnedTaskRegistry", "RuntimeTasks"]
