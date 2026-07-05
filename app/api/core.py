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


import os
import time
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core import Config, Broadcast, TaskManager
from app.services import System
from app.models.schema import *
from app.api.ws_command import ws_command
from app.utils import get_logger
from app.utils.websocket import ws_client_manager

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


class WebSocketMetaOut(BaseModel):
    """前端协商主 WebSocket 链接时使用的元信息。"""

    devMode: bool = Field(description="后端当前是否处于开发模式")
    wsPath: str = Field(default="/api/core/ws", description="主 WebSocket 路径")


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


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):

    if Config.websocket is not None:
        await websocket.close(code=1000, reason="已有连接")
        return

    await websocket.accept()
    Config.websocket = None

    async def on_message(data: dict):
        await Broadcast.put(data)

    async def on_disconnect():
        Config.websocket = None

    session = await ws_client_manager.openwsr(
        name=ws_client_manager.MAIN_CLIENT_NAME,
        websocket=websocket,
        ping_interval=15.0,
        ping_timeout=30.0,
        on_message=on_message,
        on_disconnect=on_disconnect,
    )

    Config.websocket = session
    asyncio.create_task(TaskManager.start_startup_queue())
    await session.wait_closed()
    logger.warning("主 WebSocket 已断开，等待前端重新连接")


@ws_command("core.close")
@router.post(
    "/close",
    summary="关闭后端程序",
    response_model=OutBase,
    status_code=200,
)
async def close() -> OutBase:
    """关闭后端程序"""

    try:
        if Config.websocket is not None:
            await Config.websocket.close(code=1000, reason="正常关闭")
        if is_backend_dev_mode():
            logger.warning("后端开发模式下忽略 /api/core/close 的 KillSelf 请求")
            return OutBase(message="开发模式下已忽略关闭请求")
        await System.set_power("KillSelf", from_frontend=True)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
