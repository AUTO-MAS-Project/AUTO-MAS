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


import uuid
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Body, Path

from app.core import TaskManager, Broadcast
from app.models.schema import *

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.post(
    "/start", summary="添加任务", response_model=TaskCreateOut, status_code=200
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:

    try:
        task_id = await TaskManager.add_task(task.mode, task.taskId)
    except Exception as e:
        return TaskCreateOut(code=500, status="error", message=str(e), websocketId="")
    return TaskCreateOut(websocketId=str(task_id))


@router.post("/stop", summary="中止任务", response_model=OutBase, status_code=200)
async def stop_task(task: DispatchIn = Body(...)) -> OutBase:

    try:
        await TaskManager.stop_task(task.taskId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.websocket("/ws/{taskId}")
async def websocket_endpoint(
    websocket: WebSocket, taskId: str = Path(..., description="要连接的任务ID")
):
    await websocket.accept()
    try:
        uid = uuid.UUID(taskId)
    except ValueError:
        await websocket.close(code=1008, reason="无效的任务ID")
        return

    if uid in TaskManager.connection_events and uid not in TaskManager.websocket_dict:
        TaskManager.websocket_dict[uid] = websocket
        TaskManager.connection_events[uid].set()
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                await Broadcast.put(data)
            except asyncio.TimeoutError:
                await websocket.send_json(
                    TaskMessage(type="Signal", data={"Ping": "无描述"}).model_dump()
                )
            except WebSocketDisconnect:
                TaskManager.websocket_dict.pop(uid, None)
                break
    else:
        await websocket.close(code=1008, reason="任务不存在或已结束")
