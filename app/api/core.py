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
from typing import Any, cast
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import Config, Broadcast, TaskManager
from app.services import System
from app.contracts.common_contract import OutBase
from app.models.shared import WebSocketMessage
from app.api.ws_command import ws_command
from app.utils import get_logger

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


def is_backend_dev_mode() -> bool:
    """判断后端是否处于开发模式。"""

    raw = str(os.getenv("AUTO_MAS_DEV", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    if Config.websocket is not None:
        await websocket.close(code=1000, reason="已有连接")
        return

    await websocket.accept()
    Config.websocket = websocket
    last_pong = time.monotonic()
    last_ping = time.monotonic()
    data: dict[str, Any] = {}

    asyncio.create_task(TaskManager.start_startup_queue())

    while True:
        try:
            payload = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
            if not isinstance(payload, dict):
                continue
            data = cast(dict[str, Any], payload)
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

        except WebSocketDisconnect:
            break

    Config.websocket = None
    if is_backend_dev_mode():
        logger.warning("后端开发模式下检测到 WS 断链，跳过 KillSelf 自动退出")
    else:
        await System.set_power("KillSelf", from_frontend=True)


@router.websocket("/ws/web")
async def connect_websocket_web(websocket: WebSocket):
    """Web 端 WebSocket 连接：支持多连接，断开不影响后端生命周期"""
    await websocket.accept()
    Config.web_connections.add(websocket)
    logger.info(f"Web 客户端已连接，当前 Web 连接数: {len(Config.web_connections)}")

    last_pong = time.monotonic()
    last_ping = time.monotonic()

    while True:
        try:
            payload = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            if not isinstance(payload, dict):
                continue
            data = cast(dict[str, Any], payload)
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

        except WebSocketDisconnect:
            break

        except Exception:
            break

    Config.web_connections.discard(websocket)
    logger.info(f"Web 客户端已断开，剩余 Web 连接数: {len(Config.web_connections)}")


@ws_command("core.close")
@router.post(
    "/close",
    summary="关闭后端程序",
    response_model=OutBase,
)
async def close() -> OutBase:
    """关闭后端程序"""

    if Config.websocket is not None:
        await Config.websocket.close(code=1000, reason="正常关闭")
    await System.set_power("KillSelf", from_frontend=True)
    return OutBase()
