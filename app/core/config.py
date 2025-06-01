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

"""
AUTO_MAA
AUTO_MAA配置管理
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import Signal
import sqlite3
import json
import sys
import shutil
import re
import base64
import calendar
from datetime import datetime, timedelta, date
from collections import defaultdict
from pathlib import Path
from qfluentwidgets import (
    QConfig,
    ConfigItem,
    OptionsConfigItem,
    RangeConfigItem,
    ConfigValidator,
    FolderValidator,
    BoolValidator,
    RangeValidator,
    OptionsValidator,
    exceptionHandler,
)
from urllib.parse import urlparse
from typing import Union, Dict, List

from .network import Network


class UrlListValidator(ConfigValidator):
    """Url list validator"""

    def validate(self, value):

        try:
            result = urlparse(value)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def correct(self, value: List[str]):

        urls = []

        for url in [_ for _ in value if _ != ""]:
            if url[-1] != "/":
                urls.append(f"{url}/")
            else:
                urls.append(url)

        return list(set([_ for _ in urls if self.validate(_)]))


class LQConfig(QConfig):
    """局域配置类"""

    def __init__(self) -> None:
        super().__init__()

    def toDict(self, serialize=True):
        """convert config items to `dict`"""
        items = {}
        for name in dir(self._cfg):
            item = getattr(self._cfg, name)
            if not isinstance(item, ConfigItem):
                continue

            value = item.serialize() if serialize else item.value
            if not items.get(item.group):
                if not item.name:
                    items[item.group] = value
                else:
                    items[item.group] = {}

            if item.name:
                items[item.group][item.name] = value

        return items

    @exceptionHandler()
    def load(self, file=None, config=None):
        """load config

        Parameters
        ----------
        file: str or Path
            the path of json config file

        config: Config
            config object to be initialized
        """
        if isinstance(config, QConfig):
            self._cfg = config
            self._cfg.themeChanged.connect(self.themeChanged)

        if isinstance(file, (str, Path)):
            self._cfg.file = Path(file)

        try:
            with open(self._cfg.file, encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            cfg = {}

        # map config items'key to item
        items = {}
        for name in dir(self._cfg):
            item = getattr(self._cfg, name)
            if isinstance(item, ConfigItem):
                items[item.key] = item

        # update the value of config item
        for k, v in cfg.items():
            if not isinstance(v, dict) and items.get(k) is not None:
                items[k].deserializeFrom(v)
            elif isinstance(v, dict):
                for key, value in v.items():
                    key = k + "." + key
                    if items.get(key) is not None:
                        items[key].deserializeFrom(value)

        self.theme = self.get(self._cfg.themeMode)


class GlobalConfig(LQConfig):
    """全局配置"""

    def __init__(self) -> None:
        super().__init__()

        self.function_HomeImageMode = OptionsConfigItem(
            "Function",
            "HomeImageMode",
            "默认",
            OptionsValidator(["默认", "自定义", "主题图像"]),
        )
        self.function_HistoryRetentionTime = OptionsConfigItem(
            "Function",
            "HistoryRetentionTime",
            0,
            OptionsValidator([7, 15, 30, 60, 90, 180, 365, 0]),
        )
        self.function_IfAllowSleep = ConfigItem(
            "Function", "IfAllowSleep", False, BoolValidator()
        )
        self.function_IfSilence = ConfigItem(
            "Function", "IfSilence", False, BoolValidator()
        )
        self.function_BossKey = ConfigItem("Function", "BossKey", "")
        self.function_UnattendedMode = ConfigItem(
            "Function", "UnattendedMode", False, BoolValidator()
        )
        self.function_IfAgreeBilibili = ConfigItem(
            "Function", "IfAgreeBilibili", False, BoolValidator()
        )
        self.function_IfSkipMumuSplashAds = ConfigItem(
            "Function", "IfSkipMumuSplashAds", False, BoolValidator()
        )

        self.voice_Enabled = ConfigItem("Voice", "Enabled", False, BoolValidator())
        self.voice_Type = OptionsConfigItem(
            "Voice", "Type", "simple", OptionsValidator(["simple", "noisy"])
        )

        self.start_IfSelfStart = ConfigItem(
            "Start", "IfSelfStart", False, BoolValidator()
        )
        self.start_IfRunDirectly = ConfigItem(
            "Start", "IfRunDirectly", False, BoolValidator()
        )
        self.start_IfMinimizeDirectly = ConfigItem(
            "Start", "IfMinimizeDirectly", False, BoolValidator()
        )

        self.ui_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
        self.ui_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())
        self.ui_size = ConfigItem("UI", "size", "1200x700")
        self.ui_location = ConfigItem("UI", "location", "100x100")
        self.ui_maximized = ConfigItem("UI", "maximized", False, BoolValidator())

        self.notify_SendTaskResultTime = OptionsConfigItem(
            "Notify",
            "SendTaskResultTime",
            "不推送",
            OptionsValidator(["不推送", "任何时刻", "仅失败时"]),
        )
        self.notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        self.notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
        )
        self.notify_IfPushPlyer = ConfigItem(
            "Notify", "IfPushPlyer", False, BoolValidator()
        )
        self.notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        self.notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
        self.notify_AuthorizationCode = ConfigItem("Notify", "AuthorizationCode", "")
        self.notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
        self.notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        self.notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        self.notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        self.notify_ServerChanChannel = ConfigItem("Notify", "ServerChanChannel", "")
        self.notify_ServerChanTag = ConfigItem("Notify", "ServerChanTag", "")
        self.notify_IfCompanyWebHookBot = ConfigItem(
            "Notify", "IfCompanyWebHookBot", False, BoolValidator()
        )
        self.notify_CompanyWebHookBotUrl = ConfigItem(
            "Notify", "CompanyWebHookBotUrl", ""
        )

        self.update_IfAutoUpdate = ConfigItem(
            "Update", "IfAutoUpdate", False, BoolValidator()
        )
        self.update_UpdateType = OptionsConfigItem(
            "Update", "UpdateType", "stable", OptionsValidator(["stable", "beta"])
        )
        self.update_ThreadNumb = RangeConfigItem(
            "Update", "ThreadNumb", 8, RangeValidator(1, 32)
        )
        self.update_ProxyUrlList = ConfigItem(
            "Update", "ProxyUrlList", [], UrlListValidator()
        )
        self.update_MirrorChyanCDK = ConfigItem("Update", "MirrorChyanCDK", "")


class QueueConfig(LQConfig):
    """队列配置"""

    def __init__(self) -> None:
        super().__init__()

        self.queueSet_Name = ConfigItem("QueueSet", "Name", "")
        self.queueSet_Enabled = ConfigItem(
            "QueueSet", "Enabled", False, BoolValidator()
        )
        self.queueSet_AfterAccomplish = OptionsConfigItem(
            "QueueSet",
            "AfterAccomplish",
            "NoAction",
            OptionsValidator(
                ["NoAction", "KillSelf", "Sleep", "Hibernate", "Shutdown"]
            ),
        )

        self.time_TimeEnabled_0 = ConfigItem(
            "Time", "TimeEnabled_0", False, BoolValidator()
        )
        self.time_TimeSet_0 = ConfigItem("Time", "TimeSet_0", "00:00")

        self.time_TimeEnabled_1 = ConfigItem(
            "Time", "TimeEnabled_1", False, BoolValidator()
        )
        self.time_TimeSet_1 = ConfigItem("Time", "TimeSet_1", "00:00")

        self.time_TimeEnabled_2 = ConfigItem(
            "Time", "TimeEnabled_2", False, BoolValidator()
        )
        self.time_TimeSet_2 = ConfigItem("Time", "TimeSet_2", "00:00")

        self.time_TimeEnabled_3 = ConfigItem(
            "Time", "TimeEnabled_3", False, BoolValidator()
        )
        self.time_TimeSet_3 = ConfigItem("Time", "TimeSet_3", "00:00")

        self.time_TimeEnabled_4 = ConfigItem(
            "Time", "TimeEnabled_4", False, BoolValidator()
        )
        self.time_TimeSet_4 = ConfigItem("Time", "TimeSet_4", "00:00")

        self.time_TimeEnabled_5 = ConfigItem(
            "Time", "TimeEnabled_5", False, BoolValidator()
        )
        self.time_TimeSet_5 = ConfigItem("Time", "TimeSet_5", "00:00")

        self.time_TimeEnabled_6 = ConfigItem(
            "Time", "TimeEnabled_6", False, BoolValidator()
        )
        self.time_TimeSet_6 = ConfigItem("Time", "TimeSet_6", "00:00")

        self.time_TimeEnabled_7 = ConfigItem(
            "Time", "TimeEnabled_7", False, BoolValidator()
        )
        self.time_TimeSet_7 = ConfigItem("Time", "TimeSet_7", "00:00")

        self.time_TimeEnabled_8 = ConfigItem(
            "Time", "TimeEnabled_8", False, BoolValidator()
        )
        self.time_TimeSet_8 = ConfigItem("Time", "TimeSet_8", "00:00")

        self.time_TimeEnabled_9 = ConfigItem(
            "Time", "TimeEnabled_9", False, BoolValidator()
        )
        self.time_TimeSet_9 = ConfigItem("Time", "TimeSet_9", "00:00")

        self.queue_Member_1 = OptionsConfigItem("Queue", "Member_1", "禁用")
        self.queue_Member_2 = OptionsConfigItem("Queue", "Member_2", "禁用")
        self.queue_Member_3 = OptionsConfigItem("Queue", "Member_3", "禁用")
        self.queue_Member_4 = OptionsConfigItem("Queue", "Member_4", "禁用")
        self.queue_Member_5 = OptionsConfigItem("Queue", "Member_5", "禁用")
        self.queue_Member_6 = OptionsConfigItem("Queue", "Member_6", "禁用")
        self.queue_Member_7 = OptionsConfigItem("Queue", "Member_7", "禁用")
        self.queue_Member_8 = OptionsConfigItem("Queue", "Member_8", "禁用")
        self.queue_Member_9 = OptionsConfigItem("Queue", "Member_9", "禁用")
        self.queue_Member_10 = OptionsConfigItem("Queue", "Member_10", "禁用")

        self.Data_LastProxyTime = ConfigItem(
            "Data", "LastProxyTime", "2000-01-01 00:00:00"
        )
        self.Data_LastProxyHistory = ConfigItem(
            "Data", "LastProxyHistory", "暂无历史运行记录"
        )


class MaaConfig(LQConfig):
    """MAA配置"""

    def __init__(self) -> None:
        super().__init__()

        self.MaaSet_Name = ConfigItem("MaaSet", "Name", "")
        self.MaaSet_Path = ConfigItem("MaaSet", "Path", ".", FolderValidator())

        self.RunSet_TaskTransitionMethod = OptionsConfigItem(
            "RunSet",
            "TaskTransitionMethod",
            "ExitEmulator",
            OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
        )
        self.RunSet_ProxyTimesLimit = RangeConfigItem(
            "RunSet", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
        )
        self.RunSet_ADBSearchRange = RangeConfigItem(
            "RunSet", "ADBSearchRange", 0, RangeValidator(0, 3)
        )
        self.RunSet_RunTimesLimit = RangeConfigItem(
            "RunSet", "RunTimesLimit", 3, RangeValidator(1, 1024)
        )
        self.RunSet_AnnihilationTimeLimit = RangeConfigItem(
            "RunSet", "AnnihilationTimeLimit", 40, RangeValidator(1, 1024)
        )
        self.RunSet_RoutineTimeLimit = RangeConfigItem(
            "RunSet", "RoutineTimeLimit", 10, RangeValidator(1, 1024)
        )
        self.RunSet_AnnihilationWeeklyLimit = ConfigItem(
            "RunSet", "AnnihilationWeeklyLimit", False, BoolValidator()
        )
        self.RunSet_AutoUpdateMaa = ConfigItem(
            "RunSet", "AutoUpdateMaa", False, BoolValidator()
        )


class MaaUserConfig(LQConfig):
    """MAA用户配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "新用户")
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Mode = OptionsConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        self.Info_GameIdMode = ConfigItem("Info", "GameIdMode", "固定")
        self.Info_Server = OptionsConfigItem(
            "Info", "Server", "Official", OptionsValidator(["Official", "Bilibili"])
        )
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 1024)
        )
        self.Info_Annihilation = ConfigItem(
            "Info", "Annihilation", False, BoolValidator()
        )
        self.Info_Routine = ConfigItem("Info", "Routine", False, BoolValidator())
        self.Info_InfrastMode = OptionsConfigItem(
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
        self.Info_SeriesNumb = OptionsConfigItem(
            "Info",
            "SeriesNumb",
            "0",
            OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
        )
        self.Info_GameId = ConfigItem("Info", "GameId", "-")
        self.Info_GameId_1 = ConfigItem("Info", "GameId_1", "-")
        self.Info_GameId_2 = ConfigItem("Info", "GameId_2", "-")
        self.Info_GameId_Remain = ConfigItem("Info", "GameId_Remain", "-")

        self.Data_LastProxyDate = ConfigItem("Data", "LastProxyDate", "2000-01-01")
        self.Data_LastAnnihilationDate = ConfigItem(
            "Data", "LastAnnihilationDate", "2000-01-01"
        )
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

    def get_plan_info(self) -> Dict[str, Union[str, int]]:
        """获取当前的计划下信息"""

        if self.get(self.Info_GameIdMode) == "固定":
            return {
                "MedicineNumb": self.get(self.Info_MedicineNumb),
                "SeriesNumb": self.get(self.Info_SeriesNumb),
                "GameId": self.get(self.Info_GameId),
                "GameId_1": self.get(self.Info_GameId_1),
                "GameId_2": self.get(self.Info_GameId_2),
                "GameId_Remain": self.get(self.Info_GameId_Remain),
            }
        elif "计划" in self.get(self.Info_GameIdMode):
            plan = Config.plan_dict[self.get(self.Info_GameIdMode)]["Config"]
            return {
                "MedicineNumb": plan.get(plan.get_current_info("MedicineNumb")),
                "SeriesNumb": plan.get(plan.get_current_info("SeriesNumb")),
                "GameId": plan.get(plan.get_current_info("GameId")),
                "GameId_1": plan.get(plan.get_current_info("GameId_1")),
                "GameId_2": plan.get(plan.get_current_info("GameId_2")),
                "GameId_Remain": plan.get(plan.get_current_info("GameId_Remain")),
            }


class MaaPlanConfig(LQConfig):
    """MAA计划表配置"""

    def __init__(self) -> None:
        super().__init__()

        self.Info_Name = ConfigItem("Info", "Name", "")
        self.Info_Mode = OptionsConfigItem(
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
            self.config_item_dict[group]["SeriesNumb"] = OptionsConfigItem(
                group,
                "SeriesNumb",
                "0",
                OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
            )
            self.config_item_dict[group]["GameId"] = ConfigItem(group, "GameId", "-")
            self.config_item_dict[group]["GameId_1"] = ConfigItem(
                group, "GameId_1", "-"
            )
            self.config_item_dict[group]["GameId_2"] = ConfigItem(
                group, "GameId_2", "-"
            )
            self.config_item_dict[group]["GameId_Remain"] = ConfigItem(
                group, "GameId_Remain", "-"
            )

            for name in [
                "MedicineNumb",
                "SeriesNumb",
                "GameId",
                "GameId_1",
                "GameId_2",
                "GameId_Remain",
            ]:
                setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

    def get_current_info(self, name: str) -> ConfigItem:
        """获取当前的计划表配置项"""

        if self.get(self.Info_Mode) == "ALL":
            return self.config_item_dict["ALL"][name]
        elif self.get(self.Info_Mode) == "Weekly":
            today = datetime.now().strftime("%A")
            if today in self.config_item_dict:
                return self.config_item_dict[today][name]
            else:
                return self.config_item_dict["ALL"][name]


class AppConfig(GlobalConfig):

    VERSION = "4.3.9.0"

    gameid_refreshed = Signal()
    PASSWORD_refreshed = Signal()
    user_info_changed = Signal()
    power_sign_changed = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.app_path = Path(sys.argv[0]).resolve().parent  # 获取软件根目录
        self.app_path_sys = str(Path(sys.argv[0]).resolve())  # 获取软件自身的路径

        self.log_path = self.app_path / "debug/AUTO_MAA.log"
        self.database_path = self.app_path / "data/data.db"
        self.config_path = self.app_path / "config/config.json"
        self.key_path = self.app_path / "data/key"
        self.gameid_path = self.app_path / "data/gameid.txt"
        self.version_path = self.app_path / "resources/version.json"

        self.main_window = None
        self.PASSWORD = ""
        self.running_list = []
        self.silence_list = []
        self.info_bar_list = []
        self.gameid_dict = {
            "ALL": {"value": [], "text": []},
            "Monday": {"value": [], "text": []},
            "Tuesday": {"value": [], "text": []},
            "Wednesday": {"value": [], "text": []},
            "Thursday": {"value": [], "text": []},
            "Friday": {"value": [], "text": []},
            "Saturday": {"value": [], "text": []},
            "Sunday": {"value": [], "text": []},
        }
        self.power_sign = "NoAction"
        self.if_ignore_silence = False
        self.if_database_opened = False

        self.initialize()

    def initialize(self) -> None:
        """初始化程序配置管理模块"""

        # 检查目录
        (self.app_path / "config").mkdir(parents=True, exist_ok=True)
        (self.app_path / "data").mkdir(parents=True, exist_ok=True)
        (self.app_path / "debug").mkdir(parents=True, exist_ok=True)
        (self.app_path / "history").mkdir(parents=True, exist_ok=True)

        self.load(self.config_path, self)
        self.save()

        self.init_logger()
        self.check_data()
        self.get_gameid()
        logger.info("程序初始化完成")

    def init_logger(self) -> None:
        """初始化日志记录器"""

        logger.remove(0)

        logger.add(
            sink=self.log_path,
            level="DEBUG",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            enqueue=True,
            backtrace=True,
            diagnose=True,
            rotation="1 week",
            retention="1 month",
            compression="zip",
        )
        logger.info("===================================")
        logger.info("AUTO_MAA 主程序")
        logger.info(f"版本号： v{self.VERSION}")
        logger.info(f"根目录： {self.app_path}")
        logger.info("===================================")

        logger.info("日志记录器初始化完成")

    def get_gameid(self) -> None:

        # 从MAA服务器获取活动关卡信息
        network = Network.add_task(
            mode="get",
            url="https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivity.json",
        )
        network.loop.exec()
        network_result = Network.get_result(network)
        if network_result["status_code"] == 200:
            gameid_infos: List[Dict[str, Union[str, Dict[str, Union[str, int]]]]] = (
                network_result["response_json"]["Official"]["sideStoryStage"]
            )
        else:
            logger.warning(
                f"无法从MAA服务器获取活动关卡信息:{network_result['error_message']}"
            )
            gameid_infos = []

        ss_gameid_dict = {"value": [], "text": []}

        for gameid_info in gameid_infos:

            if (
                datetime.strptime(
                    gameid_info["Activity"]["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                )
                < datetime.now()
                < datetime.strptime(
                    gameid_info["Activity"]["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                )
            ):
                ss_gameid_dict["value"].append(gameid_info["Value"])
                ss_gameid_dict["text"].append(gameid_info["Value"])

        # 生成每日关卡信息
        gameid_daily_info = [
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

        for day in range(0, 8):

            today_gameid_dict = {"value": [], "text": []}

            for gameid_info in gameid_daily_info:

                if day in gameid_info["days"] or day == 0:
                    today_gameid_dict["value"].append(gameid_info["value"])
                    today_gameid_dict["text"].append(gameid_info["text"])

            self.gameid_dict[calendar.day_name[day - 1] if day > 0 else "ALL"] = {
                "value": today_gameid_dict["value"] + ss_gameid_dict["value"],
                "text": today_gameid_dict["text"] + ss_gameid_dict["text"],
            }

        self.gameid_refreshed.emit()

    def server_date(self) -> date:
        """获取当前的服务器日期"""

        dt = datetime.now()
        if dt.time() < datetime.min.time().replace(hour=4):
            dt = dt - timedelta(days=1)
        return dt.date()

    def check_data(self) -> None:
        """检查用户数据文件并处理数据文件版本更新"""

        # 生成主数据库
        if not self.database_path.exists():
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.5",))
            db.commit()
            cur.close()
            db.close()

        # 数据文件版本更新
        db = sqlite3.connect(self.database_path)
        cur = db.cursor()
        cur.execute("SELECT * FROM version WHERE True")
        version = cur.fetchall()

        if version[0][0] != "v1.5":
            logger.info("数据文件版本更新开始")
            if_streaming = False
            # v1.0-->v1.1
            if version[0][0] == "v1.0" or if_streaming:
                logger.info("数据文件版本更新：v1.0-->v1.1")
                if_streaming = True
                cur.execute("SELECT * FROM adminx WHERE True")
                data = cur.fetchall()
                cur.execute("DROP TABLE IF EXISTS adminx")
                cur.execute(
                    "CREATE TABLE adminx(admin text,id text,server text,day int,status text,last date,game text,game_1 text,game_2 text,routines text,annihilation text,infrastructure text,password byte,notes text,numb int,mode text,uid int)"
                )
                for i in range(len(data)):
                    cur.execute(
                        "INSERT INTO adminx VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            data[i][0],  # 0 0 0
                            data[i][1],  # 1 1 -
                            "Official",  # 2 2 -
                            data[i][2],  # 3 3 1
                            data[i][3],  # 4 4 2
                            data[i][4],  # 5 5 3
                            data[i][5],  # 6 6 -
                            data[i][6],  # 7 7 -
                            data[i][7],  # 8 8 -
                            "y",  # 9 - 4
                            data[i][8],  # 10 9 5
                            data[i][9],  # 11 10 -
                            data[i][10],  # 12 11 6
                            data[i][11],  # 13 12 7
                            data[i][12],  # 14 - -
                            "simple",  # 15 - -
                            data[i][13],  # 16 - -
                        ),
                    )
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.0",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.1",))
                db.commit()
            # v1.1-->v1.2
            if version[0][0] == "v1.1" or if_streaming:
                logger.info("数据文件版本更新：v1.1-->v1.2")
                if_streaming = True
                cur.execute("SELECT * FROM adminx WHERE True")
                data = cur.fetchall()
                for i in range(len(data)):
                    cur.execute(
                        "UPDATE adminx SET infrastructure = 'n' WHERE mode = ? AND uid = ?",
                        (
                            data[i][15],
                            data[i][16],
                        ),
                    )
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.1",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.2",))
                db.commit()
            # v1.2-->v1.3
            if version[0][0] == "v1.2" or if_streaming:
                logger.info("数据文件版本更新：v1.2-->v1.3")
                if_streaming = True
                cur.execute("ALTER TABLE adminx RENAME COLUMN routines TO routine")
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.2",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.3",))
                db.commit()
            # v1.3-->v1.4
            if version[0][0] == "v1.3" or if_streaming:
                logger.info("数据文件版本更新：v1.3-->v1.4")
                if_streaming = True
                (self.app_path / "config/MaaConfig").mkdir(parents=True, exist_ok=True)
                shutil.move(
                    self.app_path / "data/MaaConfig",
                    self.app_path / "config/MaaConfig",
                )
                (self.app_path / "config/MaaConfig/MaaConfig").rename(
                    self.app_path / "config/MaaConfig/脚本_1"
                )
                shutil.copy(
                    self.database_path,
                    self.app_path / "config/MaaConfig/脚本_1/user_data.db",
                )
                cur.execute("DROP TABLE IF EXISTS adminx")
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.3",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.4",))
                db.commit()
                with (self.app_path / "config/gui.json").open(
                    "r", encoding="utf-8"
                ) as f:
                    info = json.load(f)
                maa_config = {
                    "MaaSet": {
                        "Name": "",
                        "Path": info["Default"]["MaaSet.path"],
                    },
                    "RunSet": {
                        "AnnihilationTimeLimit": info["Default"][
                            "TimeLimit.annihilation"
                        ],
                        "RoutineTimeLimit": info["Default"]["TimeLimit.routine"],
                        "RunTimesLimit": info["Default"]["TimesLimit.run"],
                    },
                }
                with (self.app_path / "config/MaaConfig/脚本_1/config.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(maa_config, f, ensure_ascii=False, indent=4)
                config = {
                    "Function": {
                        "BossKey": info["Default"]["SelfSet.BossKey"],
                        "IfAllowSleep": bool(
                            info["Default"]["SelfSet.IfSleep"] == "True"
                        ),
                        "IfSilence": bool(
                            info["Default"]["SelfSet.IfSilence"] == "True"
                        ),
                    },
                    "Notify": {
                        "IfPushPlyer": True,
                        "IfSendErrorOnly": bool(
                            info["Default"]["SelfSet.IfSendMail.OnlyError"] == "True"
                        ),
                        "IfSendMail": bool(
                            info["Default"]["SelfSet.IfSendMail"] == "True"
                        ),
                        "MailAddress": info["Default"]["SelfSet.MailAddress"],
                    },
                    "Start": {
                        "IfRunDirectly": bool(
                            info["Default"]["SelfSet.IfProxyDirectly"] == "True"
                        ),
                        "IfSelfStart": bool(
                            info["Default"]["SelfSet.IfSelfStart"] == "True"
                        ),
                    },
                    "UI": {
                        "IfShowTray": bool(
                            info["Default"]["SelfSet.IfToTray"] == "True"
                        ),
                        "IfToTray": bool(info["Default"]["SelfSet.IfToTray"] == "True"),
                        "location": info["Default"]["SelfSet.UIlocation"],
                        "maximized": bool(
                            info["Default"]["SelfSet.UImaximized"] == "True"
                        ),
                        "size": info["Default"]["SelfSet.UIsize"],
                    },
                    "Update": {"IfAutoUpdate": False},
                }
                with (self.app_path / "config/config.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                queue_config = {
                    "QueueSet": {"Enabled": True, "Name": ""},
                    "Queue": {
                        "Member_1": "脚本_1",
                        "Member_10": "禁用",
                        "Member_2": "禁用",
                        "Member_3": "禁用",
                        "Member_4": "禁用",
                        "Member_5": "禁用",
                        "Member_6": "禁用",
                        "Member_7": "禁用",
                        "Member_8": "禁用",
                        "Member_9": "禁用",
                    },
                    "Time": {
                        "TimeEnabled_0": bool(
                            info["Default"]["TimeSet.set1"] == "True"
                        ),
                        "TimeEnabled_1": bool(
                            info["Default"]["TimeSet.set2"] == "True"
                        ),
                        "TimeEnabled_2": bool(
                            info["Default"]["TimeSet.set3"] == "True"
                        ),
                        "TimeEnabled_3": bool(
                            info["Default"]["TimeSet.set4"] == "True"
                        ),
                        "TimeEnabled_4": bool(
                            info["Default"]["TimeSet.set5"] == "True"
                        ),
                        "TimeEnabled_5": bool(
                            info["Default"]["TimeSet.set6"] == "True"
                        ),
                        "TimeEnabled_6": bool(
                            info["Default"]["TimeSet.set7"] == "True"
                        ),
                        "TimeEnabled_7": bool(
                            info["Default"]["TimeSet.set8"] == "True"
                        ),
                        "TimeEnabled_8": bool(
                            info["Default"]["TimeSet.set9"] == "True"
                        ),
                        "TimeEnabled_9": bool(
                            info["Default"]["TimeSet.set10"] == "True"
                        ),
                        "TimeSet_0": info["Default"]["TimeSet.run1"],
                        "TimeSet_1": info["Default"]["TimeSet.run2"],
                        "TimeSet_2": info["Default"]["TimeSet.run3"],
                        "TimeSet_3": info["Default"]["TimeSet.run4"],
                        "TimeSet_4": info["Default"]["TimeSet.run5"],
                        "TimeSet_5": info["Default"]["TimeSet.run6"],
                        "TimeSet_6": info["Default"]["TimeSet.run7"],
                        "TimeSet_7": info["Default"]["TimeSet.run8"],
                        "TimeSet_8": info["Default"]["TimeSet.run9"],
                        "TimeSet_9": info["Default"]["TimeSet.run10"],
                    },
                }
                (self.app_path / "config/QueueConfig").mkdir(
                    parents=True, exist_ok=True
                )
                with (self.app_path / "config/QueueConfig/调度队列_1.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(queue_config, f, ensure_ascii=False, indent=4)
                (self.app_path / "config/gui.json").unlink()
            # v1.4-->v1.5
            if version[0][0] == "v1.4" or if_streaming:
                logger.info("数据文件版本更新：v1.4-->v1.5")
                if_streaming = True

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.4",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.5",))
                db.commit()

                member_dict: Dict[str, Dict[str, Union[str, Path]]] = {}
                if (self.app_path / "config/MaaConfig").exists():
                    for maa_dir in (self.app_path / "config/MaaConfig").iterdir():
                        if maa_dir.is_dir():
                            member_dict[maa_dir.name] = {
                                "Type": "Maa",
                                "Path": maa_dir,
                            }

                member_dict = dict(
                    sorted(member_dict.items(), key=lambda x: int(x[0][3:]))
                )

                for name, config in member_dict.items():
                    if config["Type"] == "Maa":

                        _db = sqlite3.connect(config["Path"] / "user_data.db")
                        _cur = _db.cursor()
                        _cur.execute("SELECT * FROM adminx WHERE True")
                        data = _cur.fetchall()
                        data = [list(row) for row in data]
                        data = sorted(data, key=lambda x: (-len(x[15]), x[16]))
                        _cur.close()
                        _db.close()

                        (config["Path"] / "user_data.db").unlink()

                        (config["Path"] / f"UserData").mkdir(
                            parents=True, exist_ok=True
                        )

                        for i in range(len(data)):

                            info = {
                                "Data": {
                                    "IfPassCheck": True,
                                    "LastAnnihilationDate": "2000-01-01",
                                    "LastProxyDate": data[i][5],
                                    "ProxyTimes": data[i][14],
                                },
                                "Info": {
                                    "Annihilation": bool(data[i][10] == "y"),
                                    "GameId": data[i][6],
                                    "GameIdMode": "固定",
                                    "GameId_1": data[i][7],
                                    "GameId_2": data[i][8],
                                    "Id": data[i][1],
                                    "Infrastructure": bool(data[i][11] == "y"),
                                    "MedicineNumb": 0,
                                    "Mode": (
                                        "简洁" if data[i][15] == "simple" else "详细"
                                    ),
                                    "Name": data[i][0],
                                    "Notes": data[i][13],
                                    "Password": base64.b64encode(data[i][12]).decode(
                                        "utf-8"
                                    ),
                                    "RemainedDay": data[i][3],
                                    "Routine": bool(data[i][9] == "y"),
                                    "Server": data[i][2],
                                    "Status": bool(data[i][4] == "y"),
                                },
                            }

                            (config["Path"] / f"UserData/用户_{i + 1}").mkdir(
                                parents=True, exist_ok=True
                            )
                            with (
                                config["Path"] / f"UserData/用户_{i + 1}/config.json"
                            ).open(mode="w", encoding="utf-8") as f:
                                json.dump(info, f, ensure_ascii=False, indent=4)

                            if (
                                self.app_path
                                / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/annihilation/gui.json"
                            ).exists():
                                (
                                    config["Path"]
                                    / f"UserData/用户_{i + 1}/Annihilation"
                                ).mkdir(parents=True, exist_ok=True)
                                shutil.move(
                                    self.app_path
                                    / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/annihilation/gui.json",
                                    config["Path"]
                                    / f"UserData/用户_{i + 1}/Annihilation/gui.json",
                                )
                            if (
                                self.app_path
                                / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/routine/gui.json"
                            ).exists():
                                (
                                    config["Path"] / f"UserData/用户_{i + 1}/Routine"
                                ).mkdir(parents=True, exist_ok=True)
                                shutil.move(
                                    self.app_path
                                    / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/routine/gui.json",
                                    config["Path"]
                                    / f"UserData/用户_{i + 1}/Routine/gui.json",
                                )
                            if (
                                self.app_path
                                / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/infrastructure/infrastructure.json"
                            ).exists():
                                (
                                    config["Path"]
                                    / f"UserData/用户_{i + 1}/Infrastructure"
                                ).mkdir(parents=True, exist_ok=True)
                                shutil.move(
                                    self.app_path
                                    / f"config/MaaConfig/{name}/{data[i][15]}/{data[i][16]}/infrastructure/infrastructure.json",
                                    config["Path"]
                                    / f"UserData/用户_{i + 1}/Infrastructure/infrastructure.json",
                                )

                        if (config["Path"] / f"simple").exists():
                            shutil.rmtree(config["Path"] / f"simple")
                        if (config["Path"] / f"beta").exists():
                            shutil.rmtree(config["Path"] / f"beta")

            cur.close()
            db.close()
            logger.info("数据文件版本更新完成")

    def search_member(self) -> None:
        """搜索所有脚本实例"""

        self.member_dict: Dict[
            str,
            Dict[
                str,
                Union[
                    str,
                    Path,
                    MaaConfig,
                    Dict[str, Dict[str, Union[Path, MaaUserConfig]]],
                ],
            ],
        ] = {}
        if (self.app_path / "config/MaaConfig").exists():
            for maa_dir in (self.app_path / "config/MaaConfig").iterdir():
                if maa_dir.is_dir():

                    maa_config = MaaConfig()
                    maa_config.load(maa_dir / "config.json", maa_config)
                    maa_config.save()

                    self.member_dict[maa_dir.name] = {
                        "Type": "Maa",
                        "Path": maa_dir,
                        "Config": maa_config,
                        "UserData": None,
                    }

        self.member_dict = dict(
            sorted(self.member_dict.items(), key=lambda x: int(x[0][3:]))
        )

    def search_maa_user(self, name) -> None:

        user_dict: Dict[str, Dict[str, Union[Path, MaaUserConfig]]] = {}
        for user_dir in (Config.member_dict[name]["Path"] / "UserData").iterdir():
            if user_dir.is_dir():

                user_config = MaaUserConfig()
                user_config.load(user_dir / "config.json", user_config)
                user_config.save()

                user_dict[user_dir.stem] = {
                    "Path": user_dir,
                    "Config": user_config,
                }

        self.member_dict[name]["UserData"] = dict(
            sorted(user_dict.items(), key=lambda x: int(x[0][3:]))
        )

    def search_plan(self) -> None:
        """搜索所有计划表"""

        self.plan_dict: Dict[str, Dict[str, Union[str, Path, MaaPlanConfig]]] = {}
        if (self.app_path / "config/MaaPlanConfig").exists():
            for maa_plan_dir in (self.app_path / "config/MaaPlanConfig").iterdir():
                if maa_plan_dir.is_dir():

                    maa_plan_config = MaaPlanConfig()
                    maa_plan_config.load(maa_plan_dir / "config.json", maa_plan_config)
                    maa_plan_config.save()

                    self.plan_dict[maa_plan_dir.name] = {
                        "Type": "Maa",
                        "Path": maa_plan_dir,
                        "Config": maa_plan_config,
                    }

        self.plan_dict = dict(
            sorted(self.plan_dict.items(), key=lambda x: int(x[0][3:]))
        )

    def search_queue(self):
        """搜索所有调度队列实例"""

        self.queue_dict: Dict[str, Dict[str, Union[Path, QueueConfig]]] = {}

        if (self.app_path / "config/QueueConfig").exists():
            for json_file in (self.app_path / "config/QueueConfig").glob("*.json"):

                queue_config = QueueConfig()
                queue_config.load(json_file, queue_config)
                queue_config.save()

                self.queue_dict[json_file.stem] = {
                    "Path": json_file,
                    "Config": queue_config,
                }

        self.queue_dict = dict(
            sorted(self.queue_dict.items(), key=lambda x: int(x[0][5:]))
        )

    def change_queue(self, old: str, new: str) -> None:
        """修改调度队列配置文件的队列参数"""

        for queue in self.queue_dict.values():

            if queue["Config"].get(queue["Config"].queue_Member_1) == old:
                queue["Config"].set(queue["Config"].queue_Member_1, new)
            if queue["Config"].get(queue["Config"].queue_Member_2) == old:
                queue["Config"].set(queue["Config"].queue_Member_2, new)
            if queue["Config"].get(queue["Config"].queue_Member_3) == old:
                queue["Config"].set(queue["Config"].queue_Member_3, new)
            if queue["Config"].get(queue["Config"].queue_Member_4) == old:
                queue["Config"].set(queue["Config"].queue_Member_4, new)
            if queue["Config"].get(queue["Config"].queue_Member_5) == old:
                queue["Config"].set(queue["Config"].queue_Member_5, new)
            if queue["Config"].get(queue["Config"].queue_Member_6) == old:
                queue["Config"].set(queue["Config"].queue_Member_6, new)
            if queue["Config"].get(queue["Config"].queue_Member_7) == old:
                queue["Config"].set(queue["Config"].queue_Member_7, new)
            if queue["Config"].get(queue["Config"].queue_Member_8) == old:
                queue["Config"].set(queue["Config"].queue_Member_8, new)
            if queue["Config"].get(queue["Config"].queue_Member_9) == old:
                queue["Config"].set(queue["Config"].queue_Member_9, new)
            if queue["Config"].get(queue["Config"].queue_Member_10) == old:
                queue["Config"].set(queue["Config"].queue_Member_10, new)

    def change_plan(self, old: str, new: str) -> None:
        """修改脚本管理所有下属用户的计划表配置参数"""

        for member in self.member_dict.values():

            for user in member["UserData"].values():

                if user["Config"].get(user["Config"].Info_GameIdMode) == old:
                    user["Config"].set(user["Config"].Info_GameIdMode, new)

    def change_user_info(
        self, name: str, user_data: Dict[str, Dict[str, Union[str, Path, dict]]]
    ) -> None:
        """代理完成后保存改动的用户信息"""

        for user, info in user_data.items():

            user_config = self.member_dict[name]["UserData"][user]["Config"]

            user_config.set(
                user_config.Info_RemainedDay, info["Config"]["Info"]["RemainedDay"]
            )
            user_config.set(
                user_config.Data_LastProxyDate, info["Config"]["Data"]["LastProxyDate"]
            )
            user_config.set(
                user_config.Data_LastAnnihilationDate,
                info["Config"]["Data"]["LastAnnihilationDate"],
            )
            user_config.set(
                user_config.Data_ProxyTimes, info["Config"]["Data"]["ProxyTimes"]
            )
            user_config.set(
                user_config.Data_IfPassCheck, info["Config"]["Data"]["IfPassCheck"]
            )
            user_config.set(
                user_config.Data_CustomInfrastPlanIndex,
                info["Config"]["Data"]["CustomInfrastPlanIndex"],
            )

        self.user_info_changed.emit()

    def set_power_sign(self, sign: str) -> None:
        """设置当前电源状态"""

        self.power_sign = sign
        self.power_sign_changed.emit()

    def save_history(self, key: str, content: dict) -> None:
        """保存历史记录"""

        if key in self.queue_dict:
            self.queue_dict[key]["Config"].set(
                self.queue_dict[key]["Config"].Data_LastProxyTime, content["Time"]
            )
            self.queue_dict[key]["Config"].set(
                self.queue_dict[key]["Config"].Data_LastProxyHistory, content["History"]
            )
        else:
            logger.warning(f"保存历史记录时未找到调度队列: {key}")

    def save_maa_log(self, log_path: Path, logs: list, maa_result: str) -> bool:
        """保存MAA日志并生成初步统计数据"""

        data: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = {
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
            if "开始任务: Fight" in line:
                # 查找对应的任务结束位置
                end_index = -1
                for j in range(i + 1, len(logs)):
                    if "完成任务: Fight" in logs[j]:
                        end_index = j
                        break
                    # 如果遇到新的Fight任务开始，则当前任务没有正常结束
                    if j < len(logs) and "开始任务: Fight" in logs[j]:
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

        logger.info(f"处理完成：{log_path}")

        self.merge_maa_logs("所有项", log_path.parent)

        return if_six_star

    def merge_maa_logs(self, mode: str, logs_path: Union[Path, List[Path]]) -> dict:
        """合并指定数据统计信息文件"""

        data = {
            "recruit_statistics": defaultdict(int),
            "drop_statistics": defaultdict(dict),
            "maa_result": defaultdict(str),
        }

        if mode == "所有项":
            logs_path_list = list(logs_path.glob("*.json"))
        elif mode == "指定项":
            logs_path_list = logs_path

        for json_file in logs_path_list:

            with json_file.open("r", encoding="utf-8") as f:
                single_data: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = (
                    json.load(f)
                )

            # 合并公招统计
            for star_level, count in single_data["recruit_statistics"].items():
                data["recruit_statistics"][star_level] += count

            # 合并掉落统计
            for stage, drops in single_data["drop_statistics"].items():
                if stage not in data["drop_statistics"]:
                    data["drop_statistics"][stage] = {}  # 初始化关卡

                for item, count in drops.items():

                    if item in data["drop_statistics"][stage]:
                        data["drop_statistics"][stage][item] += count
                    else:
                        data["drop_statistics"][stage][item] = count

            # 合并MAA结果
            data["maa_result"][json_file.stem.replace("-", ":")] = single_data[
                "maa_result"
            ]

        # 生成汇总 JSON 文件
        if mode == "所有项":

            with logs_path.with_suffix(".json").open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            logger.info(f"统计完成：{logs_path.with_suffix('.json')}")

        return data

    def load_maa_logs(
        self, mode: str, json_path: Path
    ) -> Dict[str, Union[str, list, Dict[str, list]]]:
        """加载MAA日志统计信息"""

        if mode == "总览":

            with json_path.open("r", encoding="utf-8") as f:
                info: Dict[str, Dict[str, Union[int, dict]]] = json.load(f)

            data = {}
            # 4点前的记录放在当日最后
            sorted_maa_result = sorted(
                info["maa_result"].items(),
                key=lambda x: (
                    (
                        1
                        if datetime.strptime(x[0], "%H:%M:%S").time()
                        < datetime.min.time().replace(hour=4)
                        else 0
                    ),
                    datetime.strptime(x[0], "%H:%M:%S"),
                ),
            )
            data["条目索引"] = [
                [k, "完成" if v == "Success!" else "异常"] for k, v in sorted_maa_result
            ]
            data["条目索引"].insert(0, ["数据总览", "运行"])
            data["统计数据"] = {"公招统计": list(info["recruit_statistics"].items())}

            for game_id, drops in info["drop_statistics"].items():
                data["统计数据"][f"掉落统计：{game_id}"] = list(drops.items())

            data["统计数据"]["报错汇总"] = [
                [k, v] for k, v in info["maa_result"].items() if v != "Success!"
            ]

        elif mode == "单项":

            with json_path.open("r", encoding="utf-8") as f:
                info: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = json.load(f)

            data = {}

            data["统计数据"] = {"公招统计": list(info["recruit_statistics"].items())}

            for game_id, drops in info["drop_statistics"].items():
                data["统计数据"][f"掉落统计：{game_id}"] = list(drops.items())

            with json_path.with_suffix(".log").open("r", encoding="utf-8") as f:
                log = f.read()

            data["日志信息"] = log

        return data

    def search_history(
        self, mode: str, start_date: datetime, end_date: datetime
    ) -> dict:
        """搜索所有历史记录"""

        history_dict = {}

        for date_folder in (Config.app_path / "history").iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:

                date = datetime.strptime(date_folder.name, "%Y-%m-%d")

                if not (start_date <= date <= end_date):
                    continue  # 只统计在范围内的日期

                if mode == "按日合并":

                    history_dict[date.strftime("%Y年 %m月 %d日")] = list(
                        date_folder.glob("*.json")
                    )

                elif mode == "按周合并":

                    year, week, _ = date.isocalendar()
                    if f"{year}年 第{week}周" not in history_dict:
                        history_dict[f"{year}年 第{week}周"] = {}

                    for user in date_folder.glob("*.json"):

                        if user.stem not in history_dict[f"{year}年 第{week}周"]:
                            history_dict[f"{year}年 第{week}周"][user.stem] = list(
                                user.with_suffix("").glob("*.json")
                            )
                        else:
                            history_dict[f"{year}年 第{week}周"][user.stem] += list(
                                user.with_suffix("").glob("*.json")
                            )

                elif mode == "按月合并":

                    if date.strftime("%Y年 %m月") not in history_dict:
                        history_dict[date.strftime("%Y年 %m月")] = {}

                    for user in date_folder.glob("*.json"):

                        if user.stem not in history_dict[date.strftime("%Y年 %m月")]:
                            history_dict[date.strftime("%Y年 %m月")][user.stem] = list(
                                user.with_suffix("").glob("*.json")
                            )
                        else:
                            history_dict[date.strftime("%Y年 %m月")][user.stem] += list(
                                user.with_suffix("").glob("*.json")
                            )

            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        return {
            k: v
            for k, v in sorted(history_dict.items(), key=lambda x: x[0], reverse=True)
        }


Config = AppConfig()
