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
import os
from contextlib import suppress
from typing import Optional

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel, Field

from app.core import Config, TaskManager
from app.core.ws import MainConnection, Publisher, protocol
from app.services import System
from app.models.schema import *
from app.api.ws_command import ws_command
from app.utils import get_logger

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


class WebSocketMetaOut(BaseModel):
    """前端协商主 WebSocket 链接时使用的元信息。"""

    devMode: bool = Field(description="后端当前是否处于开发模式")
    wsPath: str = Field(default="/api/core/ws", description="主 WebSocket 路径")


class BackendHealthOut(BaseModel):
    """后端核心服务与后台初始化状态。"""

    ready: bool = Field(description="核心 API 是否可用")
    backgroundStatus: str = Field(description="后台初始化状态")
    backgroundError: str | None = Field(default=None, description="后台初始化失败原因")


@router.get(
    "/health",
    summary="获取后端就绪状态",
    response_model=BackendHealthOut,
    status_code=200,
)
async def get_health(request: Request) -> BackendHealthOut:
    """返回核心 API 与后台初始化状态。"""

    return BackendHealthOut(
        ready=True,
        backgroundStatus=getattr(request.app.state, "background_status", "starting"),
        backgroundError=getattr(request.app.state, "background_error", None),
    )


def is_backend_dev_mode() -> bool:
    """判断后端是否处于开发模式。"""

    raw = str(os.getenv("AUTO_MAS_DEV", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@router.get(
    "/ws_meta",
    summary="获取主 WebSocket 元信息",
    response_model=WebSocketMetaOut,
    status_code=200,
)
async def get_ws_meta() -> WebSocketMetaOut:
    """返回前端建立主 WebSocket 连接需要的元信息。"""

    return WebSocketMetaOut(
        devMode=is_backend_dev_mode(),
        wsPath="/api/core/ws",
    )


# 主连接建立后触发启动时调度队列
MainConnection.on_connect(TaskManager.start_startup_queue)


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    """主 WebSocket 端点，接入后整体交给 MainConnection 管理。"""

    await MainConnection.serve(websocket)


# 关闭流程任务由模块持有，重复 /close 请求不重复触发
_shutdown_task: Optional[asyncio.Task] = None


async def _shutdown_backend() -> None:
    """后端正常关闭收尾：清理任务与资源，通知前端后退出。"""

    with suppress(Exception):
        await TaskManager.stop_task("ALL")
    with suppress(Exception):
        await System.cancel_power_task()

    # 清理完成后通过主 WS 通知前端可以退出
    await Publisher.send(id=protocol.ID_MAIN, type=protocol.BACKEND_SHUTDOWN_READY)

    if is_backend_dev_mode():
        logger.warning("后端开发模式下忽略退出请求，仅完成清理")
        return
    if Config.server is not None:
        Config.server.should_exit = True


@ws_command("core.close")
@router.post(
    "/close",
    summary="关闭后端程序",
    response_model=OutBase,
    status_code=200,
)
async def close() -> OutBase:
    """关闭后端程序：启动清理流程，完成后经主 WS 发送 backend.shutdown.ready"""

    global _shutdown_task

    if _shutdown_task is not None and not _shutdown_task.done():
        return OutBase(message="关闭流程已在进行中")

    _shutdown_task = asyncio.create_task(_shutdown_backend())

    def _on_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"关闭流程异常: {type(exc).__name__}: {exc}")

    _shutdown_task.add_done_callback(_on_done)
    return OutBase()
