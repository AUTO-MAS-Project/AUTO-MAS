from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import datetime
from typing import Annotated, Literal

from auto_mas_core import PlanEntry
from auto_mas_core.host.config import (
    ConfigGroup,
    Virtual,
    virtual_field,
)
from auto_mas_core.host.models_config_shared import (
    none_as,
    schema_model,
)
from pydantic import Field

from maa_adapter.config.fields import StageCode
from maa_adapter.constants import (
    game_now,
)


# Pydantic 子类重新声明并收窄字段，沿用配置模型的逐字段继承豁免。
class PlanDaysConfig(PlanEntry):
    """计划槽位以星期和 DayN 配置分组保存，按当前模式选择生效槽位。"""

    @staticmethod
    def day_group_of(day: str) -> str | None:
        """将星期名称或合法轮换天数转换为计划分组名，不支持的输入返回空值。"""
        if day in calendar.day_name:
            return day
        if day.isdigit() and 1 <= int(day) <= schema_model.PLAN_ROTATE_DAYS_MAX:
            return f"Day{int(day)}"
        return None

    def rotate_days(self) -> int:
        """读取计划配置设定的轮换周期天数。"""
        return getattr(self, "Info").RotateDays

    def rotate_group(self, now: datetime) -> str:
        """按给定日期和轮换周期计算当前应采用的 Day 分组。"""
        return f"Day{now.date().toordinal() % self.rotate_days() + 1}"

    def current_group(self, now: datetime) -> str:
        """按统一、每周或轮换模式选择给定时间对应的计划分组。"""
        mode = getattr(self, "Info").Mode
        if mode == "ALL":
            return "ALL"
        if mode == "Weekly":
            return now.strftime("%A")
        if mode == "Rotate":
            return self.rotate_group(now)
        raise ValueError("非法的计划表模式")


class MaaPlanConfig(PlanDaysConfig):
    @classmethod
    def normalize_payload(cls, data):
        """将历史 Days 容器展开为当前计划分组，保留所有合法星期和轮换槽位。"""
        data = deepcopy(data)
        days = data.pop("Days", None)
        if isinstance(days, dict):
            for day, values in days.items():
                group = cls.day_group_of(str(day))
                if group is not None:
                    data[group] = values
        return data

    def get_current_info(self, name: str, server: str | None = None):
        """按服务器游戏时间选择当前计划分组，并返回调用方指定的计划字段。"""
        group = self.current_group(game_now(server))
        return getattr(getattr(self, group), name)

    "MAA计划表配置"

    class ALLFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    ALL: ALLFields = Field(default_factory=ALLFields)

    class FridayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Friday: FridayFields = Field(default_factory=FridayFields)

    Day1: ALLFields = Field(default_factory=ALLFields)
    Day2: ALLFields = Field(default_factory=ALLFields)
    Day3: ALLFields = Field(default_factory=ALLFields)
    Day4: ALLFields = Field(default_factory=ALLFields)
    Day5: ALLFields = Field(default_factory=ALLFields)
    Day6: ALLFields = Field(default_factory=ALLFields)
    Day7: ALLFields = Field(default_factory=ALLFields)
    Day8: ALLFields = Field(default_factory=ALLFields)
    Day9: ALLFields = Field(default_factory=ALLFields)
    Day10: ALLFields = Field(default_factory=ALLFields)
    Day11: ALLFields = Field(default_factory=ALLFields)
    Day12: ALLFields = Field(default_factory=ALLFields)
    Day13: ALLFields = Field(default_factory=ALLFields)
    Day14: ALLFields = Field(default_factory=ALLFields)
    Day15: ALLFields = Field(default_factory=ALLFields)
    Day16: ALLFields = Field(default_factory=ALLFields)
    Day17: ALLFields = Field(default_factory=ALLFields)
    Day18: ALLFields = Field(default_factory=ALLFields)
    Day19: ALLFields = Field(default_factory=ALLFields)
    Day20: ALLFields = Field(default_factory=ALLFields)
    Day21: ALLFields = Field(default_factory=ALLFields)
    Day22: ALLFields = Field(default_factory=ALLFields)
    Day23: ALLFields = Field(default_factory=ALLFields)
    Day24: ALLFields = Field(default_factory=ALLFields)
    Day25: ALLFields = Field(default_factory=ALLFields)
    Day26: ALLFields = Field(default_factory=ALLFields)
    Day27: ALLFields = Field(default_factory=ALLFields)
    Day28: ALLFields = Field(default_factory=ALLFields)
    Day29: ALLFields = Field(default_factory=ALLFields)
    Day30: ALLFields = Field(default_factory=ALLFields)
    Day31: ALLFields = Field(default_factory=ALLFields)

    class InfoFields(ConfigGroup):
        RotateDays: Annotated[int, Field(ge=1, le=31)] = Field(
            default=7, description="多天轮换天数"
        )
        Mode: Literal["ALL", "Weekly", "Rotate"] = Field(
            default_factory=lambda: "ALL", description="计划表模式"
        )

        Name: str = Field(
            default_factory=lambda: "新 MAA 计划表", description="计划表名称"
        )

    Info: InfoFields = Field(default_factory=InfoFields)  # pyright: ignore[reportIncompatibleVariableOverride]

    class MondayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Monday: MondayFields = Field(default_factory=MondayFields)

    class SaturdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Saturday: SaturdayFields = Field(default_factory=SaturdayFields)

    class SundayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Sunday: SundayFields = Field(default_factory=SundayFields)

    class ThursdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Thursday: ThursdayFields = Field(default_factory=ThursdayFields)

    class TuesdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Tuesday: TuesdayFields = Field(default_factory=TuesdayFields)

    class WednesdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: StageCode = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: StageCode = Field(
            description="备选关卡 - 1", default_factory=lambda: "-"
        )

        Stage_2: StageCode = Field(
            description="备选关卡 - 2", default_factory=lambda: "-"
        )

        Stage_3: StageCode = Field(
            description="备选关卡 - 3", default_factory=lambda: "-"
        )

    Wednesday: WednesdayFields = Field(default_factory=WednesdayFields)

    class Metadata(PlanEntry.Info):
        # 来源兼容字段改为虚拟读取；Virtual 的冷态 None 与父类可写字段类型不同。
        name: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    info: Metadata = Field(default_factory=Metadata)  # pyright: ignore[reportIncompatibleVariableOverride]

    @virtual_field("info.name")
    def plugin_name(self):
        """将来源计划的名称字段提供给插件计划基类使用。"""
        return self.Info.Name
