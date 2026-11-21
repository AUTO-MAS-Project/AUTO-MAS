"""运行时配置触发器的字段写入、在途投影与任务结果。"""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.config import config_manager
from app.config.core.manager import TriggerUnavailable
from app.core.background_tasks import BackgroundTaskState
from app.models.schema import ConfigSnapshotOut, OutBase


class TriggerWriteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configUid: UUID
    group: str
    field: str
    value: StrictBool | None


class TriggerWriteOut(OutBase):
    data: UUID | None = None


class TriggerResultIn(BaseModel):
    taskId: UUID


class TriggerTaskResult(BaseModel):
    state: BackgroundTaskState
    errorCode: str | None = None


class TriggerResultOut(OutBase):
    data: TriggerTaskResult | None = None


class ActiveTriggerField(BaseModel):
    configUid: UUID
    group: str
    field: str
    taskId: UUID
    cancelling: bool


class ActiveTriggersOut(ConfigSnapshotOut):
    data: list[ActiveTriggerField] = Field(default_factory=list)


router = APIRouter(prefix="/api/config/triggers", tags=["配置触发器"])


@router.post("/write", tags=["Action"], response_model=TriggerWriteOut)
async def write_config_trigger(body: TriggerWriteIn) -> TriggerWriteOut:
    """写入三态命令并立即返回受影响的任务 UUID。"""
    try:
        uid = config_manager.write_trigger(
            body.configUid, group=body.group, field=body.field, value=body.value
        )
    except TriggerUnavailable as error:
        return TriggerWriteOut(code=409, status="error", message=str(error))
    return TriggerWriteOut(data=uid)


@router.get("/active", tags=["Get"], response_model=ActiveTriggersOut)
async def get_active_config_triggers() -> ActiveTriggersOut:
    """读取当前占用的配置触发器字段。"""
    return ActiveTriggersOut(
        uiSources=[root.uid for root in config_manager.iter_persist_roots()],
        data=[
            ActiveTriggerField(
                configUid=config_uid,
                group=group,
                field=field,
                taskId=uid,
                cancelling=cancelling,
            )
            for config_uid, group, field, uid, cancelling in config_manager.active_triggers()
        ],
    )


@router.post("/result", tags=["Get"], response_model=TriggerResultOut)
async def get_config_trigger_result(body: TriggerResultIn) -> TriggerResultOut:
    """读取任务执行状态和近期终态。"""
    result = config_manager.trigger_result(body.taskId)
    if result is None:
        return TriggerResultOut(
            code=404, status="error", message="trigger_task_not_found"
        )
    return TriggerResultOut(
        data=TriggerTaskResult(state=result.state, errorCode=result.error_code)
    )
