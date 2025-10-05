#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

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

from pathlib import Path
from datetime import datetime, timedelta
import uuid
from .ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    RangeValidator,
    FileValidator,
    FolderValidator,
    EncryptValidator,
    UUIDValidator,
    DateTimeValidator,
    JSONValidator,
    URLValidator,
    UserNameValidator,
)


class EmulatorManagerConfig(ConfigBase):
    """模拟器管理配置"""

    def __init__(self) -> None:
        super().__init__()
        self.Info_Name = ConfigItem("Info", "Name", "新多开器")

        EmulatorType = [
            "general",
            "mumu",
            "ldplayer",
            "nox",  # 以下都是骗你的, 根本没有写~~
            "memu",
            "blueStacks",
        ]

        self.Info_Type = ConfigItem(
            "Info", "Type", "general", OptionsValidator(EmulatorType)
        )
        self.Data_Path = ConfigItem("Data", "Path", "")

        self.Data_Boss_keys = ConfigItem("Data", "Boss_keys", "[]", JSONValidator(list))

        self.Data_max_wait_time = ConfigItem(
            "Data", "max_wait_time", 60, RangeValidator(-1, 9999)
        )


class Webhook(ConfigBase):
    """Webhook 配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新自定义 Webhook 通知")
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())

        self.Data_Url = ConfigItem("Data", "Url", "", URLValidator())
        self.Data_Template = ConfigItem("Data", "Template", "")
        self.Data_Headers = ConfigItem("Data", "Headers", "{ }", JSONValidator())
        self.Data_Method = ConfigItem(
            "Data", "Method", "POST", OptionsValidator(["POST", "GET"])
        )


class GlobalConfig(ConfigBase):
    """全局配置"""

    Function_HistoryRetentionTime = ConfigItem(
        "Function",
        "HistoryRetentionTime",
        0,
        OptionsValidator([7, 15, 30, 60, 90, 180, 365, 0]),
    )
    Function_IfAllowSleep = ConfigItem(
        "Function", "IfAllowSleep", False, BoolValidator()
    )
    Function_IfSilence = ConfigItem("Function", "IfSilence", False, BoolValidator())
    Function_BossKey = ConfigItem("Function", "BossKey", "")
    Function_IfAgreeBilibili = ConfigItem(
        "Function", "IfAgreeBilibili", False, BoolValidator()
    )
    Function_IfSkipMumuSplashAds = ConfigItem(
        "Function", "IfSkipMumuSplashAds", False, BoolValidator()
    )

    Voice_Enabled = ConfigItem("Voice", "Enabled", False, BoolValidator())
    Voice_Type = ConfigItem(
        "Voice", "Type", "simple", OptionsValidator(["simple", "noisy"])
    )

    Start_IfSelfStart = ConfigItem("Start", "IfSelfStart", False, BoolValidator())
    Start_IfMinimizeDirectly = ConfigItem(
        "Start", "IfMinimizeDirectly", False, BoolValidator()
    )

    UI_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
    UI_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())

    Notify_SendTaskResultTime = ConfigItem(
        "Notify",
        "SendTaskResultTime",
        "不推送",
        OptionsValidator(["不推送", "任何时刻", "仅失败时"]),
    )
    Notify_IfSendStatistic = ConfigItem(
        "Notify", "IfSendStatistic", False, BoolValidator()
    )
    Notify_IfSendSixStar = ConfigItem("Notify", "IfSendSixStar", False, BoolValidator())
    Notify_IfPushPlyer = ConfigItem("Notify", "IfPushPlyer", False, BoolValidator())
    Notify_IfSendMail = ConfigItem("Notify", "IfSendMail", False, BoolValidator())
    Notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
    Notify_AuthorizationCode = ConfigItem(
        "Notify", "AuthorizationCode", "", EncryptValidator()
    )
    Notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
    Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
    Notify_IfServerChan = ConfigItem("Notify", "IfServerChan", False, BoolValidator())
    Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
    Notify_CustomWebhooks = MultipleConfig([Webhook])

    Update_IfAutoUpdate = ConfigItem("Update", "IfAutoUpdate", False, BoolValidator())
    Update_Source = ConfigItem(
        "Update",
        "Source",
        "GitHub",
        OptionsValidator(["GitHub", "MirrorChyan", "AutoSite"]),
    )
    Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
    Update_MirrorChyanCDK = ConfigItem(
        "Update", "MirrorChyanCDK", "", EncryptValidator()
    )

    Data_UID = ConfigItem("Data", "UID", str(uuid.uuid4()), UUIDValidator())
    Data_LastStatisticsUpload = ConfigItem(
        "Data",
        "LastStatisticsUpload",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    Data_LastStageUpdated = ConfigItem(
        "Data",
        "LastStageUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    Data_StageTimeStamp = ConfigItem(
        "Data",
        "StageTimeStamp",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    Data_Stage = ConfigItem("Data", "Stage", "{ }", JSONValidator())
    Data_LastNoticeUpdated = ConfigItem(
        "Data",
        "LastNoticeUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    Data_IfShowNotice = ConfigItem("Data", "IfShowNotice", True, BoolValidator())
    Data_Notice = ConfigItem("Data", "Notice", "{ }", JSONValidator())
    Data_LastWebConfigUpdated = ConfigItem(
        "Data",
        "LastWebConfigUpdated",
        "2000-01-01 00:00:00",
        DateTimeValidator("%Y-%m-%d %H:%M:%S"),
    )
    Data_WebConfig = ConfigItem("Data", "WebConfig", "{ }", JSONValidator())
    EmulatorData = MultipleConfig([EmulatorManagerConfig])


class QueueItem(ConfigBase):
    """队列项配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        super().__init__()

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

        self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
        self.Info_Time = ConfigItem("Info", "Time", "00:00", DateTimeValidator("%H:%M"))


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新队列")
        self.Info_TimeEnabled = ConfigItem(
            "Info", "TimeEnabled", False, BoolValidator()
        )
        self.Info_StartUpEnabled = ConfigItem(
            "Info", "StartUpEnabled", False, BoolValidator()
        )
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

        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        self.Info_StageMode = ConfigItem(
            "Info",
            "StageMode",
            "Fixed",
            MultipleUIDValidator("Fixed", self.related_config, "PlanConfig"),
        )
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "Official",
            OptionsValidator(
                ["Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"]
            ),
        )
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
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
        self.Info_Routine = ConfigItem("Info", "Routine", True, BoolValidator())
        self.Info_InfrastMode = ConfigItem(
            "Info",
            "InfrastMode",
            "Normal",
            OptionsValidator(["Normal", "Rotation", "Custom"]),
        )
        self.Info_InfrastPath = ConfigItem(
            "Info", "InfrastPath", str(Path.cwd()), FileValidator()
        )
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_MedicineNumb = ConfigItem(
            "Info", "MedicineNumb", 0, RangeValidator(0, 9999)
        )
        self.Info_SeriesNumb = ConfigItem(
            "Info",
            "SeriesNumb",
            "0",
            OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
        )
        self.Info_Stage = ConfigItem("Info", "Stage", "-")
        self.Info_Stage_1 = ConfigItem("Info", "Stage_1", "-")
        self.Info_Stage_2 = ConfigItem("Info", "Stage_2", "-")
        self.Info_Stage_3 = ConfigItem("Info", "Stage_3", "-")
        self.Info_Stage_Remain = ConfigItem("Info", "Stage_Remain", "-")
        self.Info_IfSkland = ConfigItem("Info", "IfSkland", False, BoolValidator())
        self.Info_SklandToken = ConfigItem(
            "Info", "SklandToken", "", EncryptValidator()
        )

        self.Emulator_Uuid = ConfigItem("Emulator", "uuid", "")
        self.Emulator_index = ConfigItem("Emulator", "index", "")

        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_LastAnnihilationDate = ConfigItem(
            "Data", "LastAnnihilationDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_LastSklandDate = ConfigItem(
            "Data", "LastSklandDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())
        self.Data_CustomInfrastPlanIndex = ConfigItem(
            "Data", "CustomInfrastPlanIndex", "0"
        )

        self.Task_IfWakeUp = ConfigItem("Task", "IfWakeUp", True, BoolValidator())
        self.Task_IfRecruiting = ConfigItem(
            "Task", "IfRecruiting", True, BoolValidator()
        )
        self.Task_IfBase = ConfigItem("Task", "IfBase", True, BoolValidator())
        self.Task_IfCombat = ConfigItem("Task", "IfCombat", True, BoolValidator())
        self.Task_IfMall = ConfigItem("Task", "IfMall", True, BoolValidator())
        self.Task_IfMission = ConfigItem("Task", "IfMission", True, BoolValidator())
        self.Task_IfAutoRoguelike = ConfigItem(
            "Task", "IfAutoRoguelike", False, BoolValidator()
        )
        self.Task_IfReclamation = ConfigItem(
            "Task", "IfReclamation", False, BoolValidator()
        )

        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        self.Notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
        )
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])


class MaaConfig(ConfigBase):
    """MAA配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 脚本")
        self.Info_Path = ConfigItem("Info", "Path", str(Path.cwd()), FolderValidator())

        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitEmulator",
            OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
        )
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        self.Run_ADBSearchRange = ConfigItem(
            "Run", "ADBSearchRange", 0, RangeValidator(0, 3)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        self.Run_AnnihilationTimeLimit = ConfigItem(
            "Run", "AnnihilationTimeLimit", 40, RangeValidator(1, 9999)
        )
        self.Run_RoutineTimeLimit = ConfigItem(
            "Run", "RoutineTimeLimit", 10, RangeValidator(1, 9999)
        )
        self.Run_AnnihilationWeeklyLimit = ConfigItem(
            "Run", "AnnihilationWeeklyLimit", True, BoolValidator()
        )

        self.UserData = MultipleConfig([MaaUserConfig])


class MaaPlanConfig(ConfigBase):
    """MAA计划表配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 计划表")
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "ALL", OptionsValidator(["ALL", "Weekly"])
        )

        self.config_item_dict: dict[str, dict[str, ConfigItem]] = {}

        for group in [
            "ALL",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]:
            self.config_item_dict[group] = {}

            self.config_item_dict[group]["MedicineNumb"] = ConfigItem(
                group, "MedicineNumb", 0, RangeValidator(0, 9999)
            )
            self.config_item_dict[group]["SeriesNumb"] = ConfigItem(
                group,
                "SeriesNumb",
                "0",
                OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
            )
            self.config_item_dict[group]["Stage"] = ConfigItem(group, "Stage", "-")
            self.config_item_dict[group]["Stage_1"] = ConfigItem(group, "Stage_1", "-")
            self.config_item_dict[group]["Stage_2"] = ConfigItem(group, "Stage_2", "-")
            self.config_item_dict[group]["Stage_3"] = ConfigItem(group, "Stage_3", "-")
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
            dt = datetime.now()
            if dt.time() < datetime.min.time().replace(hour=4):
                dt = dt - timedelta(days=1)
            today = dt.strftime("%A")

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

        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", str(Path.cwd()), FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", str(Path.cwd()), FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")

        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )

        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])


class GeneralConfig(ConfigBase):
    """通用配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新通用脚本")
        self.Info_RootPath = ConfigItem(
            "Info", "RootPath", str(Path.cwd()), FileValidator()
        )

        self.Script_ScriptPath = ConfigItem(
            "Script", "ScriptPath", str(Path.cwd()), FileValidator()
        )
        self.Script_Arguments = ConfigItem("Script", "Arguments", "")
        self.Script_IfTrackProcess = ConfigItem(
            "Script", "IfTrackProcess", False, BoolValidator()
        )
        self.Script_ConfigPath = ConfigItem(
            "Script", "ConfigPath", str(Path.cwd()), FileValidator()
        )
        self.Script_ConfigPathMode = ConfigItem(
            "Script", "ConfigPathMode", "File", OptionsValidator(["File", "Folder"])
        )
        self.Script_UpdateConfigMode = ConfigItem(
            "Script",
            "UpdateConfigMode",
            "Never",
            OptionsValidator(["Never", "Success", "Failure", "Always"]),
        )
        self.Script_LogPath = ConfigItem(
            "Script", "LogPath", str(Path.cwd()), FileValidator()
        )
        self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "%Y-%m-%d")
        self.Script_LogTimeStart = ConfigItem(
            "Script", "LogTimeStart", 1, RangeValidator(1, 9999)
        )
        self.Script_LogTimeEnd = ConfigItem(
            "Script", "LogTimeEnd", 1, RangeValidator(1, 9999)
        )
        self.Script_LogTimeFormat = ConfigItem(
            "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S"
        )
        self.Script_SuccessLog = ConfigItem("Script", "SuccessLog", "")
        self.Script_ErrorLog = ConfigItem("Script", "ErrorLog", "")

        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        self.Game_Type = ConfigItem(
            "Game", "Type", "Emulator", OptionsValidator(["Emulator", "Client"])
        )
        self.Game_Path = ConfigItem("Game", "Path", str(Path.cwd()), FileValidator())
        self.Game_Arguments = ConfigItem("Game", "Arguments", "")
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 9999))
        self.Game_IfForceClose = ConfigItem(
            "Game", "IfForceClose", False, BoolValidator()
        )

        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([GeneralUserConfig])


CLASS_BOOK = {
    "MAA": MaaConfig,
    "MaaPlan": MaaPlanConfig,
    "General": GeneralConfig,
    "EmulatorManager": EmulatorManagerConfig,
}
"""配置类映射表"""
