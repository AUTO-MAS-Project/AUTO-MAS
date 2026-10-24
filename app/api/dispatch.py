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


from typing import (
    Literal,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.core import Config, TaskManager
from app.models.schema import (
    OutBase,
    PowerCountdownSnapshot,
    TaskRuntimeSnapshot,
    TaskStatusOut,
)
from app.services import System
from app.utils import get_logger


class DispatchIn(BaseModel):
    taskId: str = Field(
        ...,
        description="目标任务ID, 设置类任务可选对应脚本ID或用户ID, 代理类任务可选对应队列ID或脚本ID",
    )


class TaskCreateIn(DispatchIn):
    mode: Literal["AutoProxy", "ScriptConfig", "Update", "CycleRun"] = Field(
        ...,
        description="任务模式; CycleRun 为循环运行, 仅接受循环队列, 其脚本按 AutoProxy 执行",
    )
    resumeFromScriptId: str | None = Field(
        default=None,
        description="可选：仅对队列任务生效；从指定脚本ID开始执行（之前的脚本将被标记为跳过）",
    )
    userId: str | None = Field(
        default=None,
        description="可选：仅对脚本的自动代理任务生效；只运行该脚本下的这一个用户",
    )
    userIds: list[str] | None = Field(
        default=None,
        description="可选：仅对脚本的自动代理任务生效；只运行指定的多个用户",
    )
    queueUserIds: dict[str, list[str]] | None = Field(
        default=None,
        description="可选：仅对队列任务生效；按脚本ID指定本次要运行的用户；未列出的脚本不限, 空列表表示该脚本本次整项跳过",
    )
    viewOnly: bool = Field(
        default=False,
        description="可选：仅 ScriptConfig 生效；只读查看会话（不注入基线、不回读字段），用于预览历史备份",
    )
    instanceIdx: int | None = Field(
        default=None,
        description="可选：仅 ScriptConfig 生效；直控指定会话窗口打开的原生实例（临时切换活跃，会话结束还原）",
    )


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class PowerIn(BaseModel):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
        "RestartSelf",
        "Logoff",
    ] = Field(..., description="电源操作信号")


class PowerOut(OutBase):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
        "RestartSelf",
        "Logoff",
    ] = Field(..., description="电源操作信号")


router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])
logger = get_logger("任务调度 API")


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
    "/task/{task_id}",
    tags=["Get"],
    summary="按 taskId 查询单个任务状态",
    response_model=TaskStatusOut,
    status_code=200,
)
async def get_task_status(task_id: str) -> TaskStatusOut:
    """返回运行中或最近完成任务的终态；不包含日志。"""

    result = TaskManager.get_task_status(task_id)
    if result is None:
        return TaskStatusOut(
            code=404,
            status="error",
            message=f"任务 {task_id} 既不在运行中, 也不在最近完成的记录里",
            taskId=task_id,
        )
    return result


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
            user_id=task.userId,
            user_ids=task.userIds,
            queue_user_ids=task.queueUserIds,
            view_only=task.viewOnly,
            instance_idx=task.instanceIdx,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_task失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(f"stop_task失败: {type(e).__name__}: {e}")
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
        # 电源任务启动后标志已清空, 等待期间要回报任务实际待执行的操作
        signal = System.current_power_operation or Config.power_sign
    except Exception as e:
        logger.opt(exception=True).warning(f"get_power失败: {type(e).__name__}: {e}")
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
        # 手动选择的电源操作不带延时, 同时清掉队列可能残留的延时
        Config.power_delay = 0
        # 已在等待的电源任务持有旧操作, 延时期间又没有倒计时窗口提示,
        # 因此手动改选一律撤销它, 新选择留给下一次任务结束时生效
        await System.cancel_pending_power_task()
    except Exception as e:
        logger.opt(exception=True).warning(f"set_power失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(
            f"cancel_power_task失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
