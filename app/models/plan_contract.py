from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase


class PlanIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["MaaPlanConfig"] = Field(..., description="配置类型")


class MaaPlanInfoRead(ApiModel):
    Name: str = Field(default="新 MAA 计划表", description="计划表名称")
    Mode: Literal["ALL", "Weekly"] = Field(default="ALL", description="计划表模式")


class MaaPlanInfoPatch(ApiModel):
    Name: str | None = Field(default=None, description="计划表名称")
    Mode: Literal["ALL", "Weekly"] | None = Field(
        default=None, description="计划表模式"
    )


class MaaPlanDayRead(ApiModel):
    MedicineNumb: int = Field(default=0, description="吃理智药")
    SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
        default="0", description="连战次数"
    )
    Stage: str = Field(default="-", description="关卡选择")
    Stage_1: str = Field(default="-", description="备选关卡 - 1")
    Stage_2: str = Field(default="-", description="备选关卡 - 2")
    Stage_3: str = Field(default="-", description="备选关卡 - 3")
    Stage_Remain: str = Field(default="-", description="剩余理智关卡")


class MaaPlanDayPatch(ApiModel):
    MedicineNumb: int | None = Field(default=None, description="吃理智药")
    SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] | None = Field(
        default=None, description="连战次数"
    )
    Stage: str | None = Field(default=None, description="关卡选择")
    Stage_1: str | None = Field(default=None, description="备选关卡 - 1")
    Stage_2: str | None = Field(default=None, description="备选关卡 - 2")
    Stage_3: str | None = Field(default=None, description="备选关卡 - 3")
    Stage_Remain: str | None = Field(default=None, description="剩余理智关卡")


class MaaPlanRead(ApiModel):
    Info: MaaPlanInfoRead = Field(default_factory=MaaPlanInfoRead, description="基础信息")
    ALL: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="全局")
    Monday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周一")
    Tuesday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周二")
    Wednesday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周三")
    Thursday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周四")
    Friday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周五")
    Saturday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周六")
    Sunday: MaaPlanDayRead = Field(default_factory=MaaPlanDayRead, description="周日")


class MaaPlanPatch(ApiModel):
    Info: MaaPlanInfoPatch | None = Field(default=None, description="基础信息")
    ALL: MaaPlanDayPatch | None = Field(default=None, description="全局")
    Monday: MaaPlanDayPatch | None = Field(default=None, description="周一")
    Tuesday: MaaPlanDayPatch | None = Field(default=None, description="周二")
    Wednesday: MaaPlanDayPatch | None = Field(default=None, description="周三")
    Thursday: MaaPlanDayPatch | None = Field(default=None, description="周四")
    Friday: MaaPlanDayPatch | None = Field(default=None, description="周五")
    Saturday: MaaPlanDayPatch | None = Field(default=None, description="周六")
    Sunday: MaaPlanDayPatch | None = Field(default=None, description="周日")


class PlanCreateIn(ApiModel):
    type: Literal["MaaPlan"] = Field(..., description="计划类型")


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: MaaPlanRead = Field(..., description="计划配置数据")


class PlanGetIn(ApiModel):
    planId: str | None = Field(
        default=None, description="计划ID, 未携带时表示获取所有计划数据"
    )


class PlanGetOut(OutBase):
    index: list[PlanIndexItem] = Field(..., description="计划索引列表")
    data: dict[str, MaaPlanRead] = Field(..., description="计划列表或单个计划数据")


class PlanUpdateIn(ApiModel):
    planId: str = Field(..., description="计划ID")
    data: MaaPlanPatch = Field(..., description="计划更新数据")


class PlanDeleteIn(ApiModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(ApiModel):
    indexList: list[str] = Field(..., description="计划ID列表, 按新顺序排列")


__all__ = [
    "PlanIndexItem",
    "MaaPlanInfoRead",
    "MaaPlanInfoPatch",
    "MaaPlanDayRead",
    "MaaPlanDayPatch",
    "MaaPlanRead",
    "MaaPlanPatch",
    "PlanCreateIn",
    "PlanCreateOut",
    "PlanGetIn",
    "PlanGetOut",
    "PlanUpdateIn",
    "PlanDeleteIn",
    "PlanReorderIn",
]
