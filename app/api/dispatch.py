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

router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])


@router.post("/add", summary="添加任务", response_model=OutBase, status_code=200)
async def add_plan(plan: DispatchIn = Body(...)) -> OutBase:

    uid, config = await Config.add_plan(plan.type)
    return OutBase(code=200, status="success", message="任务添加成功")


@router.post("/stop", summary="中止任务", response_model=OutBase, status_code=200)
async def stop_plan(plan: DispatchIn = Body(...)) -> OutBase:

    try:
        await Config.del_plan(plan.taskId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/order", summary="重新排序计划表", response_model=OutBase, status_code=200
)
async def reorder_plan(plan: PlanReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_plan(plan.indexList)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()
