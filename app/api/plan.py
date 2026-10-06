#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""计划表配置 API（``Config.PlanConfig``）。"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import PlanEntry
from app.api import OutBase

router = APIRouter(prefix="/api/plan", tags=["计划表配置"])


class PlanCreateOut(OutBase):
    planId: str = Field(default="")
    data: PlanEntry = Field(default_factory=PlanEntry)


class PlanGetIn(BaseModel):
    planId: Optional[str] = None
    scriptType: Optional[str] = Field(
        default=None, description="按脚本 Entry 类型名筛选；缺省全部"
    )


class PlanGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, PlanEntry] = Field(default_factory=dict)


class PlanCreateIn(BaseModel):
    scriptType: str = Field(..., description="脚本 Entry 类型名；按其声明的计划表类新建")


class PlanUpdateIn(BaseModel):
    planId: str
    # 插件子类字段在基类上会被静默丢弃，补丁收原始结构、按实例真实类型校验
    data: dict[str, Any] = Field(..., description="补丁：只传要改的字段")


class PlanDeleteIn(BaseModel):
    planId: str


class PlanReorderIn(BaseModel):
    indexList: list[str]


@router.post("/add", tags=["Add"], summary="添加计划表", response_model=PlanCreateOut)
async def add_plan(body: PlanCreateIn = Body(...)) -> PlanCreateOut:
    try:
        from app.core.plugin_manager import Plugin

        plan_type = next(
            (
                d.plan_entry_type
                for d in Plugin.script_types.values()
                if d.entry_type.__name__ == body.scriptType
            ),
            None,
        )
        if plan_type is None:
            return PlanCreateOut(
                code=400,
                status="error",
                message=f"脚本类型 {body.scriptType} 未提供计划表",
                planId="",
                data=PlanEntry(),
            )
        col = Config.PlanConfig
        uid = col.add(plan_type)
        await col.commit()
        return PlanCreateOut(planId=str(uid), data=col[uid])
    except Exception as e:
        return PlanCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            planId="",
            data=PlanEntry(),
        )


@router.post("/get", tags=["Get"], summary="查询计划表", response_model=PlanGetOut)
async def get_plans(body: PlanGetIn = Body(...)) -> PlanGetOut:
    try:
        col = Config.PlanConfig
        if body.planId:
            uids = [UUID(body.planId)]
        elif body.scriptType:
            from app.core.plugin_manager import Plugin

            # combox：经 decl 把脚本类型换成它贡献的计划表类再筛
            plan_types = tuple(
                d.plan_entry_type
                for d in Plugin.script_types.values()
                if d.entry_type.__name__ == body.scriptType
                and d.plan_entry_type is not None
            )
            uids = [uid for uid in col.keys() if isinstance(col[uid], plan_types)]
        else:
            uids = list(col.keys())
        return PlanGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return PlanGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@router.post("/update", tags=["Update"], summary="更新计划表", response_model=OutBase)
async def update_plan(body: PlanUpdateIn = Body(...)) -> OutBase:
    try:
        entry = Config.PlanConfig[UUID(body.planId)]
        await entry.update(type(entry).model_validate(body.data))
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/delete", tags=["Delete"], summary="删除计划表", response_model=OutBase)
async def delete_plan(body: PlanDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.PlanConfig
        col.remove(body.planId)
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/order", tags=["Update"], summary="计划表排序", response_model=OutBase)
async def order_plans(body: PlanReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.PlanConfig
        col.set_order([UUID(x) for x in body.indexList])
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()
