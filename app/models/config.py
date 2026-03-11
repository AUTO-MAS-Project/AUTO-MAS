#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import json
import calendar
from pathlib import Path
from datetime import datetime
from typing import Callable

from app.utils.constants import (
    UTC4,
    UTC8,
    MATERIALS_MAP,
    RESOURCE_STAGE_INFO,
    MAA_STAGE_KEY,
    STARRAIL_STAGE_BOOK,
)
from .ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    MultipleOptionsValidator,
    RangeValidator,
    VirtualConfigValidator,
    FileValidator,
    FolderValidator,
    EmulatorPathValidator,
    EncryptValidator,
    UUIDValidator,
    DateTimeValidator,
    JSONValidator,
    URLValidator,
    UserNameValidator,
    KeyValidator,
    ArgumentValidator,
    AdvancedArgumentValidator,
)
from .schema import TagItem


class EmulatorConfig(ConfigBase):
    """模拟器配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 模拟器名称
        self.Info_Name = ConfigItem("Info", "Name", "新模拟器")
        ## 模拟器类型
        self.Info_Type = ConfigItem(
            "Info",
            "Type",
            "general",
            OptionsValidator(
                [
                    "general",
                    "mumu",
                    "ldplayer",
                    # "nox",  # 以下都是骗你的, 根本没有写~~
                    # "memu",
                    # "blueStacks",
                ]
            ),
            legacy_group="Data",
        )
        ## 模拟器路径
        self.Info_Path = ConfigItem(
            "Info", "Path", "", EmulatorPathValidator(self.Info_Type)
        )
        ## 老板键快捷键配置
        self.Info_BossKey = ConfigItem(
            "Info", "BossKey", "[ ]", JSONValidator(list), legacy_group="Data"
        )
        ## 最大等待时间（秒）
        self.Info_MaxWaitTime = ConfigItem(
            "Info", "MaxWaitTime", 60, RangeValidator(1, 9999), legacy_group="Data"
        )

        super().__init__()


class Webhook(ConfigBase):
    """Webhook 配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## Webhook 名称
        self.Info_Name = ConfigItem("Info", "Name", "新自定义 Webhook 通知")
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())

        ## Data ------------------------------------------------------------
        ## Webhook URL 地址
        self.Data_Url = ConfigItem("Data", "Url", "", URLValidator())
        ## 消息模板
        self.Data_Template = ConfigItem("Data", "Template", "")
        ## 请求头
        self.Data_Headers = ConfigItem("Data", "Headers", "{ }", JSONValidator())
        ## 请求方法
        self.Data_Method = ConfigItem(
            "Data", "Method", "POST", OptionsValidator(["POST", "GET"])
        )

        super().__init__()


class QueueItem(ConfigBase):
    """队列项配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本 ID
        self.Info_ScriptId = ConfigItem(
            "Info",
            "ScriptId",
            "-",
            MultipleUIDValidator("-", self.related_config, "ScriptConfig"),
        )

        super().__init__()


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())
        ## 执行周期
        self.Info_Days = ConfigItem(
            "Info",
            "Days",
            list(calendar.day_name),
            MultipleOptionsValidator(list(calendar.day_name)),
        )
        ## 执行时间
        self.Info_Time = ConfigItem("Info", "Time", "00:00", DateTimeValidator("%H:%M"))

        super().__init__()


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 队列名称
        self.Info_Name = ConfigItem("Info", "Name", "新队列")
        ## 是否启用定时启动
        self.Info_TimeEnabled = ConfigItem(
            "Info", "TimeEnabled", False, BoolValidator()
        )
        ## 是否在启动时自动运行
        self.Info_StartUpEnabled = ConfigItem(
            "Info", "StartUpEnabled", False, BoolValidator()
        )
        ## 完成后操作
        self.Info_AfterAccomplish = ConfigItem(
            "Info",
            "AfterAccomplish",
            "NoAction",
            OptionsValidator(
                [
                    "NoAction",
                    "Shutdown",
                    "ShutdownForce",
                    "Reboot",
                    "Hibernate",
                    "Sleep",
                    "KillSelf",
                ]
            ),
        )

        ## Data ------------------------------------------------------------
        ## 上次定时启动时间
        self.Data_LastTimedStart = ConfigItem(
            "Data",
            "LastTimedStart",
            "2000-01-01 00:00",
            DateTimeValidator("%Y-%m-%d %H:%M"),
        )

        self.TimeSet = MultipleConfig([TimeSet])
        self.QueueItem = MultipleConfig([QueueItem])

        super().__init__()


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
                infrast_text = f"基建：{self.getInfrastName()}"
            else:
                infrast_text = "基建：开启"
            tags.append({"text": infrast_text, "color": "purple"})
        else:
            tags.append({"text": "基建：关闭", "color": "red"})

        # 关卡信息标签
        if self.get("Info", "StageMode") == "Fixed":
            plan_data = {
                stage_key: self.get_stage_zh(self.get("Info", stage_key))
                for stage_key in MAA_STAGE_KEY[2:]
            }
            tag_color = "blue"
        else:
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


class SrcUserConfig(ConfigBase):
    """SRC用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 脚本模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "CN-Official",
            OptionsValidator(
                [
                    "CN-Official",
                    "CN-Bilibili",
                    "VN-Official",
                    "OVERSEA-America",
                    "OVERSEA-Asia",
                    "OVERSEA-Europe",
                    "OVERSEA-TWHKMO",
                ]
            ),
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## 关卡配置----------------------------------------------------------
        ## 关卡通道
        self.Stage_Channel = ConfigItem(
            "Stage",
            "Channel",
            "Relic",
            OptionsValidator(["Relic", "Materials", "Ornament"]),
        )
        ## 遗器关卡
        self.Stage_Relic = ConfigItem(
            "Stage",
            "Relic",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Cavern_of_Corrosion_Path_of_Possession",
                    "Cavern_of_Corrosion_Path_of_Hidden_Salvation",
                    "Cavern_of_Corrosion_Path_of_Thundersurge",
                    "Cavern_of_Corrosion_Path_of_Aria",
                    "Cavern_of_Corrosion_Path_of_Uncertainty",
                    "Cavern_of_Corrosion_Path_of_Cavalier",
                    "Cavern_of_Corrosion_Path_of_Dreamdive"
                    "Cavern_of_Corrosion_Path_of_Darkness",
                    "Cavern_of_Corrosion_Path_of_Elixir_Seekers",
                    "Cavern_of_Corrosion_Path_of_Conflagration",
                    "Cavern_of_Corrosion_Path_of_Holy_Hymn",
                    "Cavern_of_Corrosion_Path_of_Providence",
                    "Cavern_of_Corrosion_Path_of_Drifting",
                    "Cavern_of_Corrosion_Path_of_Jabbing_Punch",
                    "Cavern_of_Corrosion_Path_of_Gelid_Wind",
                ]
            ),
        )
        ## 材料关卡
        self.Stage_Materials = ConfigItem(
            "Stage",
            "Materials",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Calyx_Golden_Memories_Planarcadia",
                    "Calyx_Golden_Aether_Planarcadia",
                    "Calyx_Golden_Treasures_Planarcadia",
                    "Calyx_Golden_Memories_Amphoreus",
                    "Calyx_Golden_Aether_Amphoreus",
                    "Calyx_Golden_Treasures_Amphoreus",
                    "Calyx_Golden_Memories_Penacony",
                    "Calyx_Golden_Aether_Penacony",
                    "Calyx_Golden_Treasures_Penacony",
                    "Calyx_Golden_Memories_The_Xianzhou_Luofu",
                    "Calyx_Golden_Aether_The_Xianzhou_Luofu",
                    "Calyx_Golden_Treasures_The_Xianzhou_Luofu",
                    "Calyx_Golden_Memories_Jarilo_VI",
                    "Calyx_Golden_Aether_Jarilo_VI",
                    "Calyx_Golden_Treasures_Jarilo_VI",
                    "Calyx_Crimson_Destruction_Herta_StorageZone",
                    "Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape",
                    "Calyx_Crimson_Preservation_Herta_SupplyZone",
                    "Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark",
                    "Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains",
                    "Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue",
                    "Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime",
                    "Calyx_Crimson_Abundance_Jarilo_BackwaterPass",
                    "Calyx_Crimson_Abundance_Luofu_FyxestrollGarden",
                    "Calyx_Crimson_Erudition_Jarilo_RivetTown",
                    "Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater",
                    "Calyx_Crimson_Harmony_Jarilo_RobotSettlement",
                    "Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape",
                    "Calyx_Crimson_Nihility_Jarilo_GreatMine",
                    "Calyx_Crimson_Nihility_Luofu_AlchemyCommission",
                    "Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos",
                    "Calyx_Crimson_Elation_Planarcadia_WorldEndTavern",
                    "Stagnant_Shadow_Quanta",
                    "Stagnant_Shadow_Gust",
                    "Stagnant_Shadow_Fulmination",
                    "Stagnant_Shadow_Blaze",
                    "Stagnant_Shadow_Spike",
                    "Stagnant_Shadow_Rime",
                    "Stagnant_Shadow_Mirage",
                    "Stagnant_Shadow_Icicle",
                    "Stagnant_Shadow_Doom",
                    "Stagnant_Shadow_Puppetry",
                    "Stagnant_Shadow_Abomination",
                    "Stagnant_Shadow_Scorch",
                    "Stagnant_Shadow_Celestial",
                    "Stagnant_Shadow_Perdition",
                    "Stagnant_Shadow_Nectar",
                    "Stagnant_Shadow_Roast",
                    "Stagnant_Shadow_Ire",
                    "Stagnant_Shadow_Duty",
                    "Stagnant_Shadow_Timbre",
                    "Stagnant_Shadow_Mechwolf",
                    "Stagnant_Shadow_Gloam",
                    "Stagnant_Shadow_Sloggyre",
                    "Stagnant_Shadow_Gelidmoon",
                    "Stagnant_Shadow_Deepsheaf",
                    "Stagnant_Shadow_Cinders",
                    "Stagnant_Shadow_Sirens",
                    "Stagnant_Shadow_Ashes",
                    "Stagnant_Shadow_Soundburst",
                ]
            ),
        )
        ## 饰品关卡
        self.Stage_Ornament = ConfigItem(
            "Stage",
            "Ornament",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Divergent_Universe_Within_the_West_Wind",
                    "Divergent_Universe_Moonlit_Blood",
                    "Divergent_Universe_Unceasing_Strife",
                    "Divergent_Universe_Famished_Worker",
                    "Divergent_Universe_Eternal_Comedy",
                    "Divergent_Universe_To_Sweet_Dreams",
                    "Divergent_Universe_Pouring_Blades",
                    "Divergent_Universe_Fruit_of_Evil",
                    "Divergent_Universe_Permafrost",
                    "Divergent_Universe_Gentle_Words",
                    "Divergent_Universe_Smelted_Heart",
                    "Divergent_Universe_Untoppled_Walls",
                ]
            ),
        )
        ## 使用储备开拓力
        self.Stage_ExtractReservedTrailblazePower = ConfigItem(
            "Stage", "ExtractReservedTrailblazePower", False, BoolValidator()
        )
        ## 使用燃料
        self.Stage_UseFuel = ConfigItem("Stage", "UseFuel", False, BoolValidator())
        ## 保留的燃料数量
        self.Stage_FuelReserve = ConfigItem(
            "Stage", "FuelReserve", 5, RangeValidator(0, 9999)
        )
        ## 历战余响关卡
        self.Stage_EchoOfWar = ConfigItem(
            "Stage",
            "EchoOfWar",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass",
                    "Echo_of_War_Glance_of_Twilight",
                    "Echo_of_War_Inner_Beast_Battlefield",
                    "Echo_of_War_Salutations_of_Ashen_Dreams",
                    "Echo_of_War_Borehole_Planet_Past_Nightmares",
                    "Echo_of_War_Divine_Seed",
                    "Echo_of_War_End_of_the_Eternal_Freeze",
                    "Echo_of_War_Destruction_Beginning",
                ]
            ),
        )
        ## 模拟宇宙关卡
        self.Stage_SimulatedUniverseWorld = ConfigItem(
            "Stage",
            "SimulatedUniverseWorld",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Simulated_Universe_World_3",
                    "Simulated_Universe_World_4",
                    "Simulated_Universe_World_5",
                    "Simulated_Universe_World_6",
                    "Simulated_Universe_World_8",
                ]
            ),
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
        tags.append(
            {
                "text": f"关卡：{STARRAIL_STAGE_BOOK.get(self.get('Stage', self.get('Stage', 'Channel')), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"周本：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'EchoOfWar'), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"模拟宇宙：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'SimulatedUniverseWorld'), '未知关卡')}",
                "color": "blue",
            }
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


class SrcConfig(ConfigBase):
    """SRC配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## SRC 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 SRC 脚本")
        ## SRC 路径
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
            "ExitGame",
            OptionsValidator(["ExitGame", "ExitEmulator"]),
        )
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([SrcUserConfig])

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


class GeneralUserConfig(ConfigBase):
    """通用脚本用户配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 是否在任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        ## 任务前脚本路径
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", str(Path.cwd()), FileValidator()
        )
        ## 是否在任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        ## 任务后脚本路径
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", str(Path.cwd()), FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
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
        """生成通用用户标签列表"""
        tags = []

        # 任务代理标签（使用东4区时间）
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


class GeneralConfig(ConfigBase):
    """通用配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新通用脚本")
        ## 根目录路径
        self.Info_RootPath = ConfigItem(
            "Info", "RootPath", str(Path.cwd()), FileValidator()
        )

        ## Script ----------------------------------------------------------
        ## 脚本路径
        self.Script_ScriptPath = ConfigItem(
            "Script", "ScriptPath", str(Path.cwd()), FileValidator()
        )
        ## 脚本参数
        self.Script_Arguments = ConfigItem(
            "Script", "Arguments", "", AdvancedArgumentValidator()
        )
        ## 是否追踪进程
        self.Script_IfTrackProcess = ConfigItem(
            "Script", "IfTrackProcess", False, BoolValidator()
        )
        ## 追踪进程的名称
        self.Script_TrackProcessName = ConfigItem("Script", "TrackProcessName", "")
        ## 追踪进程的文件路径
        self.Script_TrackProcessExe = ConfigItem("Script", "TrackProcessExe", "")
        ## 追踪进程的启动命令行参数
        self.Script_TrackProcessCmdline = ConfigItem(
            "Script", "TrackProcessCmdline", "", ArgumentValidator()
        )
        self.Script_ConfigPath = ConfigItem(
            "Script", "ConfigPath", str(Path.cwd()), FileValidator()
        )
        ## 配置路径模式
        self.Script_ConfigPathMode = ConfigItem(
            "Script", "ConfigPathMode", "File", OptionsValidator(["File", "Folder"])
        )
        ## 更新配置模式
        self.Script_UpdateConfigMode = ConfigItem(
            "Script",
            "UpdateConfigMode",
            "Never",
            OptionsValidator(["Never", "Success", "Failure", "Always"]),
        )
        ## 日志路径
        self.Script_LogPath = ConfigItem(
            "Script", "LogPath", str(Path.cwd()), FileValidator()
        )
        ## 日志路径格式
        self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "%Y-%m-%d")
        ## 日志时间戳开始位置
        self.Script_LogTimeStart = ConfigItem(
            "Script", "LogTimeStart", 1, RangeValidator(1, 9999)
        )
        ## 日志时间戳结束位置
        self.Script_LogTimeEnd = ConfigItem(
            "Script", "LogTimeEnd", 1, RangeValidator(1, 9999)
        )
        ## 日志时间格式
        self.Script_LogTimeFormat = ConfigItem(
            "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S"
        )
        ## 成功日志匹配
        self.Script_SuccessLog = ConfigItem("Script", "SuccessLog", "")
        ## 错误日志匹配
        self.Script_ErrorLog = ConfigItem("Script", "ErrorLog", "")

        ## Game ------------------------------------------------------------
        ## 是否启用游戏
        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        ## 游戏类型
        self.Game_Type = ConfigItem(
            "Game", "Type", "Emulator", OptionsValidator(["Emulator", "Client", "URL"])
        )
        ## 游戏路径
        self.Game_Path = ConfigItem("Game", "Path", str(Path.cwd()), FileValidator())
        ## 自定义协议URL
        self.Game_URL = ConfigItem("Game", "URL", "")
        ## 游戏进程名称
        self.Game_ProcessName = ConfigItem("Game", "ProcessName", "")
        ## 游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 等待时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 9999))
        ## 是否强制关闭
        self.Game_IfForceClose = ConfigItem(
            "Game", "IfForceClose", False, BoolValidator()
        )
        ## 模拟器 ID
        self.Game_EmulatorId = ConfigItem(
            "Game",
            "EmulatorId",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Game_EmulatorIndex = ConfigItem("Game", "EmulatorIndex", "-")

        ## Run -------------------------------------------------------------
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([GeneralUserConfig])

        super().__init__()


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
        self.ScriptConfig = MultipleConfig([MaaConfig, SrcConfig, GeneralConfig])
        ## 队列配置列表
        self.QueueConfig = MultipleConfig([QueueConfig])
        ## 工具箱配置
        self.ToolsConfig = ToolsConfig()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
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
        except:
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
    "General": GeneralConfig,
}
"""配置类映射表"""
