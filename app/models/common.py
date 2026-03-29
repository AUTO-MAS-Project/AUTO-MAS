from __future__ import annotations
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportGeneralTypeIssues=false

import calendar
import uuid
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from .config_base import MultipleConfig
from .pydantic_base import PydanticConfigBase
from .type import HHMMString, JsonDictString, JsonListString, UrlString, YmdHmString


DAY_NAMES = tuple(calendar.day_name)
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
        ScriptId: str = "-"

    Info: InfoModel = Field(default_factory=InfoModel)

    def _normalize_value(self, group: str, name: str, value: Any) -> Any:
        value = super()._normalize_value(group, name, value)

        if (group, name) != ("Info", "ScriptId"):
            return value

        if value == "-":
            return "-"
        if not isinstance(value, str):
            return "-"

        try:
            uid = uuid.UUID(value)
        except (TypeError, ValueError):
            return "-"

        script_config = self.related_config.get("ScriptConfig")
        if script_config is None or uid not in script_config:
            return "-"

        return str(uid)


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
            days: list[str] = [item for item in value if isinstance(item, str)]
            return (
                days
                if len(days) == len(value) and all(item in DAY_NAMES for item in days)
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
        # MultipleConfig 目前约束 T 继承 ConfigBase；这里保持运行时兼容。
        self.TimeSet = MultipleConfig([TimeSet])  # pyright: ignore[reportArgumentType]
        self.QueueItem = MultipleConfig([QueueItem])  # pyright: ignore[reportArgumentType]


__all__ = ["EmulatorConfig", "Webhook", "QueueItem", "TimeSet", "QueueConfig"]
