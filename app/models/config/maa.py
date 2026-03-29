import uuid
import json
import calendar
from pathlib import Path
from datetime import datetime

from app.utils.constants import UTC4, UTC8, RESOURCE_STAGE_INFO, MAA_STAGE_KEY
from ..ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    RangeValidator,
    VirtualConfigValidator,
    FolderValidator,
    EncryptValidator,
    DateTimeValidator,
    JSONValidator,
    UserNameValidator,
)
from .common import Webhook


class MaaUserConfig(ConfigBase):
    """MAA用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 脚本模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        ## 关卡模式
        self.Info_StageMode = ConfigItem(
            "Info",
            "StageMode",
            "Fixed",
            MultipleUIDValidator("Fixed", self.related_config, "PlanConfig"),
        )
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "Official",
            OptionsValidator(
                ["Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"]
            ),
        )
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 剿灭模式
        self.Info_Annihilation = ConfigItem(
            "Info",
            "Annihilation",
            "Annihilation",
            OptionsValidator(
                [
                    "Close",
                    "Annihilation",
                    "Chernobog@Annihilation",
                    "LungmenOutskirts@Annihilation",
                    "LungmenDowntown@Annihilation",
                ]
            ),
        )
        ## 基建模式
        self.Info_InfrastMode = ConfigItem(
            "Info",
            "InfrastMode",
            "Normal",
            OptionsValidator(["Normal", "Rotation", "Custom"]),
        )
        ## 基建配置名称
        self.Info_InfrastName = ConfigItem(
            "Info", "InfrastName", "-", VirtualConfigValidator(self.getInfrastName)
        )
        ## 基建配置索引
        self.Info_InfrastIndex = ConfigItem(
            "Info", "InfrastIndex", "-", VirtualConfigValidator(self.getInfrastIndex)
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 理智药数量
        self.Info_MedicineNumb = ConfigItem(
            "Info", "MedicineNumb", 0, RangeValidator(0, 9999)
        )
        ## 连战次数
        self.Info_SeriesNumb = ConfigItem(
            "Info",
            "SeriesNumb",
            "0",
            OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
        )
        ## 关卡
        self.Info_Stage = ConfigItem("Info", "Stage", "-")
        ## 关卡 1
        self.Info_Stage_1 = ConfigItem("Info", "Stage_1", "-")
        ## 关卡 2
        self.Info_Stage_2 = ConfigItem("Info", "Stage_2", "-")
        ## 关卡 3
        self.Info_Stage_3 = ConfigItem("Info", "Stage_3", "-")
        ## 备用关卡
        self.Info_Stage_Remain = ConfigItem("Info", "Stage_Remain", "-")
        ## 是否启用森空岛签到
        self.Info_IfSkland = ConfigItem("Info", "IfSkland", False, BoolValidator())
        ## 森空岛 Token
        self.Info_SklandToken = ConfigItem(
            "Info", "SklandToken", "", EncryptValidator()
        )
        ## 用户标签信息（虚拟字段，供前端显示）
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 上次森空岛签到日期
        self.Data_LastSklandDate = ConfigItem(
            "Data", "LastSklandDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 是否通过检查
        self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())
        ## 自定义基建配置
        self.Data_CustomInfrast = ConfigItem(
            "Data", "CustomInfrast", "{ }", JSONValidator()
        )
        ## 基建配置索引数据
        self.Data_InfrastIndex = ConfigItem(
            "Data", "InfrastIndex", "0", legacy_group="Info"
        )

        ## Task ------------------------------------------------------------
        ## 是否自动唤醒
        self.Task_IfStartUp = ConfigItem("Task", "IfStartUp", True, BoolValidator())
        ## 是否理智作战
        self.Task_IfFight = ConfigItem("Task", "IfFight", True, BoolValidator())
        ## 是否基建换班
        self.Task_IfInfrast = ConfigItem("Task", "IfInfrast", True, BoolValidator())
        ## 是否公开招募
        self.Task_IfRecruit = ConfigItem("Task", "IfRecruit", True, BoolValidator())
        ## 是否信用收支
        self.Task_IfMall = ConfigItem("Task", "IfMall", True, BoolValidator())
        ## 是否领取奖励
        self.Task_IfAward = ConfigItem("Task", "IfAward", True, BoolValidator())
        ## 是否自动肉鸽
        self.Task_IfRoguelike = ConfigItem(
            "Task", "IfRoguelike", False, BoolValidator()
        )
        ## 是否生息演算
        self.Task_IfReclamation = ConfigItem(
            "Task", "IfReclamation", False, BoolValidator()
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送六星通知
        self.Notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
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

    def getInfrastName(self) -> str:
        if self.get("Info", "InfrastMode") != "Custom":
            return "未使用自定义基建模式"

        infrast_data = json.loads(self.get("Data", "CustomInfrast"))
        if (
            infrast_data.get("title", "文件标题") != "文件标题"
            and infrast_data.get("description", "文件描述") != "文件描述"
        ):
            return f"{infrast_data['title']} - {infrast_data['description']}"
        elif infrast_data.get("title", "文件标题") != "文件标题":
            return str(infrast_data["title"])
        elif infrast_data.get("id", None):
            return str(infrast_data["id"])
        else:
            return "未命名自定义基建"

    def getInfrastIndex(self) -> str:
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

        else:
            return self.get("Data", "InfrastIndex") or "0"

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 人工排查状态标签
        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

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

        # 基建模式标签
        infrast_mode = self.get("Info", "InfrastMode")
        if self.get("Task", "IfInfrast"):
            if infrast_mode == "Normal":
                infrast_text = "基建：常规"
            elif infrast_mode == "Rotation":
                infrast_text = "基建：轮换"
            elif infrast_mode == "Custom":
                infrast_text = f"基建：{self.getInfrastName() if len(self.getInfrastName()) < 10 else self.getInfrastName()[:10] + '...'}"
            else:
                infrast_text = "基建：开启"
            tags.append({"text": infrast_text, "color": "purple"})
        else:
            tags.append({"text": "基建：关闭", "color": "red"})

        # 关卡信息标签
        plan_data = {
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
                        plan.get_current_info(stage_key).getValue()
                    )
                    for stage_key in MAA_STAGE_KEY[2:]
                }
                tag_color = "green"
        # 主关卡
        tags.append({"text": f"主关卡：{plan_data['Stage']}", "color": tag_color})
        # 备选关卡（合并显示）
        backup_stages = [
            plan_data[f"Stage_{i}"]
            for i in range(1, 4)
            if plan_data[f"Stage_{i}"] != "禁用"
        ]
        if backup_stages:
            tags.append(
                {"text": f"备选：{', '.join(backup_stages)}", "color": tag_color}
            )
        # 剩余关卡
        if plan_data["Stage_Remain"] != "禁用":
            tags.append(
                {"text": f"剩余：{plan_data['Stage_Remain']}", "color": tag_color}
            )

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

    @staticmethod
    def get_stage_zh(stage: str) -> str:
        for stage_info in RESOURCE_STAGE_INFO:
            if stage_info.get("value") == stage:
                return (
                    stage_info.get("text", stage)
                    .replace("经验-6/5", "经验")
                    .replace("龙门币-6/5", "龙门币")
                    .replace("红票-5", "红票")
                    .replace("技能-5", "技能")
                    .replace("碳-5", "碳")
                )
        else:
            return stage


class MaaConfig(ConfigBase):
    """MAA配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## MAA 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 脚本")
        ## MAA 路径
        self.Info_Path = ConfigItem("Info", "Path", str(Path.cwd()), FolderValidator())

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Run -------------------------------------------------------------
        ## 任务切换方式
        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitEmulator",
            OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
        )
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 剿灭时间限制（分钟）
        self.Run_AnnihilationTimeLimit = ConfigItem(
            "Run", "AnnihilationTimeLimit", 40, RangeValidator(1, 9999)
        )
        ## 日常时间限制（分钟）
        self.Run_RoutineTimeLimit = ConfigItem(
            "Run", "RoutineTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 剿灭避免无代理卡浪费理智
        self.Run_AnnihilationAvoidWaste = ConfigItem(
            "Run", "AnnihilationAvoidWaste", False, BoolValidator()
        )

        self.UserData = MultipleConfig([MaaUserConfig])

        super().__init__()


class MaaPlanConfig(ConfigBase):
    """MAA计划表配置"""

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 计划表名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 计划表")
        ## 计划表模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "ALL", OptionsValidator(["ALL", "Weekly"])
        )

        self.config_item_dict: dict[str, dict[str, ConfigItem]] = {}

        for group in ["ALL", *calendar.day_name]:
            self.config_item_dict[group] = {}

            ## 理智药数量
            self.config_item_dict[group]["MedicineNumb"] = ConfigItem(
                group, "MedicineNumb", 0, RangeValidator(0, 9999)
            )
            ## 连战次数
            self.config_item_dict[group]["SeriesNumb"] = ConfigItem(
                group,
                "SeriesNumb",
                "0",
                OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
            )

            ## 理智关卡
            for name in MAA_STAGE_KEY[2:]:
                # Stage、Stage_1、Stage_2、Stage_3、Stage_Remain
                self.config_item_dict[group][name] = ConfigItem(group, name, "-")

            for name in MAA_STAGE_KEY:
                setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

        super().__init__()

    def get_current_info(self, name: str) -> ConfigItem:
        """获取当前的计划表配置项"""

        if self.get("Info", "Mode") == "ALL":
            return self.config_item_dict["ALL"][name]

        elif self.get("Info", "Mode") == "Weekly":
            today = datetime.now(tz=UTC4).strftime("%A")

            if today in self.config_item_dict:
                return self.config_item_dict[today][name]
            else:
                return self.config_item_dict["ALL"][name]

        else:
            raise ValueError("非法的计划表模式")


__all__ = ["MaaPlanConfig", "MaaUserConfig", "MaaConfig"]
