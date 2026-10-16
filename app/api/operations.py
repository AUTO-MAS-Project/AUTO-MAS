"""受管理命令的受理、查询与取消。"""

from fastapi import APIRouter
from pydantic import ValidationError

from app.core.operations import Operations, OperationUnavailable
from app.models.schema import (
    OperationGetIn,
    OperationListIn,
    OperationListOut,
    OperationOut,
    OperationStartIn,
)

router = APIRouter(prefix="/api/operations", tags=["宿主操作"])


@router.post("/start", tags=["Action"], response_model=OperationOut)
async def start_operation(body: OperationStartIn) -> OperationOut:
    try:
        uid = await Operations.start(
            config_uid=body.configUid,
            group=body.group,
            field=body.field,
            value=body.value,
        )
    except (OperationUnavailable, ValidationError) as exc:
        return OperationOut(code=400, status="error", message=str(exc))
    return OperationOut(data=Operations.get(uid))


@router.post("/get", tags=["Get"], response_model=OperationOut)
async def get_operation(body: OperationGetIn) -> OperationOut:
    info = Operations.get(body.operationId)
    if info is None:
        return OperationOut(code=404, status="error", message="operation_not_found")
    return OperationOut(data=info)


@router.post("/list", tags=["Get"], response_model=OperationListOut)
async def list_operations(body: OperationListIn) -> OperationListOut:
    return OperationListOut(data=Operations.list(config_uid=body.configUid))


@router.post("/cancel", tags=["Action"], response_model=OperationOut)
async def cancel_operation(body: OperationGetIn) -> OperationOut:
    try:
        info = await Operations.cancel(body.operationId)
    except KeyError:
        return OperationOut(code=404, status="error", message="operation_not_found")
    except OperationUnavailable as exc:
        return OperationOut(code=409, status="error", message=str(exc))
    return OperationOut(data=info)
