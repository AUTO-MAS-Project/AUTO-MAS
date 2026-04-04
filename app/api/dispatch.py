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


from fastapi import APIRouter, Body

from app.core import Config, TaskManager
from app.services import System
from app.models.common_contract import OutBase
from app.models.dispatch_contract import (
    DispatchIn,
    PowerIn,
    PowerOut,
    TaskCreateIn,
    TaskCreateOut,
)
from app.api.common import error_out

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.post(
    "/start",
    tags=["Action"],
    summary="添加任务",
    response_model=TaskCreateOut,
    status_code=200,
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:
    try:
        task_id = await TaskManager.add_task(task.mode, task.taskId)
    except Exception as e:
        return error_out(TaskCreateOut, e, taskId="")
    return TaskCreateOut(taskId=str(task_id))


@router.post(
    "/stop",
    tags=["Action"],
    summary="中止任务",
    response_model=OutBase,
    status_code=200,
)
async def stop_task(task: DispatchIn = Body(...)) -> OutBase:
    try:
        await TaskManager.stop_task(task.taskId)
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/get/power",
    tags=["Get"],
    summary="获取电源标志",
    response_model=PowerOut,
    status_code=200,
)
async def get_power() -> PowerOut:
    try:
        signal = Config.power_sign
    except Exception as e:
        return error_out(PowerOut, e, signal="NoAction")
    return PowerOut(signal=signal)


@router.post(
    "/set/power",
    tags=["Action"],
    summary="设置电源标志",
    response_model=OutBase,
    status_code=200,
)
async def set_power(task: PowerIn = Body(...)) -> OutBase:
    try:
        Config.power_sign = task.signal
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/cancel/power",
    tags=["Action"],
    summary="取消电源任务",
    response_model=OutBase,
    status_code=200,
)
async def cancel_power_task() -> OutBase:
    try:
        await System.cancel_power_task()
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()
