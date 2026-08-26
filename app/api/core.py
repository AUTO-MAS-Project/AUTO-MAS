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


import time
import asyncio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core import Config, Broadcast, TaskManager
from app.services import System
from app.models.schema import *
from app.api.ws_command import ws_command
from app.utils import get_logger

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


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


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):

    if Config.websocket is not None:
        await websocket.close(code=1000, reason="已有连接")
        return

    await websocket.accept()
    Config.websocket = websocket
    last_pong = time.monotonic()
    last_ping = time.monotonic()
    data = {}

    asyncio.create_task(TaskManager.start_startup_queue())
    try:
        while True:

            try:

                data = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
                if data.get("type") == "Signal" and "Pong" in data.get("data", {}):
                    last_pong = time.monotonic()
                elif data.get("type") == "Signal" and "Ping" in data.get("data", {}):
                    await websocket.send_json(
                        WebSocketMessage(
                            id="Main", type="Signal", data={"Pong": "无描述"}
                        ).model_dump()
                    )
                else:
                    await Broadcast.put(data)

            except asyncio.TimeoutError:

                if last_pong < last_ping:
                    await websocket.close(code=1000, reason="Ping超时")
                    break
                await websocket.send_json(
                    WebSocketMessage(
                        id="Main", type="Signal", data={"Ping": "无描述"}
                    ).model_dump()
                )
                last_ping = time.monotonic()
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.warning(f"主 WebSocket 通信失败: {type(e).__name__}: {e}")
    finally:
        if Config.websocket is websocket:
            Config.websocket = None
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
        await System.set_power("KillSelf", from_frontend=True)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
