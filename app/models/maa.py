from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import AliasChoices, AliasPath, BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.shortcuts import config, ref, sub_configs, virtual
from app.core.config.types import (
    DayCount,
    EncryptedString,
    JsonDictString,
    NonNegativeInt,
    PositiveInt,
)
from app.utils.constants import MAA_STAGE_KEY, RESOURCE_STAGE_INFO, UTC4, UTC8
from .common import Webhook
from .tag_helpers import notes_tag, proxy_date_tag, remained_day_tag


@config
@sub_configs(Notify_CustomWebhooks=[Webhook])
class MaaUserConfig(PydanticConfigBase):
    """MAA用户配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新用户"
        Id: str = ""
        Password: EncryptedString = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        StageMode: Annotated[
            str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                on_delete="set_default",
            ),
        ] = "Fixed"
        Server: Literal[
            "Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"
        ] = "Official"
        Status: bool = True
        RemainedDay: DayCount = -1
        Annihilation: Literal[
            "Close",
            "Annihilation",
            "Chernobog@Annihilation",
            "LungmenOutskirts@Annihilation",
            "LungmenDowntown@Annihilation",
        ] = "Annihilation"
        InfrastMode: Literal["Normal", "Rotation", "Custom"] = "Normal"
        InfrastName: Annotated[
            str,
            virtual("getInfrastName"),
        ] = "-"
        InfrastIndex: Annotated[
            str,
            virtual("getInfrastIndex"),
        ] = "-"
        Notes: str = "无"
        MedicineNumb: NonNegativeInt = 0
        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = "0"
        Stage: str = "-"
        Stage_1: str = "-"
        Stage_2: str = "-"
        Stage_3: str = "-"
        Stage_Remain: str = "-"
        IfSkland: bool = False
        SklandToken: EncryptedString = ""
        Tag: Annotated[
            str,
            virtual("getTags"),
        ] = "[ ]"

    class DataModel(BaseModel):
        LastProxyDate: str = "2000-01-01"
        LastSklandDate: str = "2000-01-01"
        ProxyTimes: NonNegativeInt = 0
        IfPassCheck: bool = True
        CustomInfrast: JsonDictString = "{ }"
        InfrastIndex: str = Field(
            default="0",
            validation_alias=AliasChoices(
                "InfrastIndex", AliasPath("Info", "InfrastIndex")
            ),
        )

        @field_validator("LastProxyDate", "LastSklandDate", mode="before")
        @classmethod
        def _normalize_ymd(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            try:
                datetime.strptime(text, "%Y-%m-%d")
                return text
            except ValueError:
                return "2000-01-01"

    class TaskModel(BaseModel):
        IfStartUp: bool = True
        IfFight: bool = True
        IfInfrast: bool = True
        IfRecruit: bool = True
        IfMall: bool = True
        IfAward: bool = True
        IfRoguelike: bool = False
        IfReclamation: bool = False

    class NotifyModel(BaseModel):
        Enabled: bool = False
        IfSendStatistic: bool = False
        IfSendSixStar: bool = False
        IfSendMail: bool = False
        ToAddress: str = ""
        IfServerChan: bool = False
        ServerChanKey: str = ""

    Info: InfoModel = Field(default_factory=InfoModel)
    Data: DataModel = Field(default_factory=DataModel)
    Task: TaskModel = Field(default_factory=TaskModel)
    Notify: NotifyModel = Field(default_factory=NotifyModel)

    def getInfrastName(self) -> str:  # noqa: N802
        if self.get("Info", "InfrastMode") != "Custom":
            return "未使用自定义基建模式"

        infrast_data = json.loads(self.get("Data", "CustomInfrast"))
        if (
            infrast_data.get("title", "文件标题") != "文件标题"
            and infrast_data.get("description", "文件描述") != "文件描述"
        ):
            return f"{infrast_data['title']} - {infrast_data['description']}"
        if infrast_data.get("title", "文件标题") != "文件标题":
            return str(infrast_data["title"])
        if infrast_data.get("id", None):
            return str(infrast_data["id"])
        return "未命名自定义基建"

    def getInfrastIndex(self) -> str:  # noqa: N802
        if self.get("Info", "InfrastMode") != "Custom":
            return "-1"

        infrast_data = json.loads(self.get("Data", "CustomInfrast"))

        if len(infrast_data.get("plans", [])) == 0:
            return "-1"

        for i, plan in enumerate(infrast_data.get("plans", [])):
            for t in plan.get("period", []):
                if (
                    datetime.strptime(t[0], "%H:%M").time()
                    <= datetime.now().time()
                    <= datetime.strptime(t[1], "%H:%M").time()
                ):
                    return str(i)

        return self.get("Data", "InfrastIndex") or "0"

    def getTags(self) -> str:  # noqa: N802
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags: list[dict[str, str]] = []

        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

        tags.append(
            proxy_date_tag(
                self.get("Data", "LastProxyDate"),
                self.get("Data", "ProxyTimes"),
                UTC4,
            )
        )

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

        tags.append(remained_day_tag(self.get("Info", "RemainedDay")))

        infrast_mode = self.get("Info", "InfrastMode")
        if self.get("Task", "IfInfrast"):
            if infrast_mode == "Normal":
                infrast_text = "基建：常规"
            elif infrast_mode == "Rotation":
                infrast_text = "基建：轮换"
            elif infrast_mode == "Custom":
                name = self.getInfrastName()
                infrast_text = f"基建：{name if len(name) < 10 else name[:10] + '...'}"
            else:
                infrast_text = "基建：开启"
            tags.append({"text": infrast_text, "color": "purple"})
        else:
            tags.append({"text": "基建：关闭", "color": "red"})

        plan_data: dict[str, str] = {
            stage_key: self.get_stage_zh(self.get("Info", stage_key))
            for stage_key in MAA_STAGE_KEY[2:]
        }
        tag_color = "blue"
        if self.get("Info", "StageMode") != "Fixed":
            plan = self.related_config["PlanConfig"][
                uuid.UUID(self.get("Info", "StageMode"))
            ]
            if isinstance(plan, MaaPlanConfig):
                plan_data = {
                    stage_key: self.get_stage_zh(
                        plan.get_current_info(stage_key)
                    )
                    for stage_key in MAA_STAGE_KEY[2:]
                }
                tag_color = "green"

        tags.append({"text": f"主关卡：{plan_data['Stage']}", "color": tag_color})
        backup_stages = [
            plan_data[f"Stage_{i}"]
            for i in range(1, 4)
            if plan_data[f"Stage_{i}"] != "禁用"
        ]
        if backup_stages:
            tags.append(
                {"text": f"备选：{', '.join(backup_stages)}", "color": tag_color}
            )
        if plan_data["Stage_Remain"] != "禁用":
            tags.append(
                {"text": f"剩余：{plan_data['Stage_Remain']}", "color": tag_color}
            )

        tags.append(notes_tag(self.get("Info", "Notes")))

        return json.dumps(tags, ensure_ascii=False)

    @staticmethod
    def get_stage_zh(stage: str) -> str:
        for stage_info in RESOURCE_STAGE_INFO:
            if stage_info.get("value") == stage:
                text_value = stage_info.get("text", stage)
                text = text_value if isinstance(text_value, str) else stage
                return (
                    text.replace("经验-6/5", "经验")
                    .replace("龙门币-6/5", "龙门币")
                    .replace("红票-5", "红票")
                    .replace("技能-5", "技能")
                    .replace("碳-5", "碳")
                )
        return stage


@config
@sub_configs(UserData=[MaaUserConfig])
class MaaConfig(PydanticConfigBase):
    """MAA配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新 MAA 脚本"
        Path: str = str(Path.cwd())

    class EmulatorModel(BaseModel):
        Id: Annotated[
            str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                on_delete="set_default",
            ),
        ] = "-"
        Index: str = "-"

    class RunModel(BaseModel):
        TaskTransitionMethod: Literal["NoAction", "ExitGame", "ExitEmulator"] = (
            "ExitEmulator"
        )
        ProxyTimesLimit: NonNegativeInt = Field(default=0, le=9999)
        RunTimesLimit: PositiveInt = Field(default=3, le=9999)
        AnnihilationTimeLimit: PositiveInt = Field(default=40, le=9999)
        RoutineTimeLimit: PositiveInt = Field(default=10, le=9999)
        AnnihilationAvoidWaste: bool = False

    Info: InfoModel = Field(default_factory=InfoModel)
    Emulator: EmulatorModel = Field(default_factory=EmulatorModel)
    Run: RunModel = Field(default_factory=RunModel)


class MaaPlanConfig(PydanticConfigBase):
    """MAA计划表配置"""

    class InfoModel(BaseModel):
        Name: str = "新 MAA 计划表"
        Mode: Literal["ALL", "Weekly"] = "ALL"

    class DayPlanModel(BaseModel):
        MedicineNumb: NonNegativeInt = Field(default=0, le=9999)
        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = "0"
        Stage: str = "-"
        Stage_1: str = "-"
        Stage_2: str = "-"
        Stage_3: str = "-"
        Stage_Remain: str = "-"

    Info: InfoModel = Field(default_factory=InfoModel)
    ALL: DayPlanModel = Field(default_factory=DayPlanModel)
    Monday: DayPlanModel = Field(default_factory=DayPlanModel)
    Tuesday: DayPlanModel = Field(default_factory=DayPlanModel)
    Wednesday: DayPlanModel = Field(default_factory=DayPlanModel)
    Thursday: DayPlanModel = Field(default_factory=DayPlanModel)
    Friday: DayPlanModel = Field(default_factory=DayPlanModel)
    Saturday: DayPlanModel = Field(default_factory=DayPlanModel)
    Sunday: DayPlanModel = Field(default_factory=DayPlanModel)

    def get_current_info(self, name: str) -> Any:
        """获取当前的计划表配置项"""

        if self.get("Info", "Mode") == "ALL":
            return getattr(self.ALL, name, "-")

        if self.get("Info", "Mode") == "Weekly":
            today = datetime.now(tz=UTC4).strftime("%A")
            plan = getattr(self, today, self.ALL)
            return getattr(plan, name, "-")

        raise ValueError("非法的计划表模式")


__all__ = ["MaaPlanConfig", "MaaUserConfig", "MaaConfig"]
