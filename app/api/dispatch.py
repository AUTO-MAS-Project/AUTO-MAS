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
from app.contracts.common_contract import OutBase
from app.contracts.dispatch_contract import (
    DispatchIn,
    PowerIn,
    PowerOut,
    TaskCreateIn,
    TaskCreateOut,
)

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.post(
    "/start",
    tags=["Action"],
    summary="添加任务",
    response_model=TaskCreateOut,
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:
    task_id = await TaskManager.add_task(task.mode, task.taskId)
    return TaskCreateOut(taskId=str(task_id))


@router.post(
    "/stop",
    tags=["Action"],
    summary="中止任务",
    response_model=OutBase,
)
async def stop_task(task: DispatchIn = Body(...)) -> OutBase:
    await TaskManager.stop_task(task.taskId)
    return OutBase()


@router.post(
    "/get/power",
    tags=["Get"],
    summary="获取电源标志",
    response_model=PowerOut,
)
async def get_power() -> PowerOut:
    signal = Config.power_sign
    return PowerOut(signal=signal)


@router.post(
    "/set/power",
    tags=["Action"],
    summary="设置电源标志",
    response_model=OutBase,
)
async def set_power(task: PowerIn = Body(...)) -> OutBase:
    Config.power_sign = task.signal
    return OutBase()


@router.post(
    "/cancel/power",
    tags=["Action"],
    summary="取消电源任务",
    response_model=OutBase,
)
async def cancel_power_task() -> OutBase:
    await System.cancel_power_task()
    return OutBase()
