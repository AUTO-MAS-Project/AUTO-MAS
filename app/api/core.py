#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import Config, Broadcast
from app.services import System
from app.models.schema import *

router = APIRouter(prefix="/api/core", tags=["核心信息"])


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    await websocket.accept()
    Config.websocket = websocket
    while True:
        try:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            await Broadcast.put(data)
        except asyncio.TimeoutError:
            await websocket.send_json(
                WebSocketMessage(
                    id="Main", type="Signal", data={"Ping": "无描述"}
                ).model_dump()
            )
        except WebSocketDisconnect:
            break
    await System.set_power("KillSelf")
