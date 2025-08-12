#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
import shutil
import asyncio
import calendar
import requests
import truststore
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta, date, timezone
from typing import Literal, Optional, Tuple

from app.models.ConfigBase import *
from app.utils import get_logger

logger = get_logger("配置管理")

STAGE_DAILY_INFO = [
    {"value": "-", "text": "当前/上次", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "1-7", "text": "1-7", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "R8-11", "text": "R8-11", "days": [1, 2, 3, 4, 5, 6, 7]},
    {
        "value": "12-17-HARD",
        "text": "12-17-HARD",
        "days": [1, 2, 3, 4, 5, 6, 7],
    },
    {"value": "CE-6", "text": "龙门币-6/5", "days": [2, 4, 6, 7]},
    {"value": "AP-5", "text": "红票-5", "days": [1, 4, 6, 7]},
    {"value": "CA-5", "text": "技能-5", "days": [2, 3, 5, 7]},
    {"value": "LS-6", "text": "经验-6/5", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "SK-5", "text": "碳-5", "days": [1, 3, 5, 6]},
    {"value": "PR-A-1", "text": "奶/盾芯片", "days": [1, 4, 5, 7]},
    {"value": "PR-A-2", "text": "奶/盾芯片组", "days": [1, 4, 5, 7]},
    {"value": "PR-B-1", "text": "术/狙芯片", "days": [1, 2, 5, 6]},
    {"value": "PR-B-2", "text": "术/狙芯片组", "days": [1, 2, 5, 6]},
    {"value": "PR-C-1", "text": "先/辅芯片", "days": [3, 4, 6, 7]},
    {"value": "PR-C-2", "text": "先/辅芯片组", "days": [3, 4, 6, 7]},
    {"value": "PR-D-1", "text": "近/特芯片", "days": [2, 3, 6, 7]},
    {"value": "PR-D-2", "text": "近/特芯片组", "days": [2, 3, 6, 7]},
]

MATERIALS_MAP: Dict[str, str] = {
    "30165": "重相位对映体",
    "30155": "烧结核凝晶",
    "30145": "晶体电子单元",
    "30135": "D32钢",
    "30125": "双极纳米片",
    "30115": "聚合剂",
    "31094": "手性屈光体",
    "31093": "类凝结核",
    "31084": "环烃预制体",
    "31083": "环烃聚质",
    "31074": "固化纤维板",
    "31073": "褐素纤维",
    "31064": "转质盐聚块",
    "31063": "转质盐组",
    "31054": "切削原液",
    "31053": "化合切削液",
    "31044": "精炼溶剂",
    "31043": "半自然溶剂",
    "31034": "晶体电路",
    "31033": "晶体元件",
    "31024": "炽合金块",
    "31023": "炽合金",
    "31014": "聚合凝胶",
    "31013": "凝胶",
    "30074": "白马醇",
    "30073": "扭转醇",
    "30084": "三水锰矿",
    "30083": "轻锰矿",
    "30094": "五水研磨石",
    "30093": "研磨石",
    "30104": "RMA70-24",
    "30103": "RMA70-12",
    "30014": "提纯源岩",
    "30013": "固源岩组",
    "30012": "固源岩",
    "30011": "源岩",
    "30064": "改量装置",
    "30063": "全新装置",
    "30062": "装置",
    "30061": "破损装置",
    "30034": "聚酸酯块",
    "30033": "聚酸酯组",
    "30032": "聚酸酯",
    "30031": "酯原料",
    "30024": "糖聚块",
    "30023": "糖组",
    "30022": "糖",
    "30021": "代糖",
    "30044": "异铁块",
    "30043": "异铁组",
    "30042": "异铁",
    "30041": "异铁碎片",
    "30054": "酮阵列",
    "30053": "酮凝集组",
    "30052": "酮凝集",
    "30051": "双酮",
}


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
    Notify_IfCompanyWebHookBot = ConfigItem(
        "Notify", "IfCompanyWebHookBot", False, BoolValidator()
    )
    Notify_CompanyWebHookBotUrl = ConfigItem("Notify", "CompanyWebHookBotUrl", "")

    Update_IfAutoUpdate = ConfigItem("Update", "IfAutoUpdate", False, BoolValidator())
    Update_UpdateType = ConfigItem(
        "Update", "UpdateType", "stable", OptionsValidator(["stable", "beta"])
    )
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


class QueueItem(ConfigBase):
    """队列项配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_ScriptId = ConfigItem("Info", "ScriptId", None, UidValidator())


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
        self.Info_Time = ConfigItem("Info", "Time", "00:00")


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

        self.Data_LastProxyTime = ConfigItem(
            "Data", "LastProxyTime", "2000-01-01 00:00:00"
        )
        self.Data_LastProxyHistory = ConfigItem(
            "Data", "LastProxyHistory", "暂无历史运行记录"
        )

        self.TimeSet = MultipleConfig([TimeSet])
        self.QueueItem = MultipleConfig([QueueItem])


class MaaUserConfig(ConfigBase):
    """MAA用户配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        self.Info_StageMode = ConfigItem("Info", "StageMode", "固定")
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
            "Info", "RemainedDay", -1, RangeValidator(-1, 1024)
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
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_MedicineNumb = ConfigItem(
            "Info", "MedicineNumb", 0, RangeValidator(0, 1024)
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
        self.Info_SklandToken = ConfigItem("Info", "SklandToken", "")

        self.Data_LastProxyDate = ConfigItem("Data", "LastProxyDate", "2000-01-01")
        self.Data_LastAnnihilationDate = ConfigItem(
            "Data", "LastAnnihilationDate", "2000-01-01"
        )
        self.Data_LastSklandDate = ConfigItem("Data", "LastSklandDate", "2000-01-01")
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 1024)
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
        self.Notify_IfCompanyWebHookBot = ConfigItem(
            "Notify", "IfCompanyWebHookBot", False, BoolValidator()
        )
        self.Notify_CompanyWebHookBotUrl = ConfigItem(
            "Notify", "CompanyWebHookBotUrl", ""
        )

    def get_plan_info(self) -> Dict[str, Union[str, int]]:
        """获取当前的计划下信息"""

        if self.get("Info", "StageMode") == "固定":
            return {
                "MedicineNumb": self.get("Info", "MedicineNumb"),
                "SeriesNumb": self.get("Info", "SeriesNumb"),
                "Stage": self.get("Info", "Stage"),
                "Stage_1": self.get("Info", "Stage_1"),
                "Stage_2": self.get("Info", "Stage_2"),
                "Stage_3": self.get("Info", "Stage_3"),
                "Stage_Remain": self.get("Info", "Stage_Remain"),
            }
        else:
            plan = Config.PlanConfig[uuid.UUID(self.get("Info", "StageMode"))]
            if isinstance(plan, MaaPlanConfig):
                return {
                    "MedicineNumb": plan.get_current_info("MedicineNumb").getValue(),
                    "SeriesNumb": plan.get_current_info("SeriesNumb").getValue(),
                    "Stage": plan.get_current_info("Stage").getValue(),
                    "Stage_1": plan.get_current_info("Stage_1").getValue(),
                    "Stage_2": plan.get_current_info("Stage_2").getValue(),
                    "Stage_3": plan.get_current_info("Stage_3").getValue(),
                    "Stage_Remain": plan.get_current_info("Stage_Remain").getValue(),
                }
            else:
                raise ValueError("Invalid plan type")


class MaaConfig(ConfigBase):
    """MAA配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 脚本")
        self.Info_Path = ConfigItem("Info", "Path", ".", FolderValidator())

        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitEmulator",
            OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
        )
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
        )
        self.Run_ADBSearchRange = ConfigItem(
            "Run", "ADBSearchRange", 0, RangeValidator(0, 3)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 1024)
        )
        self.Run_AnnihilationTimeLimit = ConfigItem(
            "Run", "AnnihilationTimeLimit", 40, RangeValidator(1, 1024)
        )
        self.Run_RoutineTimeLimit = ConfigItem(
            "Run", "RoutineTimeLimit", 10, RangeValidator(1, 1024)
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

        self.config_item_dict: dict[str, Dict[str, ConfigItem]] = {}

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
                group, "MedicineNumb", 0, RangeValidator(0, 1024)
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
            raise ValueError("The mode is invalid.")


class GeneralUserConfig(ConfigBase):
    """通用脚本用户配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 1024)
        )
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")

        self.Data_LastProxyDate = ConfigItem("Data", "LastProxyDate", "2000-01-01")
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 1024)
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
        self.Notify_IfCompanyWebHookBot = ConfigItem(
            "Notify", "IfCompanyWebHookBot", False, BoolValidator()
        )
        self.Notify_CompanyWebHookBotUrl = ConfigItem(
            "Notify", "CompanyWebHookBotUrl", ""
        )


class GeneralConfig(ConfigBase):
    """通用配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新通用脚本")
        self.Info_RootPath = ConfigItem("Info", "RootPath", ".", FileValidator())

        self.Script_ScriptPath = ConfigItem(
            "Script", "ScriptPath", ".", FileValidator()
        )
        self.Script_Arguments = ConfigItem("Script", "Arguments", "")
        self.Script_IfTrackProcess = ConfigItem(
            "Script", "IfTrackProcess", False, BoolValidator()
        )
        self.Script_ConfigPath = ConfigItem(
            "Script", "ConfigPath", ".", FileValidator()
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
        self.Script_LogPath = ConfigItem("Script", "LogPath", ".", FileValidator())
        self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "%Y-%m-%d")
        self.Script_LogTimeStart = ConfigItem(
            "Script", "LogTimeStart", 1, RangeValidator(1, 1024)
        )
        self.Script_LogTimeEnd = ConfigItem(
            "Script", "LogTimeEnd", 1, RangeValidator(1, 1024)
        )
        self.Script_LogTimeFormat = ConfigItem(
            "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S"
        )
        self.Script_SuccessLog = ConfigItem("Script", "SuccessLog", "")
        self.Script_ErrorLog = ConfigItem("Script", "ErrorLog", "")

        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        self.Game_Style = ConfigItem(
            "Game", "Style", "Emulator", OptionsValidator(["Emulator", "Client"])
        )
        self.Game_Path = ConfigItem("Game", "Path", ".", FileValidator())
        self.Game_Arguments = ConfigItem("Game", "Arguments", "")
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 1024))
        self.Game_IfForceClose = ConfigItem(
            "Game", "IfForceClose", False, BoolValidator()
        )

        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 1024)
        )
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 1024)
        )

        self.UserData = MultipleConfig([GeneralUserConfig])


CLASS_BOOK = {"MAA": MaaConfig, "MaaPlan": MaaPlanConfig, "General": GeneralConfig}
TYPE_BOOK = {"MaaConfig": "MAA", "GeneralConfig": "通用"}


class AppConfig(GlobalConfig):

    VERSION = "5.0.0.1"

    def __init__(self) -> None:
        super().__init__(if_save_multi_config=False)

        logger.info("")
        logger.info("===================================")
        logger.info("AUTO_MAA 后端应用程序")
        logger.info(f"版本号： v{self.VERSION}")
        logger.info(f"工作目录： {Path.cwd()}")
        logger.info("===================================")

        self.log_path = Path.cwd() / "debug/app.log"
        self.database_path = Path.cwd() / "data/data.db"
        self.config_path = Path.cwd() / "config"
        self.key_path = Path.cwd() / "data/key"
        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

        self.silence_dict: Dict[Path, datetime] = {}
        self.power_sign = "NoAction"
        self.if_ignore_silence: List[uuid.UUID] = []
        self.last_stage_update = None
        self.stage_info: Optional[Dict[str, List[Dict[str, str]]]] = None
        self.temp_task: List[asyncio.Task] = []

        self.ScriptConfig = MultipleConfig([MaaConfig, GeneralConfig])
        self.PlanConfig = MultipleConfig([MaaPlanConfig])
        self.QueueConfig = MultipleConfig([QueueConfig])

        truststore.inject_into_ssl()

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.connect(self.config_path / "Config.json")
        await self.ScriptConfig.connect(self.config_path / "ScriptConfig.json")
        await self.PlanConfig.connect(self.config_path / "PlanConfig.json")
        await self.QueueConfig.connect(self.config_path / "QueueConfig.json")

        from .task_manager import TaskManager

        self.task_dict = TaskManager.task_dict

        # self.check_data()
        logger.info("程序初始化完成")

    async def add_script(
        self, script: Literal["MAA", "General"]
    ) -> tuple[uuid.UUID, ConfigBase]:
        """添加脚本配置"""

        logger.info(f"添加脚本配置：{script}")

        return await self.ScriptConfig.add(CLASS_BOOK[script])

    async def get_script(self, script_id: Optional[str]) -> tuple[list, dict]:
        """获取脚本配置"""

        logger.info(f"获取脚本配置：{script_id}")

        if script_id is None:
            data = await self.ScriptConfig.toDict()
        else:
            data = await self.ScriptConfig.get(uuid.UUID(script_id))

        index = data.pop("instances", [])

        return list(index), data

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置：{script_id}")

        uid = uuid.UUID(script_id)

        if uid in self.task_dict:
            raise RuntimeError(
                f"Cannot update script {script_id} while tasks are running."
            )

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新脚本配置：{script_id} - {group}.{name} = {value}")
                await self.ScriptConfig[uid].set(group, name, value)

        await self.ScriptConfig.save()

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        logger.info(f"删除脚本配置：{script_id}")

        uid = uuid.UUID(script_id)

        if uid in self.task_dict:
            raise RuntimeError(
                f"Cannot delete script {script_id} while tasks are running."
            )

        await self.ScriptConfig.remove(uid)

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本：{index_list}")

        await self.ScriptConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def add_user(self, script_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加用户配置"""

        logger.info(f"{script_id} 添加用户配置")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        if isinstance(script_config, MaaConfig):
            uid, config = await script_config.UserData.add(MaaUserConfig)
        elif isinstance(script_config, GeneralConfig):
            uid, config = await script_config.UserData.add(GeneralUserConfig)
        else:
            raise TypeError(f"Unsupported script config type: {type(script_config)}")

        await self.ScriptConfig.save()
        return uid, config

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置：{user_id}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        uid = uuid.UUID(user_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新脚本配置：{script_id} - {group}.{name} = {value}")
                if isinstance(script_config, (MaaConfig | GeneralConfig)):
                    await script_config.UserData[uid].set(group, name, value)

        await self.ScriptConfig.save()

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置：{user_id}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        uid = uuid.UUID(user_id)

        if isinstance(script_config, (MaaConfig | GeneralConfig)):
            await script_config.UserData.remove(uid)
            await self.ScriptConfig.save()

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        logger.info(f"{script_id} 重新排序用户：{index_list}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        if isinstance(script_config, (MaaConfig | GeneralConfig)):
            await script_config.UserData.setOrder([uuid.UUID(_) for _ in index_list])
            await self.ScriptConfig.save()

    async def add_queue(self) -> tuple[uuid.UUID, ConfigBase]:
        """添加调度队列"""

        logger.info("添加调度队列")

        return await self.QueueConfig.add(QueueConfig)

    async def get_queue(self, queue_id: Optional[str]) -> tuple[list, dict]:
        """获取调度队列配置"""

        logger.info(f"获取调度队列配置：{queue_id}")

        if queue_id is None:
            data = await self.QueueConfig.toDict()
        else:
            data = await self.QueueConfig.get(uuid.UUID(queue_id))

        index = data.pop("instances", [])

        return list(index), data

    async def update_queue(
        self, queue_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新调度队列配置"""

        logger.info(f"更新调度队列配置：{queue_id}")

        uid = uuid.UUID(queue_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新调度队列配置：{queue_id} - {group}.{name} = {value}")
                await self.QueueConfig[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        logger.info(f"删除调度队列配置：{queue_id}")

        await self.QueueConfig.remove(uuid.UUID(queue_id))

    async def reorder_queue(self, index_list: list[str]) -> None:
        """重新排序调度队列"""

        logger.info(f"重新排序调度队列：{index_list}")

        await self.QueueConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def add_time_set(self, queue_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加时间设置配置"""

        logger.info(f"{queue_id} 添加时间设置配置")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            uid, config = await queue_config.TimeSet.add(TimeSet)
        else:
            raise TypeError(f"Unsupported script config type: {type(queue_config)}")

        await self.QueueConfig.save()
        return uid, config

    async def update_time_set(
        self, queue_id: str, time_set_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新时间设置配置"""

        logger.info(f"{queue_id} 更新时间设置配置：{time_set_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(time_set_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新时间设置配置：{queue_id} - {group}.{name} = {value}")
                if isinstance(queue_config, QueueConfig):
                    await queue_config.TimeSet[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        logger.info(f"{queue_id} 删除时间设置配置：{time_set_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(time_set_id)

        if isinstance(queue_config, QueueConfig):
            await queue_config.TimeSet.remove(uid)
            await self.QueueConfig.save()

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        logger.info(f"{queue_id} 重新排序时间设置：{index_list}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            await queue_config.TimeSet.setOrder([uuid.UUID(_) for _ in index_list])
            await self.QueueConfig.save()

    async def add_plan(
        self, script: Literal["MaaPlan"]
    ) -> tuple[uuid.UUID, ConfigBase]:
        """添加计划表"""

        logger.info(f"添加计划表：{script}")

        return await self.PlanConfig.add(CLASS_BOOK[script])

    async def get_plan(self, plan_id: Optional[str]) -> tuple[list, dict]:
        """获取计划表配置"""

        logger.info(f"获取计划表配置：{plan_id}")

        if plan_id is None:
            data = await self.PlanConfig.toDict()
        else:
            data = await self.PlanConfig.get(uuid.UUID(plan_id))

        index = data.pop("instances", [])

        return list(index), data

    async def update_plan(self, plan_id: str, data: Dict[str, Dict[str, Any]]) -> None:
        """更新计划表配置"""

        logger.info(f"更新计划表配置：{plan_id}")

        uid = uuid.UUID(plan_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新计划表配置：{plan_id} - {group}.{name} = {value}")
                await self.PlanConfig[uid].set(group, name, value)

        await self.PlanConfig.save()

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置：{plan_id}")

        await self.PlanConfig.remove(uuid.UUID(plan_id))

    async def reorder_plan(self, index_list: list[str]) -> None:
        """重新排序计划表"""

        logger.info(f"重新排序计划表：{index_list}")

        await self.PlanConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def add_queue_item(self, queue_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加队列项配置"""

        logger.info(f"{queue_id} 添加队列项配置")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            uid, config = await queue_config.QueueItem.add(QueueItem)
        else:
            raise TypeError(f"Unsupported script config type: {type(queue_config)}")

        await self.QueueConfig.save()
        return uid, config

    async def update_queue_item(
        self, queue_id: str, queue_item_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新队列项配置"""

        logger.info(f"{queue_id} 更新队列项配置：{queue_item_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(queue_item_id)

        for group, items in data.items():
            for name, value in items.items():
                if uuid.UUID(value) not in self.ScriptConfig:
                    raise ValueError(f"Script with uid {value} does not exist.")
                logger.debug(f"更新队列项配置：{queue_id} - {group}.{name} = {value}")
                if isinstance(queue_config, QueueConfig):
                    await queue_config.QueueItem[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置：{queue_item_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(queue_item_id)

        if isinstance(queue_config, QueueConfig):
            await queue_config.QueueItem.remove(uid)
            await self.QueueConfig.save()

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项：{index_list}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            await queue_config.QueueItem.setOrder([uuid.UUID(_) for _ in index_list])
            await self.QueueConfig.save()

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("Get global settings")

        return await self.toDict(ignore_multi_config=True)

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("Update global settings...")

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"Update global settings - {group}.{name} = {value}")
                await self.set(group, name, value)

        logger.success("Global settings updated successfully.")

    def server_date(self) -> date:
        """
        获取当前的服务器日期

        :return: 当前的服务器日期
        :rtype: date
        """

        dt = datetime.now()
        if dt.time() < datetime.min.time().replace(hour=4):
            dt = dt - timedelta(days=1)
        return dt.date()

    def get_proxies(self) -> Dict[str, str]:
        """获取代理设置"""
        return {
            "http": self.get("Update", "ProxyAddress"),
            "https": self.get("Update", "ProxyAddress"),
        }

    async def get_stage_info(
        self,
        type: Literal[
            "Today",
            "ALL",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "Info",
        ],
    ):
        """获取关卡信息"""

        if type == "Today":
            dt = self.server_date()
            index = dt.strftime("%A")
        else:
            index = type

        if self.stage_info is not None:
            task = asyncio.create_task(self.get_stage())
            self.temp_task.append(task)
            task.add_done_callback(lambda t: self.temp_task.remove(t))
        else:
            await self.get_stage()

        return self.stage_info.get(index, []) if self.stage_info is not None else []

    async def get_stage(self) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """更新活动关卡信息"""

        if self.last_stage_update is not None and (
            datetime.now() - self.last_stage_update
        ) < timedelta(hours=1):
            logger.info("No need to update stage info, using cached data.")
            return self.stage_info if self.stage_info is not None else {}

        logger.info("开始获取活动关卡信息")

        try:
            response = requests.get(
                "https://api.maa.plus/MaaAssistantArknights/api/stageAndTasksUpdateTime.json",
                timeout=10,
                proxies=self.get_proxies(),
            )
            if response.status_code == 200:
                remote_time_stamp = datetime.strptime(
                    str(response.json().get("timestamp", 20000101000000)),
                    "%Y%m%d%H%M%S",
                )
            else:
                logger.warning(f"无法从MAA服务器获取活动关卡时间戳:{response.text}")
                remote_time_stamp = datetime.fromtimestamp(0)
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡时间戳: {e}")
            remote_time_stamp = datetime.fromtimestamp(0)

        if (Path.cwd() / "data/StageInfo/TimeStamp.txt").exists() and (
            Path.cwd() / "data/StageInfo/StageInfo.json"
        ).exists():
            local_time_stamp = datetime.strptime(
                (Path.cwd() / "data/StageInfo/TimeStamp.txt")
                .read_text(encoding="utf-8")
                .strip(),
                "%Y%m%d%H%M%S",
            )
            with (Path.cwd() / "data/StageInfo/StageInfo.json").open(
                "r", encoding="utf-8"
            ) as f:
                local_stage_info = json.load(f)
        else:
            local_time_stamp = datetime.fromtimestamp(0)

        # 本地文件关卡信息无需更新，直接返回本地数据
        if datetime.fromtimestamp(0) < remote_time_stamp <= local_time_stamp:

            logger.info("使用本地关卡信息")
            self.stage_info = local_stage_info
            self.last_stage_update = datetime.now()
            return local_stage_info

        # 需要更新关卡信息
        logger.info("从远端更新关卡信息")

        try:
            response = requests.get(
                "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivity.json",
                timeout=10,
                proxies=self.get_proxies(),
            )
            if response.status_code == 200:
                stage_infos = (
                    response.json().get("Official", {}).get("sideStoryStage", [])
                )
                if_get_maa_stage = True
            else:
                logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
                if_get_maa_stage = False
                stage_infos = []
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")
            if_get_maa_stage = False
            stage_infos = []

        def normalize_drop(value: str) -> str:
            # 去前后空格与常见零宽字符
            s = str(value).strip()
            s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
            return s

        now_utc = datetime.now(timezone.utc)

        def parse_utc(dt_str: str) -> datetime:
            return datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )

        side_story_info: List[Dict[str, Any]] = []

        for s in stage_infos:
            act = s.get("Activity", {}) or {}
            try:
                start_utc = parse_utc(act["UtcStartTime"])
                expire_utc = parse_utc(act["UtcExpireTime"])
            except Exception:
                continue

            if start_utc <= now_utc < expire_utc:
                raw_drop = s.get("Drop", "")
                drop_id = normalize_drop(raw_drop)

                if drop_id.isdigit():
                    drop_name = MATERIALS_MAP.get(drop_id, "未知材料")
                else:
                    drop_name = (
                        "DESC:" + drop_id
                    )  # 非纯数字，直接用文本.加一个DESC前缀方便前端区分

                side_story_info.append(
                    {
                        "Display": s.get("Display", ""),
                        "Value": s.get("Value", ""),
                        "Drop": raw_drop,
                        "DropName": drop_name,
                        "Activity": s.get("Activity", {}),
                    }
                )

        side_story_stage = []

        for stage_info in stage_infos:

            if (
                datetime.strptime(
                    stage_info["Activity"]["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                )
                < datetime.now()
                < datetime.strptime(
                    stage_info["Activity"]["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                )
            ):
                side_story_stage.append(
                    {"label": stage_info["Value"], "value": stage_info["Value"]}
                )

        self.stage_info = {}

        for day in range(0, 8):

            today_stage = []

            for stage_info in STAGE_DAILY_INFO:

                if day in stage_info["days"] or day == 0:
                    today_stage.append(
                        {"label": stage_info["text"], "value": stage_info["value"]}
                    )

            self.stage_info[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                side_story_stage + today_stage
            )

        self.stage_info["Info"] = side_story_info

        if if_get_maa_stage:

            logger.success("成功获取远端活动关卡信息")
            self.last_stage_update = datetime.now()
            (Path.cwd() / "data/StageInfo").mkdir(parents=True, exist_ok=True)
            (Path.cwd() / "data/StageInfo/TimeStamp.txt").write_text(
                remote_time_stamp.strftime("%Y%m%d%H%M%S"), encoding="utf-8"
            )
            with (Path.cwd() / "data/StageInfo/StageInfo.json").open(
                "w", encoding="utf-8"
            ) as f:
                json.dump(self.stage_info, f, ensure_ascii=False, indent=4)

        return self.stage_info

    async def get_script_combox(self):
        """获取脚本下拉框信息"""

        logger.info("Getting script combo box information...")
        data = [{"label": "未选择", "value": None}]
        for uid, script in self.ScriptConfig.items():
            data.append(
                {
                    "label": f"{TYPE_BOOK[script.__class__.__name__]} - {script.get('Info', 'Name')}",
                    "value": str(uid),
                }
            )
        logger.success("Script combo box information retrieved successfully.")

        return data

    async def get_task_combox(self):
        """获取任务下拉框信息"""

        logger.info("Getting task combo box information...")
        data = [{"label": "未选择", "value": None}]
        for uid, script in self.QueueConfig.items():
            data.append(
                {
                    "label": f"队列 - {script.get('Info', 'Name')}",
                    "value": str(uid),
                }
            )
        for uid, script in self.ScriptConfig.items():
            data.append(
                {
                    "label": f"脚本 - {TYPE_BOOK[script.__class__.__name__]} - {script.get('Info', 'Name')}",
                    "value": str(uid),
                }
            )
        logger.success("Task combo box information retrieved successfully.")

        return data

    async def get_server_info(self, type: str) -> Dict[str, Any]:
        """获取公告信息"""

        logger.info(f"开始从 AUTO_MAA 服务器获取 {type} 信息")

        response = requests.get(
            url=f"http://221.236.27.82:10197/d/AUTO_MAA/Server/{type}.json",
            timeout=10,
            proxies=self.get_proxies(),
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"无法从 AUTO_MAA 服务器获取 {type} 信息:{response.text}")
            raise ConnectionError(
                "Cannot connect to the notice server. Please check your network connection or try again later."
            )

    async def save_maa_log(self, log_path: Path, logs: list, maa_result: str) -> bool:
        """
        保存MAA日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :type log_path: Path
        :param logs: 日志内容列表
        :type logs: list
        :param maa_result: MAA 结果
        :type maa_result: str
        :return: 是否包含6★招募
        :rtype: bool
        """

        logger.info(f"开始处理 MAA 日志，日志长度: {len(logs)}，日志标记：{maa_result}")

        data = {
            "recruit_statistics": defaultdict(int),
            "drop_statistics": defaultdict(dict),
            "maa_result": maa_result,
        }

        if_six_star = False

        # 公招统计（仅统计招募到的）
        confirmed_recruit = False
        current_star_level = None
        i = 0
        while i < len(logs):
            if "公招识别结果:" in logs[i]:
                current_star_level = None  # 每次识别公招时清空之前的星级
                i += 1
                while i < len(logs) and "Tags" not in logs[i]:  # 读取所有公招标签
                    i += 1

                if i < len(logs) and "Tags" in logs[i]:  # 识别星级
                    star_match = re.search(r"(\d+)\s*★ Tags", logs[i])
                    if star_match:
                        current_star_level = f"{star_match.group(1)}★"
                        if current_star_level == "6★":
                            if_six_star = True

            if "已确认招募" in logs[i]:  # 只有确认招募后才统计
                confirmed_recruit = True

            if confirmed_recruit and current_star_level:
                data["recruit_statistics"][current_star_level] += 1
                confirmed_recruit = False  # 重置，等待下一次公招
                current_star_level = None  # 清空已处理的星级

            i += 1

        # 掉落统计
        # 存储所有关卡的掉落统计
        all_stage_drops = {}

        # 查找所有Fight任务的开始和结束位置
        fight_tasks = []
        for i, line in enumerate(logs):
            if "开始任务: Fight" in line or "开始任务: 刷理智" in line:
                # 查找对应的任务结束位置
                end_index = -1
                for j in range(i + 1, len(logs)):
                    if "完成任务: Fight" in logs[j] or "完成任务: 刷理智" in logs[j]:
                        end_index = j
                        break
                    # 如果遇到新的Fight任务开始，则当前任务没有正常结束
                    if j < len(logs) and (
                        "开始任务: Fight" in logs[j] or "开始任务: 刷理智" in logs[j]
                    ):
                        break

                # 如果找到了结束位置，记录这个任务的范围
                if end_index != -1:
                    fight_tasks.append((i, end_index))

        # 处理每个Fight任务
        for start_idx, end_idx in fight_tasks:
            # 提取当前任务的日志
            task_logs = logs[start_idx : end_idx + 1]

            # 查找任务中的最后一次掉落统计
            last_drop_stats = {}
            current_stage = None

            for line in task_logs:
                # 匹配掉落统计行，如"1-7 掉落统计:"
                drop_match = re.search(r"([A-Za-z0-9\-]+) 掉落统计:", line)
                if drop_match:
                    # 发现新的掉落统计，重置当前关卡的掉落数据
                    current_stage = drop_match.group(1)
                    last_drop_stats = {}
                    continue

                # 如果已经找到了关卡，处理掉落物
                if current_stage:
                    item_match: List[str] = re.findall(
                        r"^(?!\[)(\S+?)\s*:\s*([\d,]+)(?:\s*\(\+[\d,]+\))?",
                        line,
                        re.M,
                    )
                    for item, total in item_match:
                        # 解析数值时去掉逗号 （如 2,160 -> 2160）
                        total = int(total.replace(",", ""))

                        # 黑名单
                        if item not in [
                            "当前次数",
                            "理智",
                            "最快截图耗时",
                            "专精等级",
                            "剩余时间",
                        ]:
                            last_drop_stats[item] = total

            # 如果任务中有掉落统计，更新总统计
            if current_stage and last_drop_stats:
                if current_stage not in all_stage_drops:
                    all_stage_drops[current_stage] = {}

                # 累加掉落数据
                for item, count in last_drop_stats.items():
                    all_stage_drops[current_stage].setdefault(item, 0)
                    all_stage_drops[current_stage][item] += count

        # 将累加后的掉落数据保存到结果中
        data["drop_statistics"] = all_stage_drops

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as f:
            f.writelines(logs)
        with log_path.with_suffix(".json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.success(
            f"MAA 日志统计完成，日志路径：{log_path}",
        )

        return if_six_star

    async def save_general_log(
        self, log_path: Path, logs: list, general_result: str
    ) -> None:
        """
        保存通用日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :param logs: 日志内容列表
        :param general_result: 待保存的日志结果信息
        """

        logger.info(
            f"开始处理通用日志，日志长度: {len(logs)}，日志标记：{general_result}"
        )

        data: Dict[str, str] = {"general_result": general_result}

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.with_suffix(".log").open("w", encoding="utf-8") as f:
            f.writelines(logs)
        with log_path.with_suffix(".json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.success(f"通用日志统计完成，日志路径：{log_path.with_suffix('.log')}")

    def merge_statistic_info(self, statistic_path_list: List[Path]) -> dict:
        """
        合并指定数据统计信息文件

        :param statistic_path_list: 需要合并的统计信息文件路径列表
        :return: 合并后的统计信息字典
        """

        logger.info(f"开始合并统计信息文件，共计 {len(statistic_path_list)} 个文件")

        data: Dict[str, Any] = {"index": {}}

        for json_file in statistic_path_list:

            with json_file.open("r", encoding="utf-8") as f:
                single_data = json.load(f)

            for key in single_data.keys():

                if key not in data:
                    data[key] = {}

                # 合并公招统计
                if key == "recruit_statistics":

                    for star_level, count in single_data[key].items():
                        if star_level not in data[key]:
                            data[key][star_level] = 0
                        data[key][star_level] += count

                # 合并掉落统计
                elif key == "drop_statistics":

                    for stage, drops in single_data[key].items():
                        if stage not in data[key]:
                            data[key][stage] = {}  # 初始化关卡

                        for item, count in drops.items():

                            if item not in data[key][stage]:
                                data[key][stage][item] = 0
                            data[key][stage][item] += count

                # 录入运行结果
                elif key in ["maa_result", "general_result"]:

                    actual_date = datetime.strptime(
                        f"{json_file.parent.parent.name} {json_file.stem}",
                        "%Y-%m-%d %H-%M-%S",
                    ) + timedelta(
                        days=(
                            1
                            if datetime.strptime(json_file.stem, "%H-%M-%S").time()
                            < datetime.min.time().replace(hour=4)
                            else 0
                        )
                    )

                    if single_data[key] != "Success!":
                        if "error_info" not in data:
                            data["error_info"] = {}
                        data["error_info"][actual_date.strftime("%d日 %H:%M:%S")] = (
                            single_data[key]
                        )

                    data["index"][actual_date] = [
                        actual_date.strftime("%d日 %H:%M:%S"),
                        ("完成" if single_data[key] == "Success!" else "异常"),
                        json_file,
                    ]

        data["index"] = [data["index"][_] for _ in sorted(data["index"])]

        logger.success(
            f"统计信息合并完成，共计 {len(data['index'])} 条记录",
        )

        return {k: v for k, v in data.items() if v}

    def search_history(
        self, mode: str, start_date: datetime, end_date: datetime
    ) -> dict:
        """
        搜索指定范围内的历史记录

        :param mode: 合并模式（按日合并、按周合并、按月合并）
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 搜索到的历史记录字典
        """

        logger.info(
            f"开始搜索历史记录，合并模式：{mode}，日期范围：{start_date} 至 {end_date}"
        )

        history_dict = {}

        for date_folder in (Path.cwd() / "history").iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:

                date = datetime.strptime(date_folder.name, "%Y-%m-%d")

                if not (start_date <= date <= end_date):
                    continue  # 只统计在范围内的日期

                if mode == "按日合并":
                    date_name = date.strftime("%Y年 %m月 %d日")
                elif mode == "按周合并":
                    year, week, _ = date.isocalendar()
                    date_name = f"{year}年 第{week}周"
                elif mode == "按月合并":
                    date_name = date.strftime("%Y年 %m月")

                if date_name not in history_dict:
                    history_dict[date_name] = {}

                for user_folder in date_folder.iterdir():
                    if not user_folder.is_dir():
                        continue  # 只处理用户文件夹

                    if user_folder.stem not in history_dict[date_name]:
                        history_dict[date_name][user_folder.stem] = list(
                            user_folder.with_suffix("").glob("*.json")
                        )
                    else:
                        history_dict[date_name][user_folder.stem] += list(
                            user_folder.with_suffix("").glob("*.json")
                        )

            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"历史记录搜索完成，共计 {len(history_dict)} 条记录")

        return {
            k: v
            for k, v in sorted(history_dict.items(), key=lambda x: x[0], reverse=True)
        }

    def clean_old_history(self):
        """删除超过用户设定天数的历史记录文件（基于目录日期）"""

        if self.get("Function", "HistoryRetentionTime") == 0:
            logger.info("历史记录永久保留，跳过历史记录清理")
            return

        logger.info("开始清理超过设定天数的历史记录")

        deleted_count = 0

        for date_folder in (Path.cwd() / "history").iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                # 只检查 `YYYY-MM-DD` 格式的文件夹
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d")
                if datetime.now() - folder_date > timedelta(
                    days=self.get("Function", "HistoryRetentionTime")
                ):
                    shutil.rmtree(date_folder, ignore_errors=True)
                    deleted_count += 1
                    logger.info(f"已删除超期日志目录: {date_folder}")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"清理完成: {deleted_count} 个日期目录")


Config = AppConfig()
