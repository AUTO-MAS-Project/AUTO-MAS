from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field

from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
)


class PlanIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["MaaPlanConfig"] = Field(..., description="配置类型")


class MaaPlanInfoRead(ApiModel):
    name: str = Field(
        default="新 MAA 计划表",
        validation_alias=AliasChoices("name", "Name"),
        serialization_alias="Name",
        description="计划表名称",
    )
    mode: Literal["ALL", "Weekly"] = Field(
        default="ALL",
        validation_alias=AliasChoices("mode", "Mode"),
        serialization_alias="Mode",
        description="计划表模式",
    )


class MaaPlanInfoPatch(ApiModel):
    name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("name", "Name"),
        serialization_alias="Name",
        description="计划表名称",
    )
    mode: Literal["ALL", "Weekly"] | None = Field(
        default=None,
        validation_alias=AliasChoices("mode", "Mode"),
        serialization_alias="Mode",
        description="计划表模式",
    )


class MaaPlanDayRead(ApiModel):
    medicine_numb: int = Field(
        default=0,
        validation_alias=AliasChoices("medicine_numb", "MedicineNumb"),
        serialization_alias="MedicineNumb",
        description="吃理智药",
    )
    series_numb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
        default="0",
        validation_alias=AliasChoices("series_numb", "SeriesNumb"),
        serialization_alias="SeriesNumb",
        description="连战次数",
    )
    stage: str = Field(
        default="-",
        validation_alias=AliasChoices("stage", "Stage"),
        serialization_alias="Stage",
        description="关卡选择",
    )
    stage_1: str = Field(
        default="-",
        validation_alias=AliasChoices("stage_1", "Stage_1"),
        serialization_alias="Stage_1",
        description="备选关卡 - 1",
    )
    stage_2: str = Field(
        default="-",
        validation_alias=AliasChoices("stage_2", "Stage_2"),
        serialization_alias="Stage_2",
        description="备选关卡 - 2",
    )
    stage_3: str = Field(
        default="-",
        validation_alias=AliasChoices("stage_3", "Stage_3"),
        serialization_alias="Stage_3",
        description="备选关卡 - 3",
    )
    stage_remain: str = Field(
        default="-",
        validation_alias=AliasChoices("stage_remain", "Stage_Remain"),
        serialization_alias="Stage_Remain",
        description="剩余理智关卡",
    )


class MaaPlanDayPatch(ApiModel):
    medicine_numb: int | None = Field(
        default=None,
        validation_alias=AliasChoices("medicine_numb", "MedicineNumb"),
        serialization_alias="MedicineNumb",
        description="吃理智药",
    )
    series_numb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] | None = Field(
        default=None,
        validation_alias=AliasChoices("series_numb", "SeriesNumb"),
        serialization_alias="SeriesNumb",
        description="连战次数",
    )
    stage: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stage", "Stage"),
        serialization_alias="Stage",
        description="关卡选择",
    )
    stage_1: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stage_1", "Stage_1"),
        serialization_alias="Stage_1",
        description="备选关卡 - 1",
    )
    stage_2: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stage_2", "Stage_2"),
        serialization_alias="Stage_2",
        description="备选关卡 - 2",
    )
    stage_3: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stage_3", "Stage_3"),
        serialization_alias="Stage_3",
        description="备选关卡 - 3",
    )
    stage_remain: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stage_remain", "Stage_Remain"),
        serialization_alias="Stage_Remain",
        description="剩余理智关卡",
    )


class MaaPlanRead(ApiModel):
    info: MaaPlanInfoRead = Field(
        default_factory=MaaPlanInfoRead,
        validation_alias=AliasChoices("info", "Info"),
        serialization_alias="Info",
        description="基础信息",
    )
    all_days: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("all_days", "ALL"),
        serialization_alias="ALL",
        description="全局",
    )
    monday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("monday", "Monday"),
        serialization_alias="Monday",
        description="周一",
    )
    tuesday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("tuesday", "Tuesday"),
        serialization_alias="Tuesday",
        description="周二",
    )
    wednesday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("wednesday", "Wednesday"),
        serialization_alias="Wednesday",
        description="周三",
    )
    thursday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("thursday", "Thursday"),
        serialization_alias="Thursday",
        description="周四",
    )
    friday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("friday", "Friday"),
        serialization_alias="Friday",
        description="周五",
    )
    saturday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("saturday", "Saturday"),
        serialization_alias="Saturday",
        description="周六",
    )
    sunday: MaaPlanDayRead = Field(
        default_factory=MaaPlanDayRead,
        validation_alias=AliasChoices("sunday", "Sunday"),
        serialization_alias="Sunday",
        description="周日",
    )


class MaaPlanPatch(ApiModel):
    info: MaaPlanInfoPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("info", "Info"),
        serialization_alias="Info",
        description="基础信息",
    )
    all_days: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("all_days", "ALL"),
        serialization_alias="ALL",
        description="全局",
    )
    monday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("monday", "Monday"),
        serialization_alias="Monday",
        description="周一",
    )
    tuesday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("tuesday", "Tuesday"),
        serialization_alias="Tuesday",
        description="周二",
    )
    wednesday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("wednesday", "Wednesday"),
        serialization_alias="Wednesday",
        description="周三",
    )
    thursday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("thursday", "Thursday"),
        serialization_alias="Thursday",
        description="周四",
    )
    friday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("friday", "Friday"),
        serialization_alias="Friday",
        description="周五",
    )
    saturday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("saturday", "Saturday"),
        serialization_alias="Saturday",
        description="周六",
    )
    sunday: MaaPlanDayPatch | None = Field(
        default=None,
        validation_alias=AliasChoices("sunday", "Sunday"),
        serialization_alias="Sunday",
        description="周日",
    )


class PlanCreateIn(ApiModel):
    type: Literal["MaaPlan"] = Field(..., description="计划类型")


class PlanUpdateBody(ApiModel):
    data: MaaPlanPatch = Field(..., description="计划更新数据")


PlanCreateOut = ResourceCreateOut[MaaPlanRead]
PlanDetailOut = ResourceItemOut[MaaPlanRead]
PlanGetOut = ResourceCollectionOut[PlanIndexItem, MaaPlanRead]


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
    "PlanDetailOut",
    "PlanGetOut",
    "PlanUpdateBody",
]
