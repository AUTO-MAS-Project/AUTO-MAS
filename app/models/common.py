from __future__ import annotations

import calendar
from typing import Annotated, Any, ClassVar, Literal, cast

from pydantic import BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.fields import RefField
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.types import (
    HHMMString,
    JsonDictString,
    JsonListString,
    UrlString,
    YmdHmString,
)


DAY_NAMES: tuple[str, ...] = tuple(calendar.day_name)
EMULATOR_TYPES = Literal["general", "mumu", "ldplayer"]
AFTER_ACCOMPLISH_OPTIONS = Literal[
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
]
HTTP_METHOD = Literal["POST", "GET"]


class EmulatorConfig(PydanticConfigBase):
    """模拟器配置"""

    class InfoModel(BaseModel):
        Name: str = "新模拟器"
        Type: EMULATOR_TYPES = "general"
        Path: str = ""
        BossKey: JsonListString = "[ ]"
        MaxWaitTime: int = Field(default=60, ge=1, le=9999)

    Info: InfoModel = Field(default_factory=InfoModel)

    LEGACY_FIELD_MAP: ClassVar[dict[tuple[str, str], tuple[str, str]]] = {
        ("Info", "Type"): ("Data", "Type"),
        ("Info", "BossKey"): ("Data", "BossKey"),
        ("Info", "MaxWaitTime"): ("Data", "MaxWaitTime"),
    }


class Webhook(PydanticConfigBase):
    """Webhook 配置"""

    class InfoModel(BaseModel):
        Name: str = "新自定义 Webhook 通知"
        Enabled: bool = True

    class DataModel(BaseModel):
        Url: UrlString = ""
        Template: str = ""
        Headers: JsonDictString = "{ }"
        Method: HTTP_METHOD = "POST"

    Info: InfoModel = Field(default_factory=InfoModel)
    Data: DataModel = Field(default_factory=DataModel)


class QueueItem(PydanticConfigBase):
    """队列项配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        ScriptId: Annotated[
            str,
            RefField(
                "ScriptConfig",
                default="-",
                allow_values=("-",),
                on_delete="cascade",
            ),
        ] = "-"

    Info: InfoModel = Field(default_factory=InfoModel)


class TimeSet(PydanticConfigBase):
    """时间设置配置"""

    class InfoModel(BaseModel):
        Enabled: bool = True
        Days: list[str] = Field(default_factory=lambda: list(DAY_NAMES))
        Time: HHMMString = "00:00"

        @field_validator("Days", mode="before")
        @classmethod
        def _validate_days(cls, value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            raw_days = cast(list[object], value)
            days: list[str] = [item for item in raw_days if isinstance(item, str)]
            return (
                days
                if len(days) == len(raw_days)
                and all(item in DAY_NAMES for item in days)
                else []
            )

    Info: InfoModel = Field(default_factory=InfoModel)


class QueueConfig(PydanticConfigBase):
    """队列配置"""

    class InfoModel(BaseModel):
        Name: str = "新队列"
        TimeEnabled: bool = False
        StartUpEnabled: bool = False
        AfterAccomplish: AFTER_ACCOMPLISH_OPTIONS = "NoAction"

    class DataModel(BaseModel):
        LastTimedStart: YmdHmString = "2000-01-01 00:00"

    Info: InfoModel = Field(default_factory=InfoModel)
    Data: DataModel = Field(default_factory=DataModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.TimeSet: MultipleConfig[TimeSet] = MultipleConfig([TimeSet])
        self.QueueItem: MultipleConfig[QueueItem] = MultipleConfig([QueueItem])


__all__ = ["EmulatorConfig", "Webhook", "QueueItem", "TimeSet", "QueueConfig"]
