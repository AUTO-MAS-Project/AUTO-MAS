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
from app.models.schema import *

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.get(
    "/runtime-snapshot",
    tags=["Get"],
    summary="获取运行中任务初始快照",
    response_model=TaskRuntimeSnapshot,
    status_code=200,
)
async def get_task_runtime_snapshot() -> TaskRuntimeSnapshot:
    """返回当前运行任务；WS 只承载后续状态、日志与完成事件。"""

    return TaskManager.get_runtime_snapshot()


@router.get(
    "/script-states-snapshot",
    tags=["Get"],
    summary="获取按脚本类型聚合的调度状态",
    response_model=ScriptDispatchStateSnapshot,
    status_code=200,
)
async def get_script_states_snapshot() -> ScriptDispatchStateSnapshot:
    """返回脚本类型的排队、运行和失败状态。"""

    return TaskManager.get_script_states_snapshot()


@router.get(
    "/power/countdown-snapshot",
    tags=["Get"],
    summary="获取电源倒计时初始快照",
    response_model=PowerCountdownSnapshot,
    status_code=200,
)
async def get_power_countdown_snapshot() -> PowerCountdownSnapshot:
    """返回当前倒计时；WS 只承载后续逐秒更新与取消事件。"""

    return System.get_power_countdown_snapshot()


@router.post(
    "/start",
    tags=["Action"],
    summary="添加任务",
    response_model=TaskCreateOut,
    status_code=200,
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:

    try:
        task_id = await TaskManager.add_task(
            mode=task.mode,
            id=task.taskId,
            resume_from_script_id=task.resumeFromScriptId,
        )
    except Exception as e:
        return TaskCreateOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", taskId=""
        )
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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
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
        return PowerOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            signal="NoAction",
        )
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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
