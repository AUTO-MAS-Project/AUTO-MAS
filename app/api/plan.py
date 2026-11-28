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
    Dict,
    List,
    Literal,
    Optional,
    cast,
)
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import (
    BaseModel,
    Field,
    SerializeAsAny,
    SkipValidation,
    ValidationError,
)

import app.models.config as _config_models
from app.api._config_editors import (
    FrontendWriteGuard,
    config_detail_ui,
    config_update_data,
    require_frontend_activation,
)
from app.api._error_codes import config_error_code
from app.config.errors import ConfigAggregateError
from app.config.wire import ConfigPayload, StrictConfigInput, config_contract
from app.core import Config
from app.models.schema import (
    ConfigUpdateOut,
    DeclarativeConfigGetOut,
    OutBase,
    UnavailableConfigItem,
)
from app.utils import get_logger

OkwwPlanConfig = ConfigPayload[_config_models.OkwwPlanConfig]
OkwwPlanConfigInput = StrictConfigInput[_config_models.OkwwPlanConfig]

OkNtePlanConfig = ConfigPayload[_config_models.OkNtePlanConfig]
OkNtePlanConfigInput = StrictConfigInput[_config_models.OkNtePlanConfig]

UniversalPlanConfig = ConfigPayload[_config_models.UniversalPlanConfig]
UniversalPlanConfigInput = StrictConfigInput[_config_models.UniversalPlanConfig]

MaaEndPlanConfig = ConfigPayload[_config_models.MaaEndPlanConfig]
MaaEndPlanConfigInput = StrictConfigInput[_config_models.MaaEndPlanConfig]

PlanConfigType = str


class PlanIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: PlanConfigType = Field(
        json_schema_extra={"enum": list(_config_models.PLAN_BOOK)},
        default=...,
        description="配置类型",
    )


PlanCreateType = Literal[
    "MaaEndPlan",
    "UniversalPlan",
    "OkNtePlan",
    "OkwwPlan",
]


type PlanConfigData = (
    SerializeAsAny[BaseModel]
    | MaaEndPlanConfig
    | UniversalPlanConfig
    | OkNtePlanConfig
    | OkwwPlanConfig
)
type PlanConfigDataInput = SkipValidation[
    SerializeAsAny[BaseModel]
    | MaaEndPlanConfigInput
    | UniversalPlanConfigInput
    | OkNtePlanConfigInput
    | OkwwPlanConfigInput
]


class PlanCreateIn(BaseModel):
    type: str = Field(
        json_schema_extra={
            "enum": [item["create_type"] for item in _config_models.PLAN_BOOK.values()]
        }
    )
    scriptId: str | None = None


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: PlanConfigData = Field(..., description="计划配置数据")


class PlanGetIn(BaseModel):
    planId: Optional[str] = Field(
        default=None, description="计划ID, 未携带时表示获取所有计划数据"
    )


class PlanGetOut(DeclarativeConfigGetOut):
    index: List[PlanIndexItem] = Field(..., description="计划索引列表")
    data: Dict[str, PlanConfigData] = Field(..., description="计划列表或单个计划数据")
    unavailable: List[UnavailableConfigItem] = Field(
        default_factory=list,
        description="所属插件不可用的计划表，只在获取全部计划时给出；只能删除",
    )


class PlanUpdateIn(BaseModel):
    planId: str = Field(..., description="计划ID")
    data: PlanConfigDataInput = Field(..., description="计划更新数据")


class PlanDeleteIn(BaseModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="计划ID列表, 按新顺序排列")


class UniversalPlanStateIn(BaseModel):
    planId: str


class UniversalPlanStateOut(OutBase):
    configuredDays: list[str] = Field(
        default_factory=list, description="已保存完整配置的日期分组"
    )


router = APIRouter(prefix="/api/plan", tags=["计划管理"])
logger = get_logger("计划管理 API")


@router.post(
    "/add",
    tags=["Add"],
    summary="添加计划表",
    response_model=PlanCreateOut,
    status_code=200,
)
async def add_plan(plan: PlanCreateIn = Body(...)) -> PlanCreateOut:

    try:
        uid, config = await Config.add_plan(plan.type, script_id=plan.scriptId)
        document = config.model_dump()
        document.pop("ui", None)
        data = cast(PlanConfigData, config_contract(type(config))(**document))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_plan失败: {type(e).__name__}: {e}")
        plan_contract = ConfigPayload[_config_models.UniversalPlanConfig]
        return PlanCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            planId="",
            data=cast(PlanConfigData, plan_contract(**{})),
        )
    return PlanCreateOut(planId=str(uid), data=data)


@router.post(
    "/get",
    tags=["Get"],
    summary="查询计划表",
    response_model=PlanGetOut,
    status_code=200,
)
async def get_plan(plan: PlanGetIn = Body(default_factory=PlanGetIn)) -> PlanGetOut:

    try:
        raw_index, raw_data = await Config.get_plan(plan.planId)
        index = [PlanIndexItem(**_) for _ in raw_index]
        ui = (
            config_detail_ui(Config.PlanConfig[plan.planId], raw_data)
            if plan.planId
            else None
        )
        data: dict[str, PlanConfigData] = {}

        for item in raw_index:
            uid = item["uid"]
            plan_type = item["type"]

            document = dict(raw_data[uid])
            document.pop("ui", None)
            data[uid] = cast(
                PlanConfigData,
                config_contract(Config.PlanConfig.entry_types[plan_type])(**document),
            )
    except Exception as e:
        logger.opt(exception=True).warning(f"get_plan失败: {type(e).__name__}: {e}")
        return PlanGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return PlanGetOut(
        ui=ui,
        index=index,
        data=data,
        unavailable=(
            [UnavailableConfigItem(**item) for item in Config.unavailable_plans()]
            if plan.planId is None
            else []
        ),
        uiSources=[UUID(plan.planId) if plan.planId else Config.PlanConfig.uid],
    )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新计划表配置信息",
    response_model=ConfigUpdateOut,
    status_code=200,
)
async def update_plan(
    plan: PlanUpdateIn = Body(...),
    guard: FrontendWriteGuard | None = Depends(
        require_frontend_activation, scope="function"
    ),
) -> ConfigUpdateOut:

    try:
        entry = Config.PlanConfig[plan.planId]
        if guard is not None:
            guard(entry)
        data = config_update_data(entry, plan.data, extra="forbid")
        await Config.update_plan(plan.planId, data)
    except HTTPException:
        raise
    except (ValidationError, ConfigAggregateError) as e:
        return ConfigUpdateOut.from_validation_error(e, code=config_error_code(e))
    except Exception as e:
        logger.opt(exception=True).warning(f"update_plan失败: {type(e).__name__}: {e}")
        return ConfigUpdateOut(
            code=config_error_code(e),
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )
    return ConfigUpdateOut()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除计划表",
    response_model=OutBase,
    status_code=200,
)
async def delete_plan(plan: PlanDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_plan(plan.planId)
    except Exception as e:
        logger.opt(exception=True).warning(f"delete_plan失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序计划表",
    response_model=OutBase,
    status_code=200,
)
async def reorder_plan(plan: PlanReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_plan(plan.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(f"reorder_plan失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/universal-state",
    tags=["Get"],
    summary="查询通用脚本计划表已配置的日期",
    response_model=UniversalPlanStateOut,
)
async def get_universal_plan_state(
    plan: UniversalPlanStateIn = Body(...),
) -> UniversalPlanStateOut:
    try:
        return UniversalPlanStateOut(
            configuredDays=Config.get_universal_plan_days(plan.planId)
        )
    except (KeyError, ValueError, TypeError) as error:
        return UniversalPlanStateOut(code=400, status="error", message=str(error))
