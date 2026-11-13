from typing import (
    List,
    Literal,
    Optional,
)

from auto_mas_core.host.models_schema import (
    OutBase,
    UserDeleteIn,
    UserInBase,
)
from auto_mas_core.host.utils import get_logger
from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

router = APIRouter()
logger = get_logger("MAA API")


class UserSetIn(UserInBase):
    userId: str = Field(..., description="账号ID")
    jsonFile: str = Field(..., description="JSON文件路径, 用于导入自定义基建文件")


class UserInfrastPlanSelectIn(BaseModel):
    scriptId: str = Field(..., description="托管ID")
    userId: str = Field(..., description="账号ID")
    index: int = Field(default=-1, ge=-1, description="基建班次索引（-1=按时段自动）")


class UserInfrastPlanSelectOut(OutBase):
    index: int = Field(..., description="当前基建班次索引（-1=按时段自动）")


class UserInfrastPlanComboxItem(BaseModel):
    label: str = Field(..., description="班次展示名")
    value: str = Field(..., description="班次索引, 即 MAA PlanSelect 值")
    period: Optional[str] = Field(default=None, description="时段文本, 无时段为 None")


class UserInfrastPlanComboxOut(OutBase):
    state: Literal["period", "rotate", "mixed", "empty"] = Field(
        ..., description="排班表时段形态（mixed=时段不一致不可用）"
    )
    data: List[UserInfrastPlanComboxItem] = Field(..., description="班次选项")


@router.post(
    "/user/infrastructure",
    tags=["Update"],
    summary="导入基建配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_infrastructure(user: UserSetIn = Body(...)) -> OutBase:

    try:
        import maa_adapter.native.infrastructure as maa_api

        await maa_api.set_infrastructure(user.scriptId, user.userId, user.jsonFile)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_infrastructure失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/infrastructure/plan-select",
    openapi_extra={"x-auto-mas-mcp": True},
    tags=["Update"],
    summary="设置基建班次",
    response_model=UserInfrastPlanSelectOut,
    status_code=200,
)
async def set_infrast_plan_select(
    user: UserInfrastPlanSelectIn = Body(...),
) -> UserInfrastPlanSelectOut:
    try:
        import maa_adapter.native.infrastructure as maa_api

        index = await maa_api.set_infrast_plan_select(
            user.scriptId, user.userId, user.index
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"set_infrast_plan_select失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanSelectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", index=-1
        )
    return UserInfrastPlanSelectOut(index=index)


@router.post(
    "/user/infrastructure/plan-select/get",
    openapi_extra={"x-auto-mas-mcp": True},
    tags=["Get"],
    summary="获取当前基建班次",
    response_model=UserInfrastPlanSelectOut,
    status_code=200,
)
async def get_infrast_plan_select(
    user: UserDeleteIn = Body(...),
) -> UserInfrastPlanSelectOut:
    try:
        import maa_adapter.native.infrastructure as maa_api

        index = await maa_api.get_infrast_plan_select(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_infrast_plan_select失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanSelectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", index=-1
        )
    return UserInfrastPlanSelectOut(index=index)


@router.post(
    "/user/combox/infrastructure",
    openapi_extra={"x-auto-mas-mcp": True},
    tags=["Get"],
    summary="用户自定义基建排班可选项",
    response_model=UserInfrastPlanComboxOut,
    status_code=200,
)
async def get_user_combox_infrastructure(
    user: UserDeleteIn = Body(...),
) -> UserInfrastPlanComboxOut:

    try:
        import maa_adapter.native.infrastructure as maa_api

        result = await maa_api.get_user_combox_infrastructure(
            user.scriptId, user.userId
        )
        data = [UserInfrastPlanComboxItem(**item) for item in result["data"]]
        state = result["state"]
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_user_combox_infrastructure失败: {type(e).__name__}: {e}"
        )
        return UserInfrastPlanComboxOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            state="empty",
            data=[],
        )
    return UserInfrastPlanComboxOut(state=state, data=data)
