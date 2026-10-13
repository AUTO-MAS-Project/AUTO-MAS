"""任务调度 API（``TaskDispatcher`` 为任务信息唯一事实源；含电源倒计时）。"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api import OutBase
from app.config import CollectionOrderItem
from app.core import Config, TaskDispatcher
from app.models.task import TaskItem, TaskMode
from app.services import System
from app.services.system import PowerCountdownSnapshot
from app.task import ExpandError

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])

PowerSignal = Literal[
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
    "Logoff",
]


class TaskCreateIn(BaseModel):
    """按设计 §5.1：mode + 可选 queue/script/user uid。"""

    mode: TaskMode = Field(..., description="任务模式")
    queueId: Optional[str] = Field(default=None, description="队列 uid")
    scriptId: Optional[str] = Field(default=None, description="脚本 uid")
    userId: Optional[str] = Field(default=None, description="用户 uid")


class TaskCreateOut(OutBase):
    taskId: str = Field(default="", description="新创建的任务ID")


class DispatchIn(BaseModel):
    taskId: str = Field(..., description="目标任务 ID")


class TaskGetIn(BaseModel):
    taskId: Optional[str] = None


class TaskGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, TaskItem] = Field(default_factory=dict)


class PowerIn(BaseModel):
    signal: PowerSignal = Field(..., description="电源操作信号")


class PowerOut(OutBase):
    signal: PowerSignal = Field(..., description="电源操作信号")


@router.get(
    "/power/countdown-snapshot",
    tags=["Get"],
    summary="获取电源倒计时初始快照",
    response_model=PowerCountdownSnapshot,
    status_code=200,
)
async def get_power_countdown_snapshot() -> PowerCountdownSnapshot:
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
        task_id = await TaskDispatcher.start(
            mode=task.mode,
            queue_id=task.queueId,
            script_id=task.scriptId,
            user_id=task.userId,
        )
    except ExpandError as e:
        return TaskCreateOut(code=400, status="error", message=str(e), taskId="")
    except Exception as e:
        return TaskCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            taskId="",
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
        await TaskDispatcher.stop(UUID(task.taskId))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/get", tags=["Get"], summary="查询任务", response_model=TaskGetOut)
async def get_tasks(body: TaskGetIn = Body(...)) -> TaskGetOut:
    try:
        if body.taskId:
            uid = UUID(body.taskId)
            item = TaskDispatcher.get_task(uid)
            items = [(uid, item)] if item is not None else []
        else:
            items = list(TaskDispatcher.running_items())
        return TaskGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(item).__name__)
                for uid, item in items
            ],
            data={str(uid): item for uid, item in items},
        )
    except Exception as e:
        return TaskGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


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
            message=f"{type(e).__name__}: {e}",
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
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
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
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()
