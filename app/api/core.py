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

from fastapi import APIRouter, Request, Response, WebSocket
from pydantic import BaseModel, Field

from app.core import Config, TaskManager
from app.core.lifecycle import shutdown_coordinator
from app.core.ws import Publisher, protocol
from app.core.ws.manager import ws_manager
from app.core.http_security import is_trusted_http_bootstrap_peer
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
    wsAuthToken: str | None = Field(
        default=None,
        description="仅向可信本地 Electron/开发前端返回的短期握手令牌",
    )


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
async def get_ws_meta(request: Request, response: Response) -> WebSocketMetaOut:
    """返回前端建立主 WebSocket 连接需要的元信息。"""

    client_host = request.client.host if request.client is not None else None
    trusted_local_peer = is_trusted_http_bootstrap_peer(
        client_host,
        request.headers.get("origin"),
    )
    response.headers["Cache-Control"] = "no-store"
    if trusted_local_peer and ws_manager.owner_token:
        response.headers["X-AUTO-MAS-Owner-Token"] = ws_manager.owner_token
        response.headers["X-AUTO-MAS-Owner-Pid"] = str(os.getpid())

    return WebSocketMetaOut(
        devMode=is_backend_dev_mode(),
        wsPath="/api/core/ws",
        wsAuthToken=ws_manager.auth_token if trusted_local_peer else None,
    )


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    """主 WebSocket 唯一入口，由 WSManager 管理替换和清理。"""

    await ws_manager.serve(websocket)


_shutdown_task: asyncio.Task[None] | None = None


async def _shutdown_backend() -> None:
    """完成清理、通知前端并请求 uvicorn 退出。"""

    if is_backend_dev_mode():
        with suppress(Exception):
            await TaskManager.stop_task("ALL")
        with suppress(RuntimeError):
            await System.cancel_power_task()
        await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.BACKEND_SHUTDOWN_READY,
        )
        logger.warning("后端开发模式下忽略退出，仅完成任务清理")
        return

    try:
        await shutdown_coordinator.run_teardown()
    except Exception as error:
        logger.exception(
            f"后端清理失败，取消发送退出完成信号: "
            f"{type(error).__name__}: {error}"
        )
        return

    await Publisher.send(
        id=protocol.ID_MAIN,
        type=protocol.BACKEND_SHUTDOWN_READY,
    )
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
    """启动幂等关闭流程；完成信号通过主 WebSocket 发送。"""

    global _shutdown_task

    if _shutdown_task is not None and not _shutdown_task.done():
        return OutBase(message="关闭流程已在进行中")

    _shutdown_task = asyncio.create_task(_shutdown_backend())

    def log_shutdown_failure(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(f"关闭流程异常: {type(error).__name__}: {error}")

    _shutdown_task.add_done_callback(log_shutdown_failure)
    return OutBase()
