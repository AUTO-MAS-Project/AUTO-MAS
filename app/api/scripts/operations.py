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


# [兼容旧专项] 现有手动更新入口；新专项维护能力在专项业务层定义。
# TODO(插件迁移，#1845)：全部存量专项维护保持原路径，统一迁移时再替换入口与任务结果契约。
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
