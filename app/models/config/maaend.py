import json
from pathlib import Path
from datetime import datetime

from app.utils.constants import UTC4, UTC8, MAAEND_STAGE_BOOK, MAAEND_STAGE_WITH_AB
from ..ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    RangeValidator,
    VirtualConfigValidator,
    FileValidator,
    FolderValidator,
    EncryptValidator,
    DateTimeValidator,
    UserNameValidator,
    ArgumentValidator,
)
from .common import Webhook


class MaaEndUserConfig(ConfigBase):
    """MaaEnd用户配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 配置模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        ## 资源名称
        self.Info_Resource = ConfigItem(
            "Info", "Resource", "官服", OptionsValidator(["官服"])
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 是否启用森空岛签到
        self.Info_IfSkland = ConfigItem("Info", "IfSkland", False, BoolValidator())
        ## 森空岛 Token
        self.Info_SklandToken = ConfigItem(
            "Info", "SklandToken", "", EncryptValidator()
        )
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Task ------------------------------------------------------------
        ## 协议空间选项
        self.Task_ProtocolSpaceTab = ConfigItem(
            "Task",
            "ProtocolSpaceTab",
            "OperatorProgression",
            OptionsValidator(
                ["OperatorProgression", "WeaponProgression", "CrisisDrills"]
            ),
        )
        self.Task_OperatorProgression = ConfigItem(
            "Task",
            "OperatorProgression",
            "OperatorEXP",
            OptionsValidator(["OperatorEXP", "Promotions", "T-Creds", "SkillUp"]),
        )
        self.Task_WeaponProgression = ConfigItem(
            "Task",
            "WeaponProgression",
            "WeaponEXP",
            OptionsValidator(["WeaponEXP", "WeaponTune"]),
        )
        self.Task_CrisisDrills = ConfigItem(
            "Task",
            "CrisisDrills",
            "AdvancedProgression1",
            OptionsValidator(
                [
                    "AdvancedProgression1",
                    "AdvancedProgression2",
                    "AdvancedProgression3",
                    "AdvancedProgression4",
                    "AdvancedProgression5",
                ]
            ),
        )
        self.Task_RewardsSetOption = ConfigItem(
            "Task",
            "RewardsSetOption",
            "RewardsSetA",
            OptionsValidator(["RewardsSetA", "RewardsSetB"]),
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 上次代理状态
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )
        ## 上次森空岛签到日期
        self.Data_LastSklandDate = ConfigItem(
            "Data", "LastSklandDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 是否通过检查
        self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
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

        super().__init__()

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []
        # 人工排查状态标签
        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

        # 上次代理标签
        tags.append(
            {
                "text": f"上次：{self.get('Data', 'LastProxyStatus')}",
                "color": (
                    "red" if self.get("Data", "LastProxyStatus") == "失败" else "green"
                ),
            }
        )

        # 日常代理标签（使用东4区时间）
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

        # 森空岛签到标签（使用东8区时间）
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

        # 剩余天数标签
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
                "text": (
                    f"剩余天数：{remained_day}天"
                    if remained_day >= 0
                    else "剩余天数：无期限"
                ),
                "color": tag_color,
            }
        )

        # 关卡信息标签
        stage = self.get("Task", self.get("Task", "ProtocolSpaceTab"))
        stage_ab = (
            f" - {self.get('Task', 'RewardsSetOption')[-1]}"
            if stage in MAAEND_STAGE_WITH_AB
            else ""
        )
        tags.append({"text": MAAEND_STAGE_BOOK[stage] + stage_ab, "color": "blue"})

        # 备注标签
        notes = self.get("Info", "Notes")
        tags.append(
            {
                "text": (
                    f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."
                ),
                "color": "pink",
            }
        )

        return json.dumps(tags, ensure_ascii=False)


class MaaEndConfig(ConfigBase):
    """MaaEnd配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## MaaEnd 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MaaEnd 脚本")
        ## MaaEnd 路径
        self.Info_Path = ConfigItem("Info", "Path", str(Path.cwd()), FolderValidator())

        ## Run -------------------------------------------------------------
        ## 运行超时阈值
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 每日代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )

        ## Game ------------------------------------------------------------
        ## 控制器类型
        self.Game_ControllerType = ConfigItem(
            "Game",
            "ControllerType",
            "Win32-Window",
            OptionsValidator(
                [
                    "Win32-Window",
                    "Win32-Front",
                    "Win32-Window-Background",
                    "ADB",
                ]
            ),
        )
        ## 终末地游戏路径
        self.Game_Path = ConfigItem("Game", "Path", str(Path.cwd()), FileValidator())
        ## 终末地游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 等待时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 9999))
        ## 模拟器 ID
        self.Game_EmulatorId = ConfigItem(
            "Game",
            "EmulatorId",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Game_EmulatorIndex = ConfigItem("Game", "EmulatorIndex", "-")
        ## 结束后是否关闭游戏
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )

        self.UserData = MultipleConfig([MaaEndUserConfig])

        super().__init__()


__all__ = ["MaaEndUserConfig", "MaaEndConfig"]
