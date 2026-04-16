from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.shortcuts import config, ref, sub_configs, virtual
from app.core.config.types import DayCount, EncryptedString, NonNegativeInt, PositiveInt
from app.utils.constants import MAAEND_STAGE_BOOK, MAAEND_STAGE_WITH_AB, UTC4, UTC8
from .common import Webhook


@config
@sub_configs(Notify_CustomWebhooks=[Webhook])
class MaaEndUserConfig(PydanticConfigBase):
    """MaaEnd用户配置"""

    class InfoModel(BaseModel):
        Name: str = "新用户"
        Status: bool = True
        Id: str = ""
        Password: EncryptedString = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        Resource: Literal["官服"] = "官服"
        RemainedDay: DayCount = -1
        Notes: str = "无"
        IfSkland: bool = False
        SklandToken: EncryptedString = ""
        Tag: Annotated[
            str,
            virtual("getTags"),
        ] = "[ ]"

    class TaskModel(BaseModel):
        ProtocolSpaceTab: Literal[
            "OperatorProgression", "WeaponProgression", "CrisisDrills"
        ] = "OperatorProgression"
        OperatorProgression: Literal[
            "OperatorEXP", "Promotions", "T-Creds", "SkillUp"
        ] = "OperatorEXP"
        WeaponProgression: Literal["WeaponEXP", "WeaponTune"] = "WeaponEXP"
        CrisisDrills: Literal[
            "AdvancedProgression1",
            "AdvancedProgression2",
            "AdvancedProgression3",
            "AdvancedProgression4",
            "AdvancedProgression5",
        ] = "AdvancedProgression1"
        RewardsSetOption: Literal["RewardsSetA", "RewardsSetB"] = "RewardsSetA"

    class DataModel(BaseModel):
        LastProxyDate: str = "2000-01-01"
        ProxyTimes: NonNegativeInt = Field(default=0, le=9999)
        LastProxyStatus: Literal["未知", "成功", "失败"] = "未知"
        LastSklandDate: str = "2000-01-01"
        IfPassCheck: bool = True

        @field_validator("LastProxyDate", "LastSklandDate", mode="before")
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
    Task: TaskModel = Field(default_factory=TaskModel)
    Data: DataModel = Field(default_factory=DataModel)
    Notify: NotifyModel = Field(default_factory=NotifyModel)

    def getTags(self) -> str:  # noqa: N802
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags: list[dict[str, str]] = []

        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

        tags.append(
            {
                "text": f"上次：{self.get('Data', 'LastProxyStatus')}",
                "color": "red"
                if self.get("Data", "LastProxyStatus") == "失败"
                else "green",
            }
        )

        if (
            datetime.strptime(self.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
            == datetime.now(tz=UTC4).date()
        ):
            tags.append(
                {
                    "text": f"日常：已代理{self.get('Data', 'ProxyTimes')}次",
                    "color": "green",
                }
            )
        else:
            tags.append({"text": "日常：未代理", "color": "orange"})

        if self.get("Info", "IfSkland"):
            if (
                datetime.strptime(self.get("Data", "LastSklandDate"), "%Y-%m-%d").date()
                == datetime.now(tz=UTC8).date()
            ):
                tags.append({"text": "森空岛：已签到", "color": "green"})
            else:
                tags.append({"text": "森空岛：未签到", "color": "orange"})
        else:
            tags.append({"text": "森空岛：禁用", "color": "red"})

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

        stage = self.get("Task", self.get("Task", "ProtocolSpaceTab"))
        stage_ab = (
            f" - {self.get('Task', 'RewardsSetOption')[-1]}"
            if stage in MAAEND_STAGE_WITH_AB
            else ""
        )
        tags.append({"text": MAAEND_STAGE_BOOK[stage] + stage_ab, "color": "blue"})

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
@sub_configs(UserData=[MaaEndUserConfig])
class MaaEndConfig(PydanticConfigBase):
    """MaaEnd配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新 MaaEnd 脚本"
        Path: str = str(Path.cwd())

    class RunModel(BaseModel):
        RunTimeLimit: PositiveInt = Field(default=10, le=9999)
        ProxyTimesLimit: NonNegativeInt = Field(default=0, le=9999)
        RunTimesLimit: PositiveInt = Field(default=3, le=9999)

    class GameModel(BaseModel):
        ControllerType: Literal[
            "Win32-Window", "Win32-Front", "Win32-Window-Background", "ADB"
        ] = "Win32-Window"
        Path: str = str(Path.cwd())
        Arguments: str = ""
        WaitTime: NonNegativeInt = Field(default=0, le=9999)
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
        CloseOnFinish: bool = True

    Info: InfoModel = Field(default_factory=InfoModel)
    Run: RunModel = Field(default_factory=RunModel)
    Game: GameModel = Field(default_factory=GameModel)


__all__ = ["MaaEndUserConfig", "MaaEndConfig"]
