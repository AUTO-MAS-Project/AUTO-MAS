from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.constants import UTC4
from app.core.config.base import MultipleConfig
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.shortcuts import config, ref, sub_configs, virtual
from app.core.config.types import DayCount, NonNegativeInt, PositiveInt, UrlString
from .common import Webhook


@config
@sub_configs(Notify_CustomWebhooks=[Webhook])
class GeneralUserConfig(PydanticConfigBase):
    """通用脚本用户配置"""

    class InfoModel(BaseModel):
        Name: str = "新用户"
        Status: bool = True
        RemainedDay: DayCount = -1
        IfScriptBeforeTask: bool = False
        ScriptBeforeTask: str = str(Path.cwd())
        IfScriptAfterTask: bool = False
        ScriptAfterTask: str = str(Path.cwd())
        Notes: str = "无"
        Tag: Annotated[
            str,
            virtual("getTags"),
        ] = "[ ]"

    class DataModel(BaseModel):
        LastProxyDate: str = "2000-01-01"
        ProxyTimes: NonNegativeInt = Field(default=0, le=9999)

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


@config
@sub_configs(UserData=[GeneralUserConfig])
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
        LogTimeStart: PositiveInt = Field(default=1, le=9999)
        LogTimeEnd: PositiveInt = Field(default=1, le=9999)
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
        WaitTime: NonNegativeInt = Field(default=0, le=9999)
        IfForceClose: bool = False
        EmulatorId: Annotated[
            str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                on_delete="set_default",
            ),
        ] = "-"
        EmulatorIndex: str = "-"

    class RunModel(BaseModel):
        ProxyTimesLimit: NonNegativeInt = Field(default=0, le=9999)
        RunTimesLimit: PositiveInt = Field(default=3, le=9999)
        RunTimeLimit: PositiveInt = Field(default=10, le=9999)

    Info: InfoModel = Field(default_factory=InfoModel)
    Script: ScriptModel = Field(default_factory=ScriptModel)
    Game: GameModel = Field(default_factory=GameModel)
    Run: RunModel = Field(default_factory=RunModel)


__all__ = ["GeneralUserConfig", "GeneralConfig"]
