from __future__ import annotations

import calendar
from typing import Annotated, Any, ClassVar, Literal, cast

from pydantic import AliasChoices, AliasPath, BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.shortcuts import config, ref, sub_configs
from app.core.config.types import (
    HHMMString,
    JsonDictString,
    JsonListString,
    PositiveInt,
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


@config
class EmulatorConfig(PydanticConfigBase):
    """模拟器配置"""

    class InfoModel(BaseModel):
        Name: str = "新模拟器"
        Type: EMULATOR_TYPES = Field(
            default="general",
            validation_alias=AliasChoices("Type", AliasPath("Data", "Type")),
        )
        Path: str = ""
        BossKey: JsonListString = Field(
            default="[ ]",
            validation_alias=AliasChoices("BossKey", AliasPath("Data", "BossKey")),
        )
        MaxWaitTime: PositiveInt = Field(
            default=60,
            le=9999,
            validation_alias=AliasChoices(
                "MaxWaitTime", AliasPath("Data", "MaxWaitTime")
            ),
        )

    Info: InfoModel = Field(default_factory=InfoModel)


@config
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


@config
class QueueItem(PydanticConfigBase):
    """队列项配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        ScriptId: Annotated[
            str,
            ref(
                "ScriptConfig",
                default="-",
                allow_values=("-",),
                on_delete="cascade",
            ),
        ] = "-"

    Info: InfoModel = Field(default_factory=InfoModel)


@config
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


@config
@sub_configs(TimeSet=[TimeSet], QueueItem=[QueueItem])
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


__all__ = ["EmulatorConfig", "Webhook", "QueueItem", "TimeSet", "QueueConfig"]
