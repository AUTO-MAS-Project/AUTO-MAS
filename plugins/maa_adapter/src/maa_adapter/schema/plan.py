"""MAA 计划表配置。"""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Ge, Le
from pydantic import Field

from auto_mas_core import ConfigGroup, PlanEntry, select

from ..constants import game_now
from .choices import _SERIES


class MaaPlanSlot(ConfigGroup):
    """计划表一天（或 ALL）的理智与关卡槽。"""

    medicine_numb: Annotated[int, Ge(0), Le(9999)] = Field(
        default=0, description="理智药数量"
    )
    series_numb: Annotated[Literal[*_SERIES], select()] = Field(
        default="0", description="连战次数"
    )
    stage: str = Field(default="-", description="关卡")
    stage_1: str = Field(default="-", description="关卡 1")
    stage_2: str = Field(default="-", description="关卡 2")
    stage_3: str = Field(default="-", description="关卡 3")



class MaaPlan(PlanEntry):
    """MAA 计划表。"""

    class Info(PlanEntry.Info):
        name: str = Field(default="新 MAA 计划表", description="计划表名称")
        mode: Annotated[Literal["ALL", "Weekly"], select()] = Field(
            default="ALL", description="计划表模式"
        )

    info: Info = Field(default_factory=Info, description="计划表信息")
    all: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="全部")
    monday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周一")
    tuesday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周二")
    wednesday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周三")
    thursday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周四")
    friday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周五")
    saturday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周六")
    sunday: MaaPlanSlot = Field(default_factory=MaaPlanSlot, description="周日")

    def slot(self, name: str) -> MaaPlanSlot:
        """按 ALL / 英文星期名取槽。"""

        key = "all" if name == "ALL" else name.lower()
        slot = getattr(self, key, None)
        if not isinstance(slot, MaaPlanSlot):
            return self.all
        return slot

    def get_current_info(self, name: str, server: str | None = None):
        """兼容旧 AutoProxy：返回带 getValue() 的当前槽位。"""

        value = self.current_value(name, server)

        class _Item:
            def getValue(self_inner) -> object:
                return value

        return _Item()

    def current_value(self, name: str, server: str | None = None) -> object:
        """当前生效的计划项：ALL 模式读 all，周模式按区服游戏日。"""

        attr = {
            "MedicineNumb": "medicine_numb",
            "SeriesNumb": "series_numb",
            "Stage": "stage",
            "Stage_1": "stage_1",
            "Stage_2": "stage_2",
            "Stage_3": "stage_3",
        }.get(name, name)
        if self.info.mode == "ALL":
            return getattr(self.all, attr)
        today = game_now(server).strftime("%A")
        return getattr(self.slot(today), attr)



