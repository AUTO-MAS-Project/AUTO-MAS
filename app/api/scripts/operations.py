"""专项手动维护操作；不增加公开调度模式。"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import TaskManager
from app.models.schema import OutBase


class ScriptOperationIn(BaseModel):
    targetId: str


class ScriptOperationOut(OutBase):
    taskId: str = ""


router = APIRouter(prefix="/operations")


# [兼容旧专项] 现有手动更新入口，继续沿原路径执行。
# TODO(插件迁移，#1845)：未来维护任务标准方案整体推迟，尚未确认；
# 操作身份、查询/日志、结果消费及取消停写契约届时统一讨论，不在本入口提前接入后台任务组。
@router.post("/start", response_model=ScriptOperationOut)
async def start_operation(body: ScriptOperationIn):
    try:
        return ScriptOperationOut(
            taskId=str(await TaskManager.start_maintenance(body.targetId))
        )
    except ValueError as error:
        return ScriptOperationOut(code=400, status="error", message=str(error))
    except RuntimeError as error:
        return ScriptOperationOut(code=409, status="error", message=str(error))
