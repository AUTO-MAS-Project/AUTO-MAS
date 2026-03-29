from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.constants import UTC4
from .config_base import MultipleConfig
from .common import Webhook
from .pydantic_base import PydanticConfigBase
from .type import UrlString


class GeneralUserConfig(PydanticConfigBase):
    """通用脚本用户配置"""

    class InfoModel(BaseModel):
        Name: str = "新用户"
        Status: bool = True
        RemainedDay: int = Field(default=-1, ge=-1, le=9999)
        IfScriptBeforeTask: bool = False
        ScriptBeforeTask: str = str(Path.cwd())
        IfScriptAfterTask: bool = False
        ScriptAfterTask: str = str(Path.cwd())
        Notes: str = "无"
        Tag: str = "[ ]"

    class DataModel(BaseModel):
        LastProxyDate: str = "2000-01-01"
        ProxyTimes: int = Field(default=0, ge=0, le=9999)

        @field_validator("LastProxyDate", mode="before")
        @classmethod
        def _normalize_ymd(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            try:
                datetime.strptime(text, "%Y-%m-%d")
                return text
            except ValueError:
                return "2000-01-01"

    class NotifyModel(BaseModel):
        Enabled: bool = False
        IfSendStatistic: bool = False
        IfSendMail: bool = False
        ToAddress: str = ""
        IfServerChan: bool = False
        ServerChanKey: str = ""

    Info: InfoModel = Field(default_factory=InfoModel)
    Data: DataModel = Field(default_factory=DataModel)
    Notify: NotifyModel = Field(default_factory=NotifyModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

    def _normalize_value(self, group: str, name: str, value: Any) -> Any:
        value = super()._normalize_value(group, name, value)
        if (group, name) == ("Info", "Tag"):
            return self.getTags()
        return value

    def get(self, group: str, name: str) -> Any:
        if (group, name) == ("Info", "Tag"):
            return self.getTags()
        return super().get(group, name)

    async def toDict(
        self, if_decrypt: bool = True, regenerate_uuids: bool = False
    ) -> dict[str, Any]:
        data = await super().toDict(if_decrypt, regenerate_uuids)
        info = data.get("Info")
        if isinstance(info, dict):
            info["Tag"] = self.getTags()
        return data

    def getTags(self) -> str:  # noqa: N802
        """生成通用用户标签列表"""
        tags: list[dict[str, str]] = []

        if (
            datetime.strptime(self.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
            == datetime.now(tz=UTC4).date()
        ):
            tags.append(
                {
                    "text": f"任务：已代理{self.get('Data', 'ProxyTimes')}次",
                    "color": "green",
                }
            )
        else:
            tags.append({"text": "任务：未代理", "color": "orange"})

        remained_day = self.get("Info", "RemainedDay")
        if remained_day == -1:
            tag_color = "gold"
        elif remained_day == 0:
            tag_color = "red"
        elif remained_day <= 3:
            tag_color = "orange"
        elif remained_day <= 7:
            tag_color = "yellow"
        elif remained_day <= 30:
            tag_color = "blue"
        else:
            tag_color = "green"
        tags.append(
            {
                "text": f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无期限",
                "color": tag_color,
            }
        )

        notes = self.get("Info", "Notes")
        tags.append(
            {
                "text": f"备注：{notes}"
                if len(notes) <= 20
                else f"备注：{notes[:20]}...",
                "color": "pink",
            }
        )

        return json.dumps(tags, ensure_ascii=False)


class GeneralConfig(PydanticConfigBase):
    """通用配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新通用脚本"
        RootPath: str = str(Path.cwd())

    class ScriptModel(BaseModel):
        ScriptPath: str = str(Path.cwd())
        Arguments: str = ""
        IfTrackProcess: bool = False
        TrackProcessName: str = ""
        TrackProcessExe: str = ""
        TrackProcessCmdline: str = ""
        ConfigPath: str = str(Path.cwd())
        ConfigPathMode: Literal["File", "Folder"] = "File"
        UpdateConfigMode: Literal["Never", "Success", "Failure", "Always"] = "Never"
        LogPath: str = str(Path.cwd())
        LogPathFormat: str = "%Y-%m-%d"
        LogTimeStart: int = Field(default=1, ge=1, le=9999)
        LogTimeEnd: int = Field(default=1, ge=1, le=9999)
        LogTimeFormat: str = "%Y-%m-%d %H:%M:%S"
        SuccessLog: str = ""
        ErrorLog: str = ""

    class GameModel(BaseModel):
        Enabled: bool = False
        Type: Literal["Emulator", "Client", "URL"] = "Emulator"
        Path: str = str(Path.cwd())
        URL: UrlString = ""
        ProcessName: str = ""
        Arguments: str = ""
        WaitTime: int = Field(default=0, ge=0, le=9999)
        IfForceClose: bool = False
        EmulatorId: str = "-"
        EmulatorIndex: str = "-"

    class RunModel(BaseModel):
        ProxyTimesLimit: int = Field(default=0, ge=0, le=9999)
        RunTimesLimit: int = Field(default=3, ge=1, le=9999)
        RunTimeLimit: int = Field(default=10, ge=1, le=9999)

    Info: InfoModel = Field(default_factory=InfoModel)
    Script: ScriptModel = Field(default_factory=ScriptModel)
    Game: GameModel = Field(default_factory=GameModel)
    Run: RunModel = Field(default_factory=RunModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.UserData = MultipleConfig([GeneralUserConfig])

    def _normalize_value(self, group: str, name: str, value: Any) -> Any:
        value = super()._normalize_value(group, name, value)

        if (group, name) != ("Game", "EmulatorId"):
            return value

        if value == "-":
            return "-"
        if not isinstance(value, str):
            return "-"
        try:
            uid = uuid.UUID(value)
        except (TypeError, ValueError):
            return "-"

        emulator_config = self.related_config.get("EmulatorConfig")
        if emulator_config is None or uid not in emulator_config:
            return "-"

        return str(uid)


__all__ = ["GeneralUserConfig", "GeneralConfig"]
