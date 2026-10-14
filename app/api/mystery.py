"""神秘入口的申请信息接口。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.schema import MysteryContextData, MysteryContextOut
from app.mystery.access import MysteryContextError, get_access_context
from app.utils import get_logger

router = APIRouter(prefix="/api/mystery", tags=["Mystery"])
logger = get_logger("神秘入口")


@router.get(
    "/context",
    summary="获取神秘入口申请信息",
    response_model=MysteryContextOut,
    responses={503: {"model": MysteryContextOut}},
)
def get_mystery_context() -> MysteryContextOut | JSONResponse:
    # 同步端点由 FastAPI 在线程池执行，首次设备查询与源码读取不阻塞事件循环。
    try:
        device_hash, backend_hash = get_access_context()
    except MysteryContextError as error:
        cause = error.__cause__ or error
        location = cause.__traceback__
        while location and location.tb_next:
            location = location.tb_next
        operation = (
            location.tb_frame.f_code.co_name if location else "get_access_context"
        )
        system_error = getattr(cause, "hresult", getattr(cause, "errno", None))
        # 记录异常类别、操作和系统错误，避免把设备原码或异常中的原始值写入日志。
        logger.warning(
            f"读取申请信息失败: {error.code}, "
            f"异常={type(cause).__name__}, 操作={operation}, 系统错误={system_error}"
        )
        response = MysteryContextOut(
            code=503, status="error", message="申请信息不可用", errorCode=error.code
        )
        return JSONResponse(status_code=503, content=response.model_dump())
    return MysteryContextOut(
        data=MysteryContextData(deviceHash=device_hash, backendHash=backend_hash)
    )
