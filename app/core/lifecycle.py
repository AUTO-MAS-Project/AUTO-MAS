#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

"""应用级生命周期协调。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.utils import get_logger

logger = get_logger("生命周期")

Teardown = Callable[[], Awaitable[None]]


class ShutdownCoordinator:
    """串行、幂等地执行后端退出前清理。

    `/api/core/close` 与 FastAPI lifespan 可能同时触发退出。协调器保证完整
    清理只成功执行一次；失败不会锁死状态，后续调用仍可重试。
    """

    def __init__(self) -> None:
        self._teardown: Teardown | None = None
        self._lock = asyncio.Lock()
        self._done = False

    def set_teardown(self, teardown: Teardown) -> None:
        """为当前应用生命周期注册清理流程。"""

        self._teardown = teardown
        self._done = False

    def clear_teardown(self) -> None:
        """清除已结束生命周期的回调，避免持有旧应用状态。"""

        self._teardown = None
        self._done = False

    @property
    def completed(self) -> bool:
        return self._done

    async def run_teardown(self) -> None:
        """执行清理；并发调用共享同一临界区，失败可重试。"""

        async with self._lock:
            if self._done:
                return
            if self._teardown is None:
                logger.warning("未注册后端清理流程，跳过退出前清理")
                return

            await self._teardown()
            self._done = True


shutdown_coordinator = ShutdownCoordinator()
