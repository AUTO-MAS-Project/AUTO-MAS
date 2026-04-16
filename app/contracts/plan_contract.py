from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from pydantic import AliasChoices, Field

from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
)


WEEKDAY_META: tuple[tuple[str, str, str], ...] = (
    ("monday", "Monday", "周一"),
    ("tuesday", "Tuesday", "周二"),
    ("wednesday", "Wednesday", "周三"),
    ("thursday", "Thursday", "周四"),
    ("friday", "Friday", "周五"),
    ("saturday", "Saturday", "周六"),
    ("sunday", "Sunday", "周日"),
)


def _iter_weekday_fields(
    day_model: type[ApiModel], *, optional: bool
) -> Iterator[tuple[str, object, object]]:
    """按 `WEEKDAY_META` 生成周字段定义。

    Args:
        day_model: 星期字段对应的数据模型类型（如 `MaaPlanDayRead` / `MaaPlanDayPatch`）。
        optional: 是否生成可选字段。
            - `False`：字段类型为 `day_model`，使用 `default_factory=day_model`。
            - `True`：字段类型为 `day_model | None`，使用 `default=None`。

    Yields:
        三元组 `(field_name, field_type, field_info)`，用于在类体内批量写入
        `__annotations__` 和字段默认值。
    """
    for day_key, day_alias, day_desc in WEEKDAY_META:
        if optional:
            yield (
                day_key,
                day_model | None,
                Field(
                    default=None,
                    validation_alias=AliasChoices(day_key, day_alias),
                    serialization_alias=day_alias,
                    description=day_desc,
                ),
            )
            continue

        yield (
            day_key,
            day_model,
            Field(
                default_factory=day_model,
                validation_alias=AliasChoices(day_key, day_alias),
                serialization_alias=day_alias,
                description=day_desc,
            ),
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

    # 自动展开的星期项
    for wk_key, wk_type, wk_field in _iter_weekday_fields(
        MaaPlanDayRead, optional=False
    ):
        __annotations__[wk_key] = wk_type
        locals()[wk_key] = wk_field
    del wk_key, wk_type, wk_field


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

    # 自动展开的星期项
    for wk_key, wk_type, wk_field in _iter_weekday_fields(
        MaaPlanDayPatch, optional=True
    ):
        __annotations__[wk_key] = wk_type
        locals()[wk_key] = wk_field
    del wk_key, wk_type, wk_field


class PlanCreateIn(ApiModel):
    type: Literal["MaaPlan"] = Field(..., description="计划类型")


class PlanUpdateBody(ApiModel):
    data: MaaPlanPatch = Field(..., description="计划更新数据")


class PlanCreateOut(ResourceCreateOut[MaaPlanRead]):
    """计划创建响应模型"""


class PlanDetailOut(ResourceItemOut[MaaPlanRead]):
    """计划详情响应模型"""


class PlanGetOut(ResourceCollectionOut[PlanIndexItem, MaaPlanRead]):
    """计划列表响应模型"""


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
