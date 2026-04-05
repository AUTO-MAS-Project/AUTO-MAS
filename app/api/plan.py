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


from typing import Annotated

from fastapi import APIRouter, Body, Path

from app.api.common import RECOVERABLE_EXCEPTIONS, bind_api, error_out
from app.core import Config
from app.contracts.common_contract import (
    IndexOrderPatch,
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.contracts.plan_contract import (
    MaaPlanRead,
    PlanCreateIn,
    PlanCreateOut,
    PlanDetailOut,
    PlanGetOut,
    PlanIndexItem,
    PlanUpdateBody,
)

router = APIRouter(prefix="/api/plan", tags=["计划管理"])
api = bind_api(router)

PlanIdPath = Annotated[str, Path(description="计划 ID")]


async def _build_plan_collection_out() -> PlanGetOut:
    index, data = await Config.get_plan(None)
    return PlanGetOut(
        index=project_model_list(PlanIndexItem, index),
        data=project_model_map(MaaPlanRead, data),
    )


async def _build_plan_detail_out(plan_id: str) -> PlanDetailOut:
    _, data = await Config.get_plan(plan_id)
    projected = project_model_map(MaaPlanRead, data)
    return PlanDetailOut(data=projected[plan_id])


@api.post(
    "",
    tags=["Add"],
    summary="创建计划表",
    response_model=PlanCreateOut,
    id="",
    data=MaaPlanRead(),
)
async def create_plan(plan: PlanCreateIn = Body(...)) -> PlanCreateOut:
    try:
        uid, config = await Config.add_plan(plan.type)
        data = project_model(MaaPlanRead, await config.toDict())
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(PlanCreateOut, e, id="", data=MaaPlanRead())
    return PlanCreateOut(id=str(uid), data=data)


@api.get(
    "",
    tags=["Get"],
    summary="查询全部计划表",
    response_model=PlanGetOut,
    index=[],
    data={},
)
async def list_plans() -> PlanGetOut:
    return await _build_plan_collection_out()


@api.get(
    "/{plan_id}",
    tags=["Get"],
    summary="查询单个计划表",
    response_model=PlanDetailOut,
    data=MaaPlanRead(),
)
async def get_plan(plan_id: PlanIdPath) -> PlanDetailOut:
    return await _build_plan_detail_out(plan_id)


@api.patch(
    "/{plan_id}",
    tags=["Update"],
    summary="更新计划表",
    response_model=OutBase,
)
async def update_plan(plan_id: PlanIdPath, body: PlanUpdateBody = Body(...)) -> OutBase:
    try:
        await Config.update_plan(plan_id, body.data.model_dump(exclude_unset=True))
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(OutBase, e)
    return OutBase()


@api.delete(
    "/{plan_id}",
    tags=["Delete"],
    summary="删除计划表",
    response_model=OutBase,
)
async def delete_plan(plan_id: PlanIdPath) -> OutBase:
    try:
        await Config.del_plan(plan_id)
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(OutBase, e)
    return OutBase()


@api.patch(
    "/order",
    tags=["Update"],
    summary="重新排序计划表",
    response_model=OutBase,
)
async def reorder_plan(body: IndexOrderPatch = Body(...)) -> OutBase:
    try:
        await Config.reorder_plan(body.index_list)
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(OutBase, e)
    return OutBase()
