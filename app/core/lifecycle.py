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
from datetime import datetime
from typing import Awaitable, Callable, Optional

from app.utils import get_logger

logger = get_logger("生命周期")

Teardown = Callable[[], Awaitable[None]]


class _ShutdownCoordinator:
    """后端关闭协调器。

    完整的非 WS teardown（停止任务、定时器、遥测等）只执行一次，
    供 `/close` 关闭流程与 uvicorn lifespan 收尾共用：
    - `/close` 先跑完整 teardown，成功后才向前端发 backend.shutdown.ready，
      再置 `should_exit`，避免前端在清理途中触发强制关闭。
    - lifespan yield 后再次调用（幂等），覆盖 taskkill 等未经 `/close` 的退出路径。
    """

    def __init__(self) -> None:
        self._teardown: Optional[Teardown] = None
        self._lock = asyncio.Lock()
        self._done = False
        self._exit_task: asyncio.Task[None] | None = None

    def request_exit(
        self,
        *,
        restart: bool = False,
        automatic: bool = False,
        next_wake_at: datetime | None = None,
        notify_frontend: bool = True,
    ) -> None:
        """独立持有退出流程；发起者不等待它，避免收尾反向取消发起者形成等待环。"""
        if self._exit_task is not None and not self._exit_task.done():
            return

        async def exit_application() -> None:
            from app.core import Config, Publisher
            from app.core.ws import protocol
            from app.models.schema import WSFrontendCloseRequestedData

            if notify_frontend:
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.FRONTEND_RESTART_REQUESTED
                    if restart
                    else protocol.FRONTEND_CLOSE_REQUESTED,
                    data=WSFrontendCloseRequestedData(
                        automatic=automatic, nextWakeAt=next_wake_at
                    ),
                )
            await self.run_teardown()
            await Publisher.send(
                id=protocol.ID_MAIN, type=protocol.BACKEND_SHUTDOWN_READY
            )
            if Config.server is not None:
                Config.server.should_exit = True

        self._exit_task = asyncio.create_task(
            exit_application(), name="application-exit"
        )

        def finished(task: asyncio.Task) -> None:
            if not task.cancelled() and (error := task.exception()) is not None:
                logger.opt(exception=error).error("应用退出收尾失败")

        self._exit_task.add_done_callback(finished)

    def set_teardown(self, teardown: Teardown) -> None:
        """注册完整 teardown 步骤（应用启动时调用一次）。"""
        self._teardown = teardown

    async def run_teardown(self) -> None:
        """执行完整 teardown，幂等：并发/重复调用只真正执行一次。

        Raises:
            Exception: teardown 步骤抛出的异常向上传播，供调用方决定是否发送
                完成信号。
        """
        async with self._lock:
            if self._done:
                return
            if self._teardown is None:
                logger.warning("未注册 teardown，跳过后端清理")
                self._done = True
                return
            # 仅在完整成功后置位：清理中途失败时保留可重试性，
            # 各 teardown 步骤本身幂等，重试不会重复副作用
            await self._teardown()
            self._done = True


ShutdownCoordinator = _ShutdownCoordinator()


__all__ = ["ShutdownCoordinator"]
