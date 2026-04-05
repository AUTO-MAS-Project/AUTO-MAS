from __future__ import annotations

import calendar
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Callable, Literal

from pydantic import AliasChoices, AliasPath, BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.fields import VirtualField
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.types import (
    EncryptedString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    UrlString,
    YmdHmsString,
)
from app.utils.constants import MATERIALS_MAP, RESOURCE_STAGE_INFO, UTC8
from app.models.shared import TagItem
from .common import EmulatorConfig, QueueConfig, QueueItem, Webhook
from .general import GeneralConfig
from .maa import MaaConfig, MaaPlanConfig, MaaUserConfig
from .maaend import MaaEndConfig
from .src import SrcConfig


class ToolsConfig(PydanticConfigBase):
    """工具配置"""

    class ArknightsPCModel(BaseModel):
        Enabled: bool = False
        PauseKey: KeyboardKeyString = "f10"
        SelectDeployedKey: KeyboardKeyString = "w"
        UseSkillKey: KeyboardKeyString = "r"
        RetreatKey: KeyboardKeyString = "t"
        NextFrameKey: KeyboardKeyString = "f"
        AnotherQuitKey: KeyboardKeyString = "space"
        Status: Annotated[
            str,
            VirtualField(
                "arknights_pc_status",
                depends_on=(("ArknightsPC", "Enabled"),),
            ),
        ] = "-"

    ArknightsPC: ArknightsPCModel = Field(default_factory=ArknightsPCModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.arknights_pc_running = False
        self.arknights_pc_get_connected: Callable[[], bool] = lambda: False

    @property
    def arknights_pc_connected(self) -> bool:
        return self.arknights_pc_get_connected()

    def arknights_pc_status(self) -> str:
        if not self.get("ArknightsPC", "Enabled"):
            return TagItem(text="未启用", color="gray").model_dump_json()

        if self.arknights_pc_running:
            if self.arknights_pc_connected:
                return TagItem(text="运行中", color="green").model_dump_json()
            return TagItem(text="未连接", color="red").model_dump_json()

        return TagItem(text="已暂停", color="yellow").model_dump_json()

    @property
    def arknights_pc_keys(self) -> list[str]:
        """获取明日方舟 PC 按键配置"""

        return [
            self.get("ArknightsPC", _)
            for _ in (
                "SelectDeployedKey",
                "UseSkillKey",
                "RetreatKey",
                "NextFrameKey",
                "AnotherQuitKey",
            )
        ]


class GlobalConfig(PydanticConfigBase):
    """全局配置"""

    class FunctionModel(BaseModel):
        HistoryRetentionTime: Literal[7, 15, 30, 60, 90, 180, 365, 0] = 0
        IfAllowSleep: bool = False
        IfSilence: bool = False
        IfAgreeBilibili: bool = False
        IfBlockAd: bool = False

    class VoiceModel(BaseModel):
        Enabled: bool = False
        Type: Literal["simple", "noisy"] = "simple"

    class StartModel(BaseModel):
        IfSelfStart: bool = False
        IfMinimizeDirectly: bool = False

    class UIModel(BaseModel):
        IfShowTray: bool = False
        IfToTray: bool = False

    class NotifyModel(BaseModel):
        SendTaskResultTime: Literal["不推送", "任何时刻", "仅失败时"] = "不推送"
        IfSendStatistic: bool = False
        IfSendSixStar: bool = False
        IfPushPlyer: bool = False
        IfSendMail: bool = False
        IfKoishiSupport: bool = False
        KoishiServerAddress: UrlString = "ws://localhost:5140/AUTO_MAS"
        KoishiToken: str = ""
        SMTPServerAddress: str = ""
        AuthorizationCode: EncryptedString = ""
        FromAddress: str = ""
        ToAddress: str = ""
        IfServerChan: bool = False
        ServerChanKey: str = ""

    class UpdateModel(BaseModel):
        IfAutoUpdate: bool = False
        Source: Literal["GitHub", "MirrorChyan", "AutoSite"] = "GitHub"
        Channel: Literal["stable", "beta"] = "stable"
        ProxyAddress: str = ""
        MirrorChyanCDK: EncryptedString = ""

    class DataModel(BaseModel):
        UID: str = str(uuid.uuid4())
        LastStatisticsUpload: YmdHmsString = "2000-01-01 00:00:00"
        LastStageUpdated: YmdHmsString = "2000-01-01 00:00:00"
        StageETag: str = ""
        StageData: JsonDictString = Field(
            default="{ }",
            validation_alias=AliasChoices("StageData", AliasPath("Data", "Stage")),
        )
        LastNoticeUpdated: YmdHmsString = "2000-01-01 00:00:00"
        NoticeETag: str = ""
        IfShowNotice: bool = True
        Notice: JsonDictString = "{ }"
        LastWebConfigUpdated: YmdHmsString = "2000-01-01 00:00:00"
        WebConfig: JsonListString = "[ ]"
        Stage: Annotated[
            str,
            VirtualField("getStage", depends_on=(("Data", "StageData"),)),
        ] = "-"

        @field_validator("UID", mode="before")
        @classmethod
        def _normalize_uid(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            try:
                return str(uuid.UUID(text))
            except (TypeError, ValueError):
                return str(uuid.uuid4())

    Function: FunctionModel = Field(default_factory=FunctionModel)
    Voice: VoiceModel = Field(default_factory=VoiceModel)
    Start: StartModel = Field(default_factory=StartModel)
    UI: UIModel = Field(default_factory=UIModel)
    Notify: NotifyModel = Field(default_factory=NotifyModel)
    Update: UpdateModel = Field(default_factory=UpdateModel)
    Data: DataModel = Field(default_factory=DataModel)

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.Notify_CustomWebhooks: MultipleConfig[Webhook] = MultipleConfig([Webhook])
        self.EmulatorConfig: MultipleConfig[EmulatorConfig] = MultipleConfig(
            [EmulatorConfig]
        )
        self.PlanConfig: MultipleConfig[MaaPlanConfig] = MultipleConfig([MaaPlanConfig])
        self.ScriptConfig: MultipleConfig[
            MaaConfig | MaaEndConfig | SrcConfig | GeneralConfig
        ] = MultipleConfig([MaaConfig, MaaEndConfig, SrcConfig, GeneralConfig])
        self.QueueConfig: MultipleConfig[QueueConfig] = MultipleConfig([QueueConfig])
        self.ToolsConfig = ToolsConfig()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaEndConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        SrcConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        GeneralConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaUserConfig.related_config["PlanConfig"] = self.PlanConfig
        QueueItem.related_config["ScriptConfig"] = self.ScriptConfig

    def getStage(self) -> str:  # noqa: N802
        """获取关卡信息"""

        try:
            raw_stage_data = json.loads(self.get("Data", "StageData"))

            activity_stage_drop_info: list[dict[str, Any]] = []
            activity_stage_combox: list[dict[str, str]] = []

            for side_story in raw_stage_data.values():
                if (
                    datetime.strptime(
                        side_story["Activity"]["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=UTC8)
                    < datetime.now(tz=UTC8)
                    < datetime.strptime(
                        side_story["Activity"]["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                    ).replace(tzinfo=UTC8)
                ):
                    for stage in side_story["Stages"]:
                        activity_stage_combox.append(
                            {"label": stage["Display"], "value": stage["Value"]}
                        )

                        if "SSReopen" not in stage["Display"]:
                            if stage["Drop"] in MATERIALS_MAP:
                                drop_id = stage["Drop"]
                            elif "玉" in stage["Drop"]:
                                drop_id = "30012"
                            else:
                                drop_id = "NotFound"

                            activity_stage_drop_info.append(
                                {
                                    "Display": stage["Display"],
                                    "Value": stage["Value"],
                                    "Drop": drop_id,
                                    "DropName": MATERIALS_MAP.get(
                                        stage["Drop"], stage["Drop"]
                                    ),
                                    "Activity": side_story["Activity"],
                                }
                            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return "{ }"

        stage_data: dict[str, Any] = {"Info": activity_stage_drop_info}

        for day in range(0, 8):
            res_stage: list[dict[str, str]] = []

            for stage in RESOURCE_STAGE_INFO:
                stage_days = stage.get("days")
                stage_text = stage.get("text")
                stage_value = stage.get("value")
                if (
                    isinstance(stage_days, list)
                    and isinstance(stage_text, str)
                    and isinstance(stage_value, str)
                    and (day in stage_days or day == 0)
                ):
                    res_stage.append({"label": stage_text, "value": stage_value})

            stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                res_stage[0:1] + activity_stage_combox + res_stage[1:]
            )

        return json.dumps(stage_data, ensure_ascii=False)


CLASS_BOOK = {
    "MAA": MaaConfig,
    "MaaPlan": MaaPlanConfig,
    "SRC": SrcConfig,
    "MaaEnd": MaaEndConfig,
    "General": GeneralConfig,
}
"""配置类映射表"""


__all__ = ["ToolsConfig", "GlobalConfig", "CLASS_BOOK"]
