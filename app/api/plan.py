#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import *

router = APIRouter(prefix="/api/plan", tags=["计划管理"])


@router.post(
    "/add", summary="添加计划表", response_model=PlanCreateOut, status_code=200
)
async def add_plan(plan: PlanCreateIn = Body(...)) -> PlanCreateOut:

    try:
        uid, config = await Config.add_plan(plan.type)
        data = MaaPlanConfig(**(await config.toDict()))
    except Exception as e:
        return PlanCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            planId="",
            data=MaaPlanConfig(**{}),
        )
    return PlanCreateOut(planId=str(uid), data=data)


@router.post("/get", summary="查询计划表", response_model=PlanGetOut, status_code=200)
async def get_plan(plan: PlanGetIn = Body(...)) -> PlanGetOut:

    try:
        index, data = await Config.get_plan(plan.planId)
        index = [PlanIndexItem(**_) for _ in index]
        data = {uid: MaaPlanConfig(**cfg) for uid, cfg in data.items()}
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
    "/update", summary="更新计划表配置信息", response_model=OutBase, status_code=200
)
async def update_plan(plan: PlanUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_plan(plan.planId, plan.data.model_dump(exclude_unset=True))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post("/delete", summary="删除计划表", response_model=OutBase, status_code=200)
async def delete_plan(plan: PlanDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_plan(plan.planId)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order", summary="重新排序计划表", response_model=OutBase, status_code=200
)
async def reorder_plan(plan: PlanReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_plan(plan.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
