#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


from __future__ import annotations

import calendar
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.config import (
    ConfigGroup,
)
from app.utils import constants as _utils_constants

from .base import DomainEntry
from .shared import (
    default_baah_plan_key,
    none_as,
    normalize_baah_plan_key,
    normalize_maaend_plan_key,
    normalize_mss_plan_key,
    schema_model,
)


class PlanDaysConfig(DomainEntry):
    """计划槽位以星期和 DayN 配置分组保存，按当前模式选择生效槽位。"""

    @staticmethod
    def day_group_of(day: str) -> str | None:
        if day in calendar.day_name:
            return day
        if day.isdigit() and 1 <= int(day) <= schema_model.PLAN_ROTATE_DAYS_MAX:
            return f"Day{int(day)}"
        return None

    def rotate_days(self) -> int:
        return getattr(self, "Info").RotateDays

    def rotate_group(self, now: datetime) -> str:
        return f"Day{now.date().toordinal() % self.rotate_days() + 1}"

    def current_group(self, now: datetime) -> str:
        mode = getattr(self, "Info").Mode
        if mode == "ALL":
            return "ALL"
        if mode == "Weekly":
            return now.strftime("%A")
        if mode == "Rotate":
            return self.rotate_group(now)
        raise ValueError("非法的计划表模式")


class WeeklyKeyPlan(PlanDaysConfig):
    def get_current_key(self):
        key = getattr(
            self, self.current_group(datetime.now(tz=_utils_constants.UTC4))
        ).Key
        return key.model_dump(exclude_none=True)


class MaaPlanConfig(PlanDaysConfig):
    def get_current_info(self, name: str, server: str | None = None):
        group = self.current_group(_utils_constants.game_now(server))
        return getattr(getattr(self, group), name)

    "MAA计划表配置"

    class ALLFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    ALL: ALLFields = Field(default_factory=ALLFields)

    class FridayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

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

    Info: InfoFields = Field(default_factory=InfoFields)

    class MondayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Monday: MondayFields = Field(default_factory=MondayFields)

    class SaturdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Saturday: SaturdayFields = Field(default_factory=SaturdayFields)

    class SundayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Sunday: SundayFields = Field(default_factory=SundayFields)

    class ThursdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Thursday: ThursdayFields = Field(default_factory=ThursdayFields)

    class TuesdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Tuesday: TuesdayFields = Field(default_factory=TuesdayFields)

    class WednesdayFields(ConfigGroup):
        MedicineNumb: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="吃理智药", default_factory=lambda: 0
        )

        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = Field(
            description="连战次数", default_factory=lambda: "0"
        )

        Stage: str = Field(description="关卡选择", default_factory=lambda: "-")

        Stage_1: str = Field(description="备选关卡 - 1", default_factory=lambda: "-")

        Stage_2: str = Field(description="备选关卡 - 2", default_factory=lambda: "-")

        Stage_3: str = Field(description="备选关卡 - 3", default_factory=lambda: "-")

    Wednesday: WednesdayFields = Field(default_factory=WednesdayFields)


class MaaEndPlanConfig(WeeklyKeyPlan):
    "MaaEnd 计划表配置。"

    class ALLFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    ALL: ALLFields = Field(default_factory=ALLFields)

    class FridayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
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
            description="计划表模式", default_factory=lambda: "ALL"
        )

        Name: str = Field(
            description="计划表名称", default_factory=lambda: "新 MaaEnd 计划表"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class MondayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Monday: MondayFields = Field(default_factory=MondayFields)

    class SaturdayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Saturday: SaturdayFields = Field(default_factory=SaturdayFields)

    class SundayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Sunday: SundayFields = Field(default_factory=SundayFields)

    class ThursdayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Thursday: ThursdayFields = Field(default_factory=ThursdayFields)

    class TuesdayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Tuesday: TuesdayFields = Field(default_factory=TuesdayFields)

    class WednesdayFields(ConfigGroup):
        Key: schema_model.MaaEndPlanKey = Field(
            description="MaaEnd 计划表专项 key",
            default_factory=schema_model.MaaEndProtocolSpacePlanKey,
        )

    Wednesday: WednesdayFields = Field(default_factory=WednesdayFields)

    @classmethod
    def normalize_payload(cls, data):
        normalized_data = super().normalize_payload(data)
        for group in ["ALL", *calendar.day_name, *(f"Day{i}" for i in range(1, 32))]:
            group_data = normalized_data.get(group)
            if isinstance(group_data, dict):
                normalized_data[group] = {"Key": normalize_maaend_plan_key(group_data)}
        return normalized_data


class BAAHPlanConfig(WeeklyKeyPlan):
    "BAAH 计划表配置。"

    def get_current_key(self) -> dict[str, list[int]]:
        """活动关卡由 BAAH 自身配置维护，不从计划表下发。"""
        key = super().get_current_key()
        key.pop("Event", None)
        return key

    class ALLFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    ALL: ALLFields = Field(default_factory=ALLFields)

    class FridayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
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
            default=3, description="多天轮换天数"
        )
        Mode: Literal["ALL", "Weekly", "Rotate"] = Field(
            description="计划表模式", default_factory=lambda: "ALL"
        )

        Name: str = Field(
            description="计划表名称", default_factory=lambda: "新 BAAH 计划表"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class MondayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Monday: MondayFields = Field(default_factory=MondayFields)

    class SaturdayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Saturday: SaturdayFields = Field(default_factory=SaturdayFields)

    class SundayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Sunday: SundayFields = Field(default_factory=SundayFields)

    class ThursdayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Thursday: ThursdayFields = Field(default_factory=ThursdayFields)

    class TuesdayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Tuesday: TuesdayFields = Field(default_factory=TuesdayFields)

    class WednesdayFields(ConfigGroup):
        Key: schema_model.BAAHPlanKey = Field(
            description="BAAH 计划表专项 key",
            default_factory=lambda: schema_model.BAAHPlanKey.model_validate(
                default_baah_plan_key()
            ),
        )

    Wednesday: WednesdayFields = Field(default_factory=WednesdayFields)

    @classmethod
    def normalize_payload(cls, data):
        normalized_data = super().normalize_payload(data)
        for group in ["ALL", *calendar.day_name, *(f"Day{i}" for i in range(1, 32))]:
            group_data = normalized_data.get(group)
            if isinstance(group_data, dict) and group_data:
                normalized_data[group] = {"Key": normalize_baah_plan_key(group_data)}
        return normalized_data


class MSSPlanConfig(WeeklyKeyPlan):
    "MSS 计划表配置：每个日期槽位存一套悬赏试炼配置。"

    class ALLFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    ALL: ALLFields = Field(default_factory=ALLFields)

    class FridayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
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
            description="计划表模式", default_factory=lambda: "ALL"
        )

        Name: str = Field(
            description="计划表名称", default_factory=lambda: "新 MSS 计划表"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class MondayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Monday: MondayFields = Field(default_factory=MondayFields)

    class SaturdayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Saturday: SaturdayFields = Field(default_factory=SaturdayFields)

    class SundayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Sunday: SundayFields = Field(default_factory=SundayFields)

    class ThursdayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Thursday: ThursdayFields = Field(default_factory=ThursdayFields)

    class TuesdayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Tuesday: TuesdayFields = Field(default_factory=TuesdayFields)

    class WednesdayFields(ConfigGroup):
        Key: schema_model.MSSPlanKey = Field(
            description="MSS 计划表专项 key",
            default_factory=schema_model.MSSPlanKey,
        )

    Wednesday: WednesdayFields = Field(default_factory=WednesdayFields)

    @classmethod
    def normalize_payload(cls, data):
        normalized_data = super().normalize_payload(data)
        for group in ["ALL", *calendar.day_name, *(f"Day{i}" for i in range(1, 32))]:
            group_data = normalized_data.get(group)
            if isinstance(group_data, dict):
                normalized_data[group] = {"Key": normalize_mss_plan_key(group_data)}
        return normalized_data


__all__ = [
    "WeeklyKeyPlan",
    "MaaPlanConfig",
    "MaaEndPlanConfig",
    "BAAHPlanConfig",
    "MSSPlanConfig",
]
