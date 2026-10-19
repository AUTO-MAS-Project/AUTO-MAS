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

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

import app.models.config as _config_models
from app.config.wire import ConfigPayload, StrictConfigInput, config_contract
from app.core import Config
from app.models.config import PLAN_BOOK
from app.models.schema import OutBase
from app.utils import get_logger

BAAHPlanConfig = ConfigPayload[_config_models.BAAHPlanConfig]
BAAHPlanConfigInput = StrictConfigInput[_config_models.BAAHPlanConfig]
MSSPlanConfig = ConfigPayload[_config_models.MSSPlanConfig]
MSSPlanConfigInput = StrictConfigInput[_config_models.MSSPlanConfig]
MaaEndPlanConfig = ConfigPayload[_config_models.MaaEndPlanConfig]
MaaEndPlanConfigInput = StrictConfigInput[_config_models.MaaEndPlanConfig]
MaaPlanConfig = ConfigPayload[_config_models.MaaPlanConfig]
MaaPlanConfigInput = StrictConfigInput[_config_models.MaaPlanConfig]

PlanConfigType = Literal[
    "MaaPlanConfig", "MaaEndPlanConfig", "BAAHPlanConfig", "MSSPlanConfig"
]


class PlanIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: PlanConfigType = Field(..., description="配置类型")


PlanCreateType = Literal["MaaPlan", "MaaEndPlan", "BAAHPlan", "MSSPlan"]


type PlanConfigData = MaaPlanConfig | MaaEndPlanConfig | BAAHPlanConfig | MSSPlanConfig
type PlanConfigDataInput = (
    MaaPlanConfigInput
    | MaaEndPlanConfigInput
    | BAAHPlanConfigInput
    | MSSPlanConfigInput
)


class PlanCreateIn(BaseModel):
    type: PlanCreateType


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: PlanConfigData = Field(..., description="计划配置数据")


class PlanGetIn(BaseModel):
    planId: Optional[str] = Field(
        default=None, description="计划ID, 未携带时表示获取所有计划数据"
    )


class PlanGetOut(OutBase):
    index: List[PlanIndexItem] = Field(..., description="计划索引列表")
    data: Dict[str, PlanConfigData] = Field(..., description="计划列表或单个计划数据")


class PlanUpdateIn(BaseModel):
    planId: str = Field(..., description="计划ID")
    data: PlanConfigDataInput = Field(..., description="计划更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.PlanConfig[value["planId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(
            type(target), mode="input", extra="forbid"
        ).model_validate(value["data"])
        return {**value, "data": payload}


class PlanDeleteIn(BaseModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="计划ID列表, 按新顺序排列")


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
        uid, config = await Config.add_plan(plan.type)
        document = config.model_dump()
        document.pop("ui", None)
        data = cast(PlanConfigData, config_contract(type(config))(**document))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_plan失败: {type(e).__name__}: {e}")
        plan_contract = next(
            config_contract(item["config_class"])
            for item in PLAN_BOOK.values()
            if item["create_type"] == plan.type
        )
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
async def get_plan(plan: PlanGetIn = Body(...)) -> PlanGetOut:

    try:
        raw_index, raw_data = await Config.get_plan(plan.planId)
        index = [PlanIndexItem(**_) for _ in raw_index]
        data: dict[str, PlanConfigData] = {}

        for item in raw_index:
            uid = item["uid"]
            plan_type = item["type"]

            document = dict(raw_data[uid])
            document.pop("ui", None)
            data[uid] = cast(
                PlanConfigData,
                config_contract(PLAN_BOOK[plan_type]["config_class"])(**document),
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
    return PlanGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新计划表配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_plan(plan: PlanUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_plan(plan.planId, plan.data.model_dump(exclude_unset=True))
    except Exception as e:
        logger.opt(exception=True).warning(f"update_plan失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


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
