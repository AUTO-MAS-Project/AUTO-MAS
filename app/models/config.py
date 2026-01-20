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


import re
import uuid
import json
import calendar
from pathlib import Path
from datetime import datetime

from app.utils.constants import UTC4, UTC8, MATERIALS_MAP, RESOURCE_STAGE_INFO
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
    EncryptValidator,
    UUIDValidator,
    DateTimeValidator,
    JSONValidator,
    URLValidator,
    UserNameValidator,
    ArgumentValidator,
    AdvancedArgumentValidator,
)


class EmulatorConfig(ConfigBase):
    """模拟器配置"""

    def __init__(self) -> None:
        super().__init__()

        ## Info ------------------------------------------------------------
        ## 模拟器名称
        self.Info_Name = ConfigItem("Info", "Name", "新模拟器")
        ## 模拟器路径
        self.Info_Path = ConfigItem("Info", "Path", "", FileValidator())

        ## Data ------------------------------------------------------------
        ## 模拟器类型
        self.Data_Type = ConfigItem(
            "Data",
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
        )
        ## 老板键快捷键配置
        self.Data_BossKey = ConfigItem("Data", "BossKey", "[ ]", JSONValidator(list))
        ## 最大等待时间（秒）
        self.Data_MaxWaitTime = ConfigItem(
            "Data", "MaxWaitTime", 60, RangeValidator(1, 9999)
        )


class Webhook(ConfigBase):
    """Webhook 配置"""

    def __init__(self) -> None:
        super().__init__()

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


class QueueItem(ConfigBase):
    """队列项配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        super().__init__()

        ## Info ------------------------------------------------------------
        ## 脚本 ID
        self.Info_ScriptId = ConfigItem(
            "Info",
            "ScriptId",
            "-",
            MultipleUIDValidator("-", self.related_config, "ScriptConfig"),
        )


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:
        super().__init__()

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


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:
        super().__init__()

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
                    "KillSelf",
                    "Sleep",
                    "Hibernate",
                    "Shutdown",
                    "ShutdownForce",
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


class MaaUserConfig(ConfigBase):
    """MAA用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        super().__init__()

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
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
            "Info", "InfrastIndex", "0", VirtualConfigValidator(self.getInfrastIndex)
        )
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 理智药数量
        self.Info_MedicineNumb = ConfigItem(
            "Info", "MedicineNumb", 0, RangeValidator(0, 9999)
        )
        ## 使用源石数量
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

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 上次剿灭日期
        self.Data_LastAnnihilationDate = ConfigItem(
            "Data", "LastAnnihilationDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
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
            "Data", "CustomInfrast", "{ }", JSONValidator(dict)
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

    def getInfrastName(self, v) -> str:

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

    def getInfrastIndex(self, v) -> str:

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
            return v or "0"


class MaaConfig(ConfigBase):
    """MAA配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        super().__init__()

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
        ## 是否限制剿灭每周一次
        self.Run_AnnihilationWeeklyLimit = ConfigItem(
            "Run", "AnnihilationWeeklyLimit", True, BoolValidator()
        )

        self.UserData = MultipleConfig([MaaUserConfig])


class MaaPlanConfig(ConfigBase):
    """MAA计划表配置"""

    def __init__(self) -> None:
        super().__init__()

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
            ## 源石数量
            self.config_item_dict[group]["SeriesNumb"] = ConfigItem(
                group,
                "SeriesNumb",
                "0",
                OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
            )
            ## 关卡
            self.config_item_dict[group]["Stage"] = ConfigItem(group, "Stage", "-")
            ## 关卡 1
            self.config_item_dict[group]["Stage_1"] = ConfigItem(group, "Stage_1", "-")
            ## 关卡 2
            self.config_item_dict[group]["Stage_2"] = ConfigItem(group, "Stage_2", "-")
            ## 关卡 3
            self.config_item_dict[group]["Stage_3"] = ConfigItem(group, "Stage_3", "-")
            ## 备用关卡
            self.config_item_dict[group]["Stage_Remain"] = ConfigItem(
                group, "Stage_Remain", "-"
            )

            for name in [
                "MedicineNumb",
                "SeriesNumb",
                "Stage",
                "Stage_1",
                "Stage_2",
                "Stage_3",
                "Stage_Remain",
            ]:
                setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

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
        super().__init__()

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


class GeneralConfig(ConfigBase):
    """通用配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        super().__init__()

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


def getStage(raw) -> str:
    """获取关卡信息"""

    raw_data = json.loads(raw)

    activity_stage_drop_info = []
    activity_stage_combox = []

    for side_story in raw_data.values():
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
                            "DropName": MATERIALS_MAP.get(stage["Drop"], stage["Drop"]),
                            "Activity": side_story["Activity"],
                        }
                    )

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


class GlobalConfig(ConfigBase):
    """全局配置"""

    ## Function ---------------------------------------------------------
    ## 历史记录保留时间（天）
    Function_HistoryRetentionTime = ConfigItem(
        "Function",
        "HistoryRetentionTime",
        0,
        OptionsValidator([7, 15, 30, 60, 90, 180, 365, 0]),
    )
    ## 是否允许睡眠
    Function_IfAllowSleep = ConfigItem(
        "Function", "IfAllowSleep", False, BoolValidator()
    )
    ## 是否启用静默模式
    Function_IfSilence = ConfigItem("Function", "IfSilence", False, BoolValidator())
    ## 是否同意 Bilibili 协议
    Function_IfAgreeBilibili = ConfigItem(
        "Function", "IfAgreeBilibili", False, BoolValidator()
    )
    ## 是否屏蔽模拟器广告
    Function_IfBlockAd = ConfigItem("Function", "IfBlockAd", False, BoolValidator())

    ## Voice ------------------------------------------------------------
    ## 是否启用语音
    Voice_Enabled = ConfigItem("Voice", "Enabled", False, BoolValidator())
    ## 语音类型
    Voice_Type = ConfigItem(
        "Voice", "Type", "simple", OptionsValidator(["simple", "noisy"])
    )

    ## Start ------------------------------------------------------------
    ## 是否自动启动
    Start_IfSelfStart = ConfigItem("Start", "IfSelfStart", False, BoolValidator())
    ## 是否启动时直接最小化
    Start_IfMinimizeDirectly = ConfigItem(
        "Start", "IfMinimizeDirectly", False, BoolValidator()
    )

    ## UI ---------------------------------------------------------------
    ## 是否显示托盘图标
    UI_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
    ## 是否关闭到托盘
    UI_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())

    ## Notify -----------------------------------------------------------
    ## 任务结果推送时间
    Notify_SendTaskResultTime = ConfigItem(
        "Notify",
        "SendTaskResultTime",
        "不推送",
        OptionsValidator(["不推送", "任何时刻", "仅失败时"]),
    )
    ## 是否发送统计信息
    Notify_IfSendStatistic = ConfigItem(
        "Notify", "IfSendStatistic", False, BoolValidator()
    )
    ## 是否发送六星通知
    Notify_IfSendSixStar = ConfigItem("Notify", "IfSendSixStar", False, BoolValidator())
    ## 是否推送系统通知
    Notify_IfPushPlyer = ConfigItem("Notify", "IfPushPlyer", False, BoolValidator())
    ## 是否发送邮件
    Notify_IfSendMail = ConfigItem("Notify", "IfSendMail", False, BoolValidator())
    ## 是否发送Koishi通知
    Notify_IfKoishiSupport = ConfigItem(
        "Notify", "IfKoishiSupport", False, BoolValidator()
    )
    ## Koishi WebSocket 服务器地址
    Notify_KoishiServerAddress = ConfigItem(
        "Notify", "KoishiServerAddress", "ws://localhost:5140/AUTO_MAS", URLValidator()
    )
    ## Koishi Token
    Notify_KoishiToken = ConfigItem("Notify", "KoishiToken", "")
    ## SMTP 服务器地址
    Notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
    ## 邮箱授权码
    Notify_AuthorizationCode = ConfigItem(
        "Notify", "AuthorizationCode", "", EncryptValidator()
    )
    ## 发件地址
    Notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
    ## 收件地址
    Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
    ## 是否启用 Server 酱
    Notify_IfServerChan = ConfigItem("Notify", "IfServerChan", False, BoolValidator())
    ## Server 酱密钥
    Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
    ## 自定义 Webhook 列表
    Notify_CustomWebhooks = MultipleConfig([Webhook])

    ## Update -----------------------------------------------------------
    ## 是否自动更新
    Update_IfAutoUpdate = ConfigItem("Update", "IfAutoUpdate", False, BoolValidator())
    ## 更新源
    Update_Source = ConfigItem(
        "Update",
        "Source",
        "GitHub",
        OptionsValidator(["GitHub", "MirrorChyan", "AutoSite"]),
    )
    ## 更新频道
    Update_Channel = ConfigItem(
        "Update", "Channel", "stable", OptionsValidator(["stable", "beta"])
    )
    ## 代理地址
    Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
    ## 镜像站 CDK
    Update_MirrorChyanCDK = ConfigItem(
        "Update", "MirrorChyanCDK", "", EncryptValidator()
    )

    ## Data -------------------------------------------------------------
    ## 唯一标识符
    Data_UID = ConfigItem("Data", "UID", str(uuid.uuid4()), UUIDValidator())
    ## 上次统计上传时间
    Data_LastStatisticsUpload = ConfigItem(
        "Data",
        "LastStatisticsUpload",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    ## 上次关卡更新时间
    Data_LastStageUpdated = ConfigItem(
        "Data",
        "LastStageUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    ## 关卡数据的版本标识符
    Data_StageETag = ConfigItem("Data", "StageETag", "")
    ## 关卡数据
    Data_Stage = ConfigItem("Data", "Stage", "{ }", VirtualConfigValidator(getStage))
    ## 上次公告更新时间
    Data_LastNoticeUpdated = ConfigItem(
        "Data",
        "LastNoticeUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    ## 公告的版本标识符
    Data_NoticeETag = ConfigItem("Data", "NoticeETag", "")
    ## 是否显示公告
    Data_IfShowNotice = ConfigItem("Data", "IfShowNotice", True, BoolValidator())
    ## 公告内容
    Data_Notice = ConfigItem("Data", "Notice", "{ }", JSONValidator())
    ## 上次 Web 配置更新时间
    Data_LastWebConfigUpdated = ConfigItem(
        "Data",
        "LastWebConfigUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    ## Web 配置
    Data_WebConfig = ConfigItem("Data", "WebConfig", "[ ]", JSONValidator(list))

    ## Config -----------------------------------------------------------
    ## 模拟器配置列表
    EmulatorConfig = MultipleConfig([EmulatorConfig], if_save_needed=False)
    ## 计划表配置列表
    PlanConfig = MultipleConfig([MaaPlanConfig], if_save_needed=False)
    ## 脚本配置列表
    ScriptConfig = MultipleConfig([MaaConfig, GeneralConfig], if_save_needed=False)
    ## 队列配置列表
    QueueConfig = MultipleConfig([QueueConfig], if_save_needed=False)

    def __init__(self):
        super().__init__()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        GeneralConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaUserConfig.related_config["PlanConfig"] = self.PlanConfig
        QueueItem.related_config["ScriptConfig"] = self.ScriptConfig


CLASS_BOOK = {"MAA": MaaConfig, "MaaPlan": MaaPlanConfig, "General": GeneralConfig}
"""配置类映射表"""
