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


from fastapi import APIRouter, Body

from app.core import Config
from app.models.config import MaaEndPlanConfig as MaaEndPlanConfigModel
from app.models.config import MaaPlanConfig as MaaPlanConfigModel
from app.models.schema import *

router = APIRouter(prefix="/api/plan", tags=["计划管理"])


def build_plan_config_model(
    plan_type: str, plan_data: dict
) -> MaaPlanConfig | MaaEndPlanConfig:
    if plan_type == "MaaEndPlanConfig":
        return MaaEndPlanConfig(**plan_data)
    return MaaPlanConfig(**plan_data)


def build_plan_config_from_instance(
    config: MaaPlanConfigModel | MaaEndPlanConfigModel, plan_data: dict
) -> MaaPlanConfig | MaaEndPlanConfig:
    if isinstance(config, MaaEndPlanConfigModel):
        return MaaEndPlanConfig(**plan_data)
    return MaaPlanConfig(**plan_data)


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
        data = build_plan_config_from_instance(config, await config.toDict())
    except Exception as e:
        return PlanCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            planId="",
            data=(
                MaaEndPlanConfig(**{})
                if plan.type == "MaaEndPlan"
                else MaaPlanConfig(**{})
            ),
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
        index_book = {item["uid"]: item["type"] for item in raw_index}
        data = {
            uid: build_plan_config_model(index_book.get(uid, "MaaPlanConfig"), cfg)
            for uid, cfg in raw_data.items()
        }
    except Exception as e:
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
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
