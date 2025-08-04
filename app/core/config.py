#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

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


import argparse
import sqlite3
import json
import sys
import shutil
import re
import base64
import calendar
from datetime import datetime, timedelta, date
from pathlib import Path


from typing import Union, Dict, List, Literal, Optional, Any, Tuple, Callable, TypeVar

from utils import get_logger
from models.ConfigBase import *


class GlobalConfig(ConfigBase):
    """全局配置"""

    Function_HomeImageMode = ConfigItem(
        "Function",
        "HomeImageMode",
        "默认",
        OptionsValidator(["默认", "自定义", "主题图像"]),
    )
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
    Function_UnattendedMode = ConfigItem(
        "Function", "UnattendedMode", False, BoolValidator()
    )
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
    Notify_AuthorizationCode = ConfigItem("Notify", "AuthorizationCode", "")
    Notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
    Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
    Notify_IfServerChan = ConfigItem("Notify", "IfServerChan", False, BoolValidator())
    Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
    Notify_ServerChanChannel = ConfigItem("Notify", "ServerChanChannel", "")
    Notify_ServerChanTag = ConfigItem("Notify", "ServerChanTag", "")
    Notify_IfCompanyWebHookBot = ConfigItem(
        "Notify", "IfCompanyWebHookBot", False, BoolValidator()
    )
    Notify_CompanyWebHookBotUrl = ConfigItem("Notify", "CompanyWebHookBotUrl", "")

    Update_IfAutoUpdate = ConfigItem("Update", "IfAutoUpdate", False, BoolValidator())
    Update_UpdateType = ConfigItem(
        "Update", "UpdateType", "stable", OptionsValidator(["stable", "beta"])
    )
    Update_ThreadNumb = ConfigItem("Update", "ThreadNumb", 8, RangeValidator(1, 32))
    Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
    Update_ProxyUrlList = ConfigItem("Update", "ProxyUrlList", [])
    Update_MirrorChyanCDK = ConfigItem("Update", "MirrorChyanCDK", "")


class QueueItem(ConfigBase):
    """队列项配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_ScriptId = ConfigItem("Info", "ScriptId", "", UidValidator())


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
        self.Info_Time = ConfigItem("Info", "Set", "00:00")


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "")
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
        self.Info_Password = ConfigItem("Info", "Password", "")
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
        self.Notify_ServerChanChannel = ConfigItem("Notify", "ServerChanChannel", "")
        self.Notify_ServerChanTag = ConfigItem("Notify", "ServerChanTag", "")
        self.Notify_IfCompanyWebHookBot = ConfigItem(
            "Notify", "IfCompanyWebHookBot", False, BoolValidator()
        )
        self.Notify_CompanyWebHookBotUrl = ConfigItem(
            "Notify", "CompanyWebHookBotUrl", ""
        )

    # def get_plan_info(self) -> Dict[str, Union[str, int]]:
    #     """获取当前的计划下信息"""

    #     if self.get(self.Info_StageMode) == "固定":
    #         return {
    #             "MedicineNumb": self.get(self.Info_MedicineNumb),
    #             "SeriesNumb": self.get(self.Info_SeriesNumb),
    #             "Stage": self.get(self.Info_Stage),
    #             "Stage_1": self.get(self.Info_Stage_1),
    #             "Stage_2": self.get(self.Info_Stage_2),
    #             "Stage_3": self.get(self.Info_Stage_3),
    #             "Stage_Remain": self.get(self.Info_Stage_Remain),
    #         }
    #     elif "计划" in self.get(self.Info_StageMode):
    #         plan = Config.plan_dict[self.get(self.Info_StageMode)]["Config"]
    #         return {
    #             "MedicineNumb": plan.get(plan.get_current_info("MedicineNumb")),
    #             "SeriesNumb": plan.get(plan.get_current_info("SeriesNumb")),
    #             "Stage": plan.get(plan.get_current_info("Stage")),
    #             "Stage_1": plan.get(plan.get_current_info("Stage_1")),
    #             "Stage_2": plan.get(plan.get_current_info("Stage_2")),
    #             "Stage_3": plan.get(plan.get_current_info("Stage_3")),
    #             "Stage_Remain": plan.get(plan.get_current_info("Stage_Remain")),
    #         }


class MaaConfig(ConfigBase):
    """MAA配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "")
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

        self.Info_Name = ConfigItem("Info", "Name", "")
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

    # def get_current_info(self, name: str) -> ConfigItem:
    #     """获取当前的计划表配置项"""

    #     if self.get(self.Info_Mode) == "ALL":

    #         return self.config_item_dict["ALL"][name]

    #     elif self.get(self.Info_Mode) == "Weekly":

    #         dt = datetime.now()
    #         if dt.time() < datetime.min.time().replace(hour=4):
    #             dt = dt - timedelta(days=1)
    #         today = dt.strftime("%A")

    #         if today in self.config_item_dict:
    #             return self.config_item_dict[today][name]
    #         else:
    #             return self.config_item_dict["ALL"][name]


class GeneralUserConfig(ConfigBase):
    """通用子配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新配置")
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
        self.Notify_ServerChanChannel = ConfigItem("Notify", "ServerChanChannel", "")
        self.Notify_ServerChanTag = ConfigItem("Notify", "ServerChanTag", "")
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

        self.Info_Name = ConfigItem("Info", "Name", "")
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


class AppConfig(GlobalConfig):

    VERSION = "4.5.0.1"

    def __init__(self) -> None:
        super().__init__(if_save_multi_config=False)

        self.root_path = Path.cwd()

        self.log_path = self.root_path / "debug/app.log"
        # self.database_path = self.root_path / "data/data.db"
        self.config_path = self.root_path / "config"
        # self.key_path = self.root_path / "data/key"

        # self.main_window = None
        # self.PASSWORD = ""
        # self.running_list = []
        # self.silence_dict: Dict[Path, datetime] = {}
        # self.info_bar_list = []
        # self.stage_dict = {
        #     "ALL": {"value": [], "text": []},
        #     "Monday": {"value": [], "text": []},
        #     "Tuesday": {"value": [], "text": []},
        #     "Wednesday": {"value": [], "text": []},
        #     "Thursday": {"value": [], "text": []},
        #     "Friday": {"value": [], "text": []},
        #     "Saturday": {"value": [], "text": []},
        #     "Sunday": {"value": [], "text": []},
        # }
        # self.power_sign = "NoAction"
        # self.if_ignore_silence = False
        # self.if_database_opened = False

        self.logger = get_logger("配置管理")
        self.logger.info("")
        self.logger.info("===================================")
        self.logger.info("AUTO_MAA 后端应用程序")
        self.logger.info(f"版本号： v{self.VERSION}")
        self.logger.info(f"根目录： {self.root_path}")
        self.logger.info("===================================")

        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

        self.ScriptConfig = MultipleConfig([MaaConfig, GeneralConfig])
        self.PlanConfig = MultipleConfig([MaaPlanConfig])
        self.QueueConfig = MultipleConfig([QueueConfig])

    async def init_config(self) -> None:
        """初始化配置管理"""
        await self.connect(self.config_path / "Config.json")
        await self.ScriptConfig.connect(self.config_path / "ScriptConfig.json")
        await self.PlanConfig.connect(self.config_path / "PlanConfig.json")
        await self.QueueConfig.connect(self.config_path / "QueueConfig.json")

        # self.check_data()
        self.logger.info("程序初始化完成")

    async def add_script(
        self, script: Literal["MAA", "General"]
    ) -> tuple[uuid.UUID, ConfigBase]:
        """添加脚本配置"""

        self.logger.info(f"添加脚本配置：{script}")

        class_book = {"MAA": MaaConfig, "General": GeneralConfig}

        return await self.ScriptConfig.add(class_book[script])

    async def get_script(self, script_id: Optional[str]) -> tuple[list, dict]:
        """获取脚本配置"""

        self.logger.info(f"获取脚本配置：{script_id}")

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

        self.logger.info(f"更新脚本配置：{script_id}")

        uid = uuid.UUID(script_id)

        for group, items in data.items():
            for name, value in items.items():
                self.logger.debug(
                    f"更新脚本配置：{script_id} - {group}.{name} = {value}"
                )
                await self.ScriptConfig[uid].set(group, name, value)

        await self.ScriptConfig.save()

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        self.logger.info(f"删除脚本配置：{script_id}")

        await self.ScriptConfig.remove(uuid.UUID(script_id))

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        self.logger.info(f"重新排序脚本：{index_list}")

        await self.ScriptConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def add_user(self, script_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加用户配置"""

        self.logger.info(f"{script_id} 添加用户配置")

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

        self.logger.info(f"{script_id} 更新用户配置：{user_id}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        uid = uuid.UUID(user_id)

        for group, items in data.items():
            for name, value in items.items():
                self.logger.debug(
                    f"更新脚本配置：{script_id} - {group}.{name} = {value}"
                )
                if isinstance(script_config, (MaaConfig | GeneralConfig)):
                    await script_config.UserData[uid].set(group, name, value)

        await self.ScriptConfig.save()

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        self.logger.info(f"{script_id} 删除用户配置：{user_id}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        uid = uuid.UUID(user_id)

        if isinstance(script_config, (MaaConfig | GeneralConfig)):
            await script_config.UserData.remove(uid)
            await self.ScriptConfig.save()

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        self.logger.info(f"{script_id} 重新排序用户：{index_list}")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        if isinstance(script_config, (MaaConfig | GeneralConfig)):
            await script_config.UserData.setOrder([uuid.UUID(_) for _ in index_list])
            await self.ScriptConfig.save()

    async def add_queue(self) -> tuple[uuid.UUID, ConfigBase]:
        """添加调度队列"""

        self.logger.info("添加调度队列")

        return await self.QueueConfig.add(QueueConfig)

    async def get_queue(self, queue_id: Optional[str]) -> tuple[list, dict]:
        """获取调度队列配置"""

        self.logger.info(f"获取调度队列配置：{queue_id}")

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

        self.logger.info(f"更新调度队列配置：{queue_id}")

        uid = uuid.UUID(queue_id)

        for group, items in data.items():
            for name, value in items.items():
                self.logger.debug(
                    f"更新调度队列配置：{queue_id} - {group}.{name} = {value}"
                )
                await self.QueueConfig[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        self.logger.info(f"删除调度队列配置：{queue_id}")

        await self.QueueConfig.remove(uuid.UUID(queue_id))

    async def reorder_queue(self, index_list: list[str]) -> None:
        """重新排序调度队列"""

        self.logger.info(f"重新排序调度队列：{index_list}")

        await self.QueueConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def add_time_set(self, queue_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加时间设置配置"""

        self.logger.info(f"{queue_id} 添加时间设置配置")

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

        self.logger.info(f"{queue_id} 更新时间设置配置：{time_set_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(time_set_id)

        for group, items in data.items():
            for name, value in items.items():
                self.logger.debug(
                    f"更新时间设置配置：{queue_id} - {group}.{name} = {value}"
                )
                if isinstance(queue_config, QueueConfig):
                    await queue_config.TimeSet[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        self.logger.info(f"{queue_id} 删除时间设置配置：{time_set_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(time_set_id)

        if isinstance(queue_config, QueueConfig):
            await queue_config.TimeSet.remove(uid)
            await self.QueueConfig.save()

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        self.logger.info(f"{queue_id} 重新排序时间设置：{index_list}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            await queue_config.TimeSet.setOrder([uuid.UUID(_) for _ in index_list])
            await self.QueueConfig.save()

    async def add_queue_item(self, queue_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加队列项配置"""

        self.logger.info(f"{queue_id} 添加队列项配置")

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

        self.logger.info(f"{queue_id} 更新队列项配置：{queue_item_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(queue_item_id)

        for group, items in data.items():
            for name, value in items.items():
                if uuid.UUID(value) not in self.ScriptConfig:
                    raise ValueError(f"Script with uid {value} does not exist.")
                self.logger.debug(
                    f"更新队列项配置：{queue_id} - {group}.{name} = {value}"
                )
                if isinstance(queue_config, QueueConfig):
                    await queue_config.QueueItem[uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        self.logger.info(f"{queue_id} 删除队列项配置：{queue_item_id}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]
        uid = uuid.UUID(queue_item_id)

        if isinstance(queue_config, QueueConfig):
            await queue_config.QueueItem.remove(uid)
            await self.QueueConfig.save()

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        self.logger.info(f"{queue_id} 重新排序队列项：{index_list}")

        queue_config = self.QueueConfig[uuid.UUID(queue_id)]

        if isinstance(queue_config, QueueConfig):
            await queue_config.QueueItem.setOrder([uuid.UUID(_) for _ in index_list])
            await self.QueueConfig.save()

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        self.logger.info("获取全局设置")

        return await self.toDict(ignore_multi_config=True)

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        self.logger.info(f"更新全局设置")

        for group, items in data.items():
            for name, value in items.items():
                self.logger.debug(f"更新全局设置 - {group}.{name} = {value}")
                await self.set(group, name, value)

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


Config = AppConfig()
