#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body

from app.core import Config, TaskManager
from app.services import System
from app.models.schema import *

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.post(
    "/start", summary="添加任务", response_model=TaskCreateOut, status_code=200
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:

    try:
        task_id = await TaskManager.add_task(task.mode, task.taskId)
    except Exception as e:
        return TaskCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            websocketId="",
        )
    return TaskCreateOut(websocketId=str(task_id))


@router.post("/stop", summary="中止任务", response_model=OutBase, status_code=200)
async def stop_task(task: DispatchIn = Body(...)) -> OutBase:

    try:
        await TaskManager.stop_task(task.taskId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/set/power", summary="设置电源标志", response_model=OutBase, status_code=200
)
async def set_power(task: PowerIn = Body(...)) -> OutBase:

    try:
        Config.power_sign = task.signal
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/cancel/power", summary="取消电源任务", response_model=OutBase, status_code=200
)
async def cancel_power_task() -> OutBase:

    try:
        await System.cancel_power_task()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
