#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

"""开发模式专用工具接口。"""

from fastapi import APIRouter, Body, HTTPException

from app.models.schema import MaaBasePresetOut, MaaBasePresetUpdateIn
from app.utils import get_logger, is_backend_dev_mode

router = APIRouter(prefix="/api/developer", tags=["Developer"])
logger = get_logger("开发者工具 API")


@router.get(
    "/maa/base-preset",
    summary="读取 MAA 内置预设（仅开发模式）",
    response_model=MaaBasePresetOut,
    status_code=200,
)
async def get_maa_base_preset_api() -> MaaBasePresetOut:
    """读取当前进程正在使用的 MAA 内置预设。"""

    if not is_backend_dev_mode():
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        from app.task.MAA.base_preset import (
            MAA_BASE_PRESET_PATH,
            reload_maa_base_preset,
        )

        return MaaBasePresetOut(
            data=reload_maa_base_preset(), path=str(MAA_BASE_PRESET_PATH)
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"读取 MAA 内置预设失败: {type(exc).__name__}: {exc}"
        )
        return MaaBasePresetOut(
            code=500,
            status="error",
            message="读取 MAA 内置预设失败",
        )


@router.post(
    "/maa/base-preset",
    summary="保存 MAA 内置预设（仅开发模式）",
    response_model=MaaBasePresetOut,
    status_code=200,
)
async def update_maa_base_preset_api(
    request: MaaBasePresetUpdateIn = Body(...),
) -> MaaBasePresetOut:
    """校验并保存完整 MAA 内置预设，同时刷新当前进程内存。"""

    if not is_backend_dev_mode():
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        from app.task.MAA.base_preset import (
            MAA_BASE_PRESET_PATH,
            update_maa_base_preset,
        )

        data = update_maa_base_preset(request.data)
        return MaaBasePresetOut(
            message="MAA 内置预设已保存并刷新运行时配置",
            data=data,
            path=str(MAA_BASE_PRESET_PATH),
        )
    except ValueError as exc:
        logger.warning(f"MAA 内置预设校验失败: {exc}")
        return MaaBasePresetOut(
            code=400,
            status="error",
            message=str(exc),
        )
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"保存 MAA 内置预设失败: {type(exc).__name__}: {exc}"
        )
        return MaaBasePresetOut(
            code=500,
            status="error",
            message="保存 MAA 内置预设失败",
        )
