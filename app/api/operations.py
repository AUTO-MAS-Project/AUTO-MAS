"""宿主命令的受理、可重复查询及受策略约束的取消。"""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationError

from app.core.plugin.operations import Operations, OperationUnavailable
from app.models.schema import OperationInfo, OutBase


class OperationStartIn(BaseModel):
    configUid: UUID
    group: str
    field: str
    value: bool | str


class OperationGetIn(BaseModel):
    operationId: UUID


class OperationListIn(BaseModel):
    configUid: UUID | None = None


class OperationOut(OutBase):
    data: OperationInfo | None = None


class OperationListOut(OutBase):
    data: list[OperationInfo] = Field(default_factory=list)


router = APIRouter(prefix="/api/operations", tags=["宿主操作"])


@router.post("/start", tags=["Action"], response_model=OperationOut)
async def start_operation(body: OperationStartIn) -> OperationOut:
    """校验配置触发器请求并提交后台操作，返回操作记录或当前无法执行的原因。"""
    try:
        uid = await Operations.start(
            config_uid=body.configUid,
            group=body.group,
            field=body.field,
            value=body.value,
        )
    except (OperationUnavailable, ValidationError) as error:
        return OperationOut(code=409, status="error", message=str(error))
    return OperationOut(data=Operations.get(uid))


@router.post("/get", tags=["Get"], response_model=OperationOut)
async def get_operation(body: OperationGetIn) -> OperationOut:
    """按操作标识读取执行记录，记录不存在时返回未找到错误。"""
    info = Operations.get(body.operationId)
    if info is None:
        return OperationOut(code=404, status="error", message="operation_not_found")
    return OperationOut(data=info)


@router.post("/list", tags=["Get"], response_model=OperationListOut)
async def list_operations(body: OperationListIn) -> OperationListOut:
    """查询全部或指定配置节点的操作记录，供前端展示执行状态。"""
    return OperationListOut(data=Operations.list(config_uid=body.configUid))


@router.post("/cancel", tags=["Action"], response_model=OperationOut)
async def cancel_operation(body: OperationGetIn) -> OperationOut:
    """请求取消指定后台操作，返回取消后的记录，并区分不存在与不允许取消的情况。"""
    try:
        return OperationOut(data=await Operations.cancel(body.operationId))
    except KeyError:
        return OperationOut(code=404, status="error", message="operation_not_found")
    except OperationUnavailable as error:
        return OperationOut(code=409, status="error", message=str(error))
