import uuid
import json
import calendar
from datetime import datetime
from typing import Callable

from app.utils.constants import UTC8, MATERIALS_MAP, RESOURCE_STAGE_INFO
from ..ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    BoolValidator,
    OptionsValidator,
    VirtualConfigValidator,
    EncryptValidator,
    UUIDValidator,
    DateTimeValidator,
    JSONValidator,
    URLValidator,
    KeyValidator,
)
from ..schema import TagItem
from .common import EmulatorConfig, QueueConfig, QueueItem, Webhook
from .general import GeneralConfig
from .maa import MaaConfig, MaaPlanConfig, MaaUserConfig
from .maaend import MaaEndConfig
from .src import SrcConfig


class ToolsConfig(ConfigBase):
    """工具配置"""

    def __init__(self) -> None:
        self.ArknightsPC_Enabled = ConfigItem(
            "ArknightsPC", "Enabled", False, BoolValidator()
        )
        self.ArknightsPC_PauseKey = ConfigItem(
            "ArknightsPC", "PauseKey", "f10", KeyValidator("f10")
        )
        self.ArknightsPC_SelectDeployedKey = ConfigItem(
            "ArknightsPC", "SelectDeployedKey", "w", KeyValidator("w")
        )
        self.ArknightsPC_UseSkillKey = ConfigItem(
            "ArknightsPC", "UseSkillKey", "r", KeyValidator("r")
        )
        self.ArknightsPC_RetreatKey = ConfigItem(
            "ArknightsPC", "RetreatKey", "t", KeyValidator("t")
        )
        self.ArknightsPC_NextFrameKey = ConfigItem(
            "ArknightsPC", "NextFrameKey", "f", KeyValidator("f")
        )
        self.ArknightsPC_AnotherQuitKey = ConfigItem(
            "ArknightsPC", "AnotherQuitKey", "space", KeyValidator("space")
        )
        self.ArknightsPC_Status = ConfigItem(
            "ArknightsPC",
            "Status",
            "-",
            VirtualConfigValidator(self.arknights_pc_status),
        )

        self.arknights_pc_running = False
        self.arknights_pc_get_connected: Callable[[], bool] = lambda: False

        super().__init__()

    @property
    def arknights_pc_connected(self) -> bool:
        return self.arknights_pc_get_connected()

    def arknights_pc_status(self) -> str:
        if not self.get("ArknightsPC", "Enabled"):
            return TagItem(text="未启用", color="gray").model_dump_json()
        else:
            if self.arknights_pc_running:
                if self.arknights_pc_connected:
                    return TagItem(text="运行中", color="green").model_dump_json()
                else:
                    return TagItem(text="未连接", color="red").model_dump_json()
            else:
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


class GlobalConfig(ConfigBase):
    """全局配置"""

    def __init__(self):
        ## Function ---------------------------------------------------------
        ## 历史记录保留时间（天）
        self.Function_HistoryRetentionTime = ConfigItem(
            "Function",
            "HistoryRetentionTime",
            0,
            OptionsValidator([7, 15, 30, 60, 90, 180, 365, 0]),
        )
        ## 是否允许睡眠
        self.Function_IfAllowSleep = ConfigItem(
            "Function", "IfAllowSleep", False, BoolValidator()
        )
        ## 是否启用静默模式
        self.Function_IfSilence = ConfigItem(
            "Function", "IfSilence", False, BoolValidator()
        )
        ## 是否同意 Bilibili 协议
        self.Function_IfAgreeBilibili = ConfigItem(
            "Function", "IfAgreeBilibili", False, BoolValidator()
        )
        ## 是否屏蔽模拟器广告
        self.Function_IfBlockAd = ConfigItem(
            "Function", "IfBlockAd", False, BoolValidator()
        )

        ## Voice ------------------------------------------------------------
        ## 是否启用语音
        self.Voice_Enabled = ConfigItem("Voice", "Enabled", False, BoolValidator())
        ## 语音类型
        self.Voice_Type = ConfigItem(
            "Voice", "Type", "simple", OptionsValidator(["simple", "noisy"])
        )

        ## Start ------------------------------------------------------------
        ## 是否自动启动
        self.Start_IfSelfStart = ConfigItem(
            "Start", "IfSelfStart", False, BoolValidator()
        )
        ## 是否启动时直接最小化
        self.Start_IfMinimizeDirectly = ConfigItem(
            "Start", "IfMinimizeDirectly", False, BoolValidator()
        )

        ## UI ---------------------------------------------------------------
        ## 是否显示托盘图标
        self.UI_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
        ## 是否关闭到托盘
        self.UI_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())

        ## Notify -----------------------------------------------------------
        ## 任务结果推送时间
        self.Notify_SendTaskResultTime = ConfigItem(
            "Notify",
            "SendTaskResultTime",
            "不推送",
            OptionsValidator(["不推送", "任何时刻", "仅失败时"]),
        )
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送六星通知
        self.Notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
        )
        ## 是否推送系统通知
        self.Notify_IfPushPlyer = ConfigItem(
            "Notify", "IfPushPlyer", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 是否发送Koishi通知
        self.Notify_IfKoishiSupport = ConfigItem(
            "Notify", "IfKoishiSupport", False, BoolValidator()
        )
        ## Koishi WebSocket 服务器地址
        self.Notify_KoishiServerAddress = ConfigItem(
            "Notify",
            "KoishiServerAddress",
            "ws://localhost:5140/AUTO_MAS",
            URLValidator(),
        )
        ## Koishi Token
        self.Notify_KoishiToken = ConfigItem("Notify", "KoishiToken", "")
        ## SMTP 服务器地址
        self.Notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
        ## 邮箱授权码
        self.Notify_AuthorizationCode = ConfigItem(
            "Notify", "AuthorizationCode", "", EncryptValidator()
        )
        ## 发件地址
        self.Notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        ## Update -----------------------------------------------------------
        ## 是否自动更新
        self.Update_IfAutoUpdate = ConfigItem(
            "Update", "IfAutoUpdate", False, BoolValidator()
        )
        ## 更新源
        self.Update_Source = ConfigItem(
            "Update",
            "Source",
            "GitHub",
            OptionsValidator(["GitHub", "MirrorChyan", "AutoSite"]),
        )
        ## 更新频道
        self.Update_Channel = ConfigItem(
            "Update", "Channel", "stable", OptionsValidator(["stable", "beta"])
        )
        ## 代理地址
        self.Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
        ## 镜像站 CDK
        self.Update_MirrorChyanCDK = ConfigItem(
            "Update", "MirrorChyanCDK", "", EncryptValidator()
        )

        ## Data -------------------------------------------------------------
        ## 唯一标识符
        self.Data_UID = ConfigItem("Data", "UID", str(uuid.uuid4()), UUIDValidator())
        ## 上次统计上传时间
        self.Data_LastStatisticsUpload = ConfigItem(
            "Data",
            "LastStatisticsUpload",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 上次关卡更新时间
        self.Data_LastStageUpdated = ConfigItem(
            "Data",
            "LastStageUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 关卡数据的版本标识符
        self.Data_StageETag = ConfigItem("Data", "StageETag", "")
        ## 关卡信息数据
        self.Data_StageData = ConfigItem(
            "Data", "StageData", "{ }", JSONValidator(), legacy_name="Stage"
        )
        ## 关卡信息
        self.Data_Stage = ConfigItem(
            "Data", "Stage", "-", VirtualConfigValidator(self.getStage)
        )
        ## 上次公告更新时间
        self.Data_LastNoticeUpdated = ConfigItem(
            "Data",
            "LastNoticeUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 公告的版本标识符
        self.Data_NoticeETag = ConfigItem("Data", "NoticeETag", "")
        ## 是否显示公告
        self.Data_IfShowNotice = ConfigItem(
            "Data", "IfShowNotice", True, BoolValidator()
        )
        ## 公告内容
        self.Data_Notice = ConfigItem("Data", "Notice", "{ }", JSONValidator())
        ## 上次 Web 配置更新时间
        self.Data_LastWebConfigUpdated = ConfigItem(
            "Data",
            "LastWebConfigUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## Web 配置
        self.Data_WebConfig = ConfigItem(
            "Data", "WebConfig", "[ ]", JSONValidator(list)
        )
        super().__init__()

        ## 模拟器配置列表
        self.EmulatorConfig = MultipleConfig([EmulatorConfig])
        ## 计划表配置列表
        self.PlanConfig = MultipleConfig([MaaPlanConfig])
        ## 脚本配置列表
        self.ScriptConfig = MultipleConfig(
            [MaaConfig, MaaEndConfig, SrcConfig, GeneralConfig]
        )
        ## 队列配置列表
        self.QueueConfig = MultipleConfig([QueueConfig])
        ## 工具箱配置
        self.ToolsConfig = ToolsConfig()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaEndConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        SrcConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        GeneralConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaUserConfig.related_config["PlanConfig"] = self.PlanConfig
        QueueItem.related_config["ScriptConfig"] = self.ScriptConfig

    def getStage(self) -> str:
        """获取关卡信息"""

        try:
            raw_stage_data = json.loads(self.get("Data", "StageData"))

            activity_stage_drop_info = []
            activity_stage_combox = []

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
        except Exception:
            return "{ }"

        stage_data = {"Info": activity_stage_drop_info}

        for day in range(0, 8):
            res_stage = []

            for stage in RESOURCE_STAGE_INFO:
                if day in stage["days"] or day == 0:
                    res_stage.append({"label": stage["text"], "value": stage["value"]})

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
