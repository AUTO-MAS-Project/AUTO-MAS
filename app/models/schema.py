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


from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal


class OutBase(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class InfoOut(OutBase):
    data: Dict[str, Any] = Field(..., description="收到的服务器数据")


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")


class ComboBoxOut(OutBase):
    data: List[ComboBoxItem] = Field(..., description="下拉框选项")


class GetStageIn(BaseModel):
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
    ] = Field(
        ...,
        description="选择的日期类型, Today为当天, ALL为包含当天未开放关卡在内的所有项",
    )


class GlobalConfig_Function(BaseModel):
    HistoryRetentionTime: Optional[Literal[7, 15, 30, 60, 90, 180, 365, 0]] = Field(
        None, description="历史记录保留时间, 0表示永久保存"
    )
    IfAllowSleep: Optional[bool] = Field(None, description="允许休眠")
    IfSilence: Optional[bool] = Field(None, description="静默模式")
    BossKey: Optional[str] = Field(None, description="模拟器老板键")
    IfAgreeBilibili: Optional[bool] = Field(None, description="同意哔哩哔哩用户协议")
    IfSkipMumuSplashAds: Optional[bool] = Field(
        None, description="跳过Mumu模拟器启动广告"
    )


class GlobalConfig_Voice(BaseModel):
    Enabled: Optional[bool] = Field(None, description="语音功能是否启用")
    Type: Optional[Literal["simple", "noisy"]] = Field(
        None, description="语音类型, simple为简洁, noisy为聒噪"
    )


class GlobalConfig_Start(BaseModel):
    IfSelfStart: Optional[bool] = Field(None, description="是否在系统启动时自动运行")
    IfMinimizeDirectly: Optional[bool] = Field(
        None, description="启动时是否直接最小化到托盘而不显示主窗口"
    )


class GlobalConfig_UI(BaseModel):
    IfShowTray: Optional[bool] = Field(None, description="是否常态显示托盘图标")
    IfToTray: Optional[bool] = Field(None, description="是否最小化到托盘")


class GlobalConfig_Notify(BaseModel):
    SendTaskResultTime: Optional[Literal["不推送", "任何时刻", "仅失败时"]] = Field(
        None, description="任务结果推送时机"
    )
    IfSendStatistic: Optional[bool] = Field(None, description="是否发送统计信息")
    IfSendSixStar: Optional[bool] = Field(None, description="是否发送公招六星通知")
    IfPushPlyer: Optional[bool] = Field(None, description="是否推送系统通知")
    IfSendMail: Optional[bool] = Field(None, description="是否发送邮件通知")
    SMTPServerAddress: Optional[str] = Field(None, description="SMTP服务器地址")
    AuthorizationCode: Optional[str] = Field(None, description="SMTP授权码")
    FromAddress: Optional[str] = Field(None, description="邮件发送地址")
    ToAddress: Optional[str] = Field(None, description="邮件接收地址")
    IfServerChan: Optional[bool] = Field(None, description="是否使用ServerChan推送")
    ServerChanKey: Optional[str] = Field(None, description="ServerChan推送密钥")
    IfCompanyWebHookBot: Optional[bool] = Field(
        None, description="是否使用企微Webhook推送"
    )
    CompanyWebHookBotUrl: Optional[str] = Field(None, description="企微Webhook Bot URL")


class GlobalConfig_Update(BaseModel):
    IfAutoUpdate: Optional[bool] = Field(None, description="是否自动更新")
    UpdateType: Optional[Literal["stable", "beta"]] = Field(
        None, description="更新类型, stable为稳定版, beta为测试版"
    )
    Source: Optional[Literal["GitHub", "MirrorChyan", "AutoSite"]] = Field(
        None, description="更新源: GitHub源, Mirror酱源, 自建源"
    )
    ProxyAddress: Optional[str] = Field(None, description="网络代理地址")
    MirrorChyanCDK: Optional[str] = Field(None, description="Mirror酱CDK")


class GlobalConfig(BaseModel):
    Function: Optional[GlobalConfig_Function] = Field(None, description="功能相关配置")
    Voice: Optional[GlobalConfig_Voice] = Field(None, description="语音相关配置")
    Start: Optional[GlobalConfig_Start] = Field(None, description="启动相关配置")
    UI: Optional[GlobalConfig_UI] = Field(None, description="界面相关配置")
    Notify: Optional[GlobalConfig_Notify] = Field(None, description="通知相关配置")
    Update: Optional[GlobalConfig_Update] = Field(None, description="更新相关配置")


# class QueueItem(ConfigBase):
#     """队列项配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_ScriptId = ConfigItem("Info", "ScriptId", None, UidValidator())


# class TimeSet(ConfigBase):
#     """时间设置配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
#         self.Info_Time = ConfigItem("Info", "Time", "00:00")


# class QueueConfig(ConfigBase):
#     """队列配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "")
#         self.Info_TimeEnabled = ConfigItem(
#             "Info", "TimeEnabled", False, BoolValidator()
#         )
#         self.Info_StartUpEnabled = ConfigItem(
#             "Info", "StartUpEnabled", False, BoolValidator()
#         )
#         self.Info_AfterAccomplish = ConfigItem(
#             "Info",
#             "AfterAccomplish",
#             "NoAction",
#             OptionsValidator(
#                 [
#                     "NoAction",
#                     "KillSelf",
#                     "Sleep",
#                     "Hibernate",
#                     "Shutdown",
#                     "ShutdownForce",
#                 ]
#             ),
#         )

#         self.Data_LastProxyTime = ConfigItem(
#             "Data", "LastProxyTime", "2000-01-01 00:00:00"
#         )
#         self.Data_LastProxyHistory = ConfigItem(
#             "Data", "LastProxyHistory", "暂无历史运行记录"
#         )

#         self.TimeSet = MultipleConfig([TimeSet])
#         self.QueueItem = MultipleConfig([QueueItem])


# class MaaUserConfig(ConfigBase):
#     """MAA用户配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "新用户")
#         self.Info_Id = ConfigItem("Info", "Id", "")
#         self.Info_Mode = ConfigItem(
#             "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
#         )
#         self.Info_StageMode = ConfigItem("Info", "StageMode", "固定")
#         self.Info_Server = ConfigItem(
#             "Info",
#             "Server",
#             "Official",
#             OptionsValidator(
#                 ["Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"]
#             ),
#         )
#         self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
#         self.Info_RemainedDay = ConfigItem(
#             "Info", "RemainedDay", -1, RangeValidator(-1, 1024)
#         )
#         self.Info_Annihilation = ConfigItem(
#             "Info",
#             "Annihilation",
#             "Annihilation",
#             OptionsValidator(
#                 [
#                     "Close",
#                     "Annihilation",
#                     "Chernobog@Annihilation",
#                     "LungmenOutskirts@Annihilation",
#                     "LungmenDowntown@Annihilation",
#                 ]
#             ),
#         )
#         self.Info_Routine = ConfigItem("Info", "Routine", True, BoolValidator())
#         self.Info_InfrastMode = ConfigItem(
#             "Info",
#             "InfrastMode",
#             "Normal",
#             OptionsValidator(["Normal", "Rotation", "Custom"]),
#         )
#         self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
#         self.Info_Notes = ConfigItem("Info", "Notes", "无")
#         self.Info_MedicineNumb = ConfigItem(
#             "Info", "MedicineNumb", 0, RangeValidator(0, 1024)
#         )
#         self.Info_SeriesNumb = ConfigItem(
#             "Info",
#             "SeriesNumb",
#             "0",
#             OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
#         )
#         self.Info_Stage = ConfigItem("Info", "Stage", "-")
#         self.Info_Stage_1 = ConfigItem("Info", "Stage_1", "-")
#         self.Info_Stage_2 = ConfigItem("Info", "Stage_2", "-")
#         self.Info_Stage_3 = ConfigItem("Info", "Stage_3", "-")
#         self.Info_Stage_Remain = ConfigItem("Info", "Stage_Remain", "-")
#         self.Info_IfSkland = ConfigItem("Info", "IfSkland", False, BoolValidator())
#         self.Info_SklandToken = ConfigItem("Info", "SklandToken", "")

#         self.Data_LastProxyDate = ConfigItem("Data", "LastProxyDate", "2000-01-01")
#         self.Data_LastAnnihilationDate = ConfigItem(
#             "Data", "LastAnnihilationDate", "2000-01-01"
#         )
#         self.Data_LastSklandDate = ConfigItem("Data", "LastSklandDate", "2000-01-01")
#         self.Data_ProxyTimes = ConfigItem(
#             "Data", "ProxyTimes", 0, RangeValidator(0, 1024)
#         )
#         self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())
#         self.Data_CustomInfrastPlanIndex = ConfigItem(
#             "Data", "CustomInfrastPlanIndex", "0"
#         )

#         self.Task_IfWakeUp = ConfigItem("Task", "IfWakeUp", True, BoolValidator())
#         self.Task_IfRecruiting = ConfigItem(
#             "Task", "IfRecruiting", True, BoolValidator()
#         )
#         self.Task_IfBase = ConfigItem("Task", "IfBase", True, BoolValidator())
#         self.Task_IfCombat = ConfigItem("Task", "IfCombat", True, BoolValidator())
#         self.Task_IfMall = ConfigItem("Task", "IfMall", True, BoolValidator())
#         self.Task_IfMission = ConfigItem("Task", "IfMission", True, BoolValidator())
#         self.Task_IfAutoRoguelike = ConfigItem(
#             "Task", "IfAutoRoguelike", False, BoolValidator()
#         )
#         self.Task_IfReclamation = ConfigItem(
#             "Task", "IfReclamation", False, BoolValidator()
#         )

#         self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
#         self.Notify_IfSendStatistic = ConfigItem(
#             "Notify", "IfSendStatistic", False, BoolValidator()
#         )
#         self.Notify_IfSendSixStar = ConfigItem(
#             "Notify", "IfSendSixStar", False, BoolValidator()
#         )
#         self.Notify_IfSendMail = ConfigItem(
#             "Notify", "IfSendMail", False, BoolValidator()
#         )
#         self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
#         self.Notify_IfServerChan = ConfigItem(
#             "Notify", "IfServerChan", False, BoolValidator()
#         )
#         self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
#         self.Notify_IfCompanyWebHookBot = ConfigItem(
#             "Notify", "IfCompanyWebHookBot", False, BoolValidator()
#         )
#         self.Notify_CompanyWebHookBotUrl = ConfigItem(
#             "Notify", "CompanyWebHookBotUrl", ""
#         )

#     def get_plan_info(self) -> Dict[str, Union[str, int]]:
#         """获取当前的计划下信息"""

#         if self.get("Info", "StageMode") == "固定":
#             return {
#                 "MedicineNumb": self.get("Info", "MedicineNumb"),
#                 "SeriesNumb": self.get("Info", "SeriesNumb"),
#                 "Stage": self.get("Info", "Stage"),
#                 "Stage_1": self.get("Info", "Stage_1"),
#                 "Stage_2": self.get("Info", "Stage_2"),
#                 "Stage_3": self.get("Info", "Stage_3"),
#                 "Stage_Remain": self.get("Info", "Stage_Remain"),
#             }
#         else:
#             plan = Config.PlanConfig[uuid.UUID(self.get("Info", "StageMode"))]
#             if isinstance(plan, MaaPlanConfig):
#                 return {
#                     "MedicineNumb": plan.get_current_info("MedicineNumb").getValue(),
#                     "SeriesNumb": plan.get_current_info("SeriesNumb").getValue(),
#                     "Stage": plan.get_current_info("Stage").getValue(),
#                     "Stage_1": plan.get_current_info("Stage_1").getValue(),
#                     "Stage_2": plan.get_current_info("Stage_2").getValue(),
#                     "Stage_3": plan.get_current_info("Stage_3").getValue(),
#                     "Stage_Remain": plan.get_current_info("Stage_Remain").getValue(),
#                 }
#             else:
#                 raise ValueError("Invalid plan type")


# class MaaConfig(ConfigBase):
#     """MAA配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "")
#         self.Info_Path = ConfigItem("Info", "Path", ".", FolderValidator())

#         self.Run_TaskTransitionMethod = ConfigItem(
#             "Run",
#             "TaskTransitionMethod",
#             "ExitEmulator",
#             OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
#         )
#         self.Run_ProxyTimesLimit = ConfigItem(
#             "Run", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
#         )
#         self.Run_ADBSearchRange = ConfigItem(
#             "Run", "ADBSearchRange", 0, RangeValidator(0, 3)
#         )
#         self.Run_RunTimesLimit = ConfigItem(
#             "Run", "RunTimesLimit", 3, RangeValidator(1, 1024)
#         )
#         self.Run_AnnihilationTimeLimit = ConfigItem(
#             "Run", "AnnihilationTimeLimit", 40, RangeValidator(1, 1024)
#         )
#         self.Run_RoutineTimeLimit = ConfigItem(
#             "Run", "RoutineTimeLimit", 10, RangeValidator(1, 1024)
#         )
#         self.Run_AnnihilationWeeklyLimit = ConfigItem(
#             "Run", "AnnihilationWeeklyLimit", True, BoolValidator()
#         )

#         self.UserData = MultipleConfig([MaaUserConfig])


# class MaaPlanConfig(ConfigBase):
#     """MAA计划表配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "")
#         self.Info_Mode = ConfigItem(
#             "Info", "Mode", "ALL", OptionsValidator(["ALL", "Weekly"])
#         )

#         self.config_item_dict: dict[str, Dict[str, ConfigItem]] = {}

#         for group in [
#             "ALL",
#             "Monday",
#             "Tuesday",
#             "Wednesday",
#             "Thursday",
#             "Friday",
#             "Saturday",
#             "Sunday",
#         ]:
#             self.config_item_dict[group] = {}

#             self.config_item_dict[group]["MedicineNumb"] = ConfigItem(
#                 group, "MedicineNumb", 0, RangeValidator(0, 1024)
#             )
#             self.config_item_dict[group]["SeriesNumb"] = ConfigItem(
#                 group,
#                 "SeriesNumb",
#                 "0",
#                 OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
#             )
#             self.config_item_dict[group]["Stage"] = ConfigItem(group, "Stage", "-")
#             self.config_item_dict[group]["Stage_1"] = ConfigItem(group, "Stage_1", "-")
#             self.config_item_dict[group]["Stage_2"] = ConfigItem(group, "Stage_2", "-")
#             self.config_item_dict[group]["Stage_3"] = ConfigItem(group, "Stage_3", "-")
#             self.config_item_dict[group]["Stage_Remain"] = ConfigItem(
#                 group, "Stage_Remain", "-"
#             )

#             for name in [
#                 "MedicineNumb",
#                 "SeriesNumb",
#                 "Stage",
#                 "Stage_1",
#                 "Stage_2",
#                 "Stage_3",
#                 "Stage_Remain",
#             ]:
#                 setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

#     def get_current_info(self, name: str) -> ConfigItem:
#         """获取当前的计划表配置项"""

#         if self.get("Info", "Mode") == "ALL":

#             return self.config_item_dict["ALL"][name]

#         elif self.get("Info", "Mode") == "Weekly":

#             dt = datetime.now()
#             if dt.time() < datetime.min.time().replace(hour=4):
#                 dt = dt - timedelta(days=1)
#             today = dt.strftime("%A")

#             if today in self.config_item_dict:
#                 return self.config_item_dict[today][name]
#             else:
#                 return self.config_item_dict["ALL"][name]

#         else:
#             raise ValueError("The mode is invalid.")


# class GeneralUserConfig(ConfigBase):
#     """通用子配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "新配置")
#         self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
#         self.Info_RemainedDay = ConfigItem(
#             "Info", "RemainedDay", -1, RangeValidator(-1, 1024)
#         )
#         self.Info_IfScriptBeforeTask = ConfigItem(
#             "Info", "IfScriptBeforeTask", False, BoolValidator()
#         )
#         self.Info_ScriptBeforeTask = ConfigItem(
#             "Info", "ScriptBeforeTask", "", FileValidator()
#         )
#         self.Info_IfScriptAfterTask = ConfigItem(
#             "Info", "IfScriptAfterTask", False, BoolValidator()
#         )
#         self.Info_ScriptAfterTask = ConfigItem(
#             "Info", "ScriptAfterTask", "", FileValidator()
#         )
#         self.Info_Notes = ConfigItem("Info", "Notes", "无")

#         self.Data_LastProxyDate = ConfigItem("Data", "LastProxyDate", "2000-01-01")
#         self.Data_ProxyTimes = ConfigItem(
#             "Data", "ProxyTimes", 0, RangeValidator(0, 1024)
#         )

#         self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
#         self.Notify_IfSendStatistic = ConfigItem(
#             "Notify", "IfSendStatistic", False, BoolValidator()
#         )
#         self.Notify_IfSendMail = ConfigItem(
#             "Notify", "IfSendMail", False, BoolValidator()
#         )
#         self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
#         self.Notify_IfServerChan = ConfigItem(
#             "Notify", "IfServerChan", False, BoolValidator()
#         )
#         self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
#         self.Notify_IfCompanyWebHookBot = ConfigItem(
#             "Notify", "IfCompanyWebHookBot", False, BoolValidator()
#         )
#         self.Notify_CompanyWebHookBotUrl = ConfigItem(
#             "Notify", "CompanyWebHookBotUrl", ""
#         )


# class GeneralConfig(ConfigBase):
#     """通用配置"""

#     def __init__(self) -> None:
#         super().__init__()

#         self.Info_Name = ConfigItem("Info", "Name", "")
#         self.Info_RootPath = ConfigItem("Info", "RootPath", ".", FileValidator())

#         self.Script_ScriptPath = ConfigItem(
#             "Script", "ScriptPath", ".", FileValidator()
#         )
#         self.Script_Arguments = ConfigItem("Script", "Arguments", "")
#         self.Script_IfTrackProcess = ConfigItem(
#             "Script", "IfTrackProcess", False, BoolValidator()
#         )
#         self.Script_ConfigPath = ConfigItem(
#             "Script", "ConfigPath", ".", FileValidator()
#         )
#         self.Script_ConfigPathMode = ConfigItem(
#             "Script", "ConfigPathMode", "File", OptionsValidator(["File", "Folder"])
#         )
#         self.Script_UpdateConfigMode = ConfigItem(
#             "Script",
#             "UpdateConfigMode",
#             "Never",
#             OptionsValidator(["Never", "Success", "Failure", "Always"]),
#         )
#         self.Script_LogPath = ConfigItem("Script", "LogPath", ".", FileValidator())
#         self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "%Y-%m-%d")
#         self.Script_LogTimeStart = ConfigItem(
#             "Script", "LogTimeStart", 1, RangeValidator(1, 1024)
#         )
#         self.Script_LogTimeEnd = ConfigItem(
#             "Script", "LogTimeEnd", 1, RangeValidator(1, 1024)
#         )
#         self.Script_LogTimeFormat = ConfigItem(
#             "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S"
#         )
#         self.Script_SuccessLog = ConfigItem("Script", "SuccessLog", "")
#         self.Script_ErrorLog = ConfigItem("Script", "ErrorLog", "")

#         self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
#         self.Game_Style = ConfigItem(
#             "Game", "Style", "Emulator", OptionsValidator(["Emulator", "Client"])
#         )
#         self.Game_Path = ConfigItem("Game", "Path", ".", FileValidator())
#         self.Game_Arguments = ConfigItem("Game", "Arguments", "")
#         self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 1024))
#         self.Game_IfForceClose = ConfigItem(
#             "Game", "IfForceClose", False, BoolValidator()
#         )

#         self.Run_ProxyTimesLimit = ConfigItem(
#             "Run", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
#         )
#         self.Run_RunTimesLimit = ConfigItem(
#             "Run", "RunTimesLimit", 3, RangeValidator(1, 1024)
#         )
#         self.Run_RunTimeLimit = ConfigItem(
#             "Run", "RunTimeLimit", 10, RangeValidator(1, 1024)
#         )

#         self.UserData = MultipleConfig([GeneralUserConfig])


class ScriptCreateIn(BaseModel):
    type: Literal["MAA", "General"] = Field(
        ..., description="脚本类型: MAA脚本, 通用脚本"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Dict[str, Any] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(None, description="脚本ID，仅在模式为Single时需要")


class ScriptGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="脚本索引列表")
    data: Dict[str, Any] = Field(..., description="脚本列表或单个脚本数据")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="脚本更新数据")


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表，按新顺序排列")


class UserInBase(BaseModel):
    scriptId: str = Field(..., description="所属脚本ID")


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Dict[str, Any] = Field(..., description="用户配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="用户更新数据")


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="用户ID列表，按新顺序排列")


class PlanCreateIn(BaseModel):
    type: Literal["MaaPlan"]


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: Dict[str, Any] = Field(..., description="计划配置数据")


class PlanGetIn(BaseModel):
    planId: Optional[str] = Field(None, description="计划ID，仅在模式为Single时需要")


class PlanGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="计划索引列表")
    data: Dict[str, Any] = Field(..., description="计划列表或单个计划数据")


class PlanUpdateIn(BaseModel):
    planId: str = Field(..., description="计划ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="计划更新数据")


class PlanDeleteIn(BaseModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="计划ID列表，按新顺序排列")


class QueueCreateOut(OutBase):
    queueId: str = Field(..., description="新创建的队列ID")
    data: Dict[str, Any] = Field(..., description="队列配置数据")


class QueueGetIn(BaseModel):
    queueId: Optional[str] = Field(None, description="队列ID，仅在模式为Single时需要")


class QueueGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="队列索引列表")
    data: Dict[str, Any] = Field(..., description="队列列表或单个队列数据")


class QueueUpdateIn(BaseModel):
    queueId: str = Field(..., description="队列ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="队列更新数据")


class QueueDeleteIn(BaseModel):
    queueId: str = Field(..., description="队列ID")


class QueueReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="调度队列ID列表，按新顺序排列")


class QueueSetInBase(BaseModel):
    queueId: str = Field(..., description="所属队列ID")


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(..., description="新创建的时间设置ID")
    data: Dict[str, Any] = Field(..., description="时间设置配置数据")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="时间设置更新数据")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="时间设置ID列表，按新顺序排列")


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(..., description="新创建的队列项ID")
    data: Dict[str, Any] = Field(..., description="队列项配置数据")


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="队列项更新数据")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="队列项ID列表，按新顺序排列")


class DispatchIn(BaseModel):
    taskId: str = Field(
        ...,
        description="目标任务ID，设置类任务可选对应脚本ID或用户ID，代理类任务可选对应队列ID或脚本ID",
    )


class TaskCreateIn(DispatchIn):
    mode: Literal["自动代理", "人工排查", "设置脚本"] = Field(
        ..., description="任务模式"
    )


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class TaskMessage(BaseModel):
    type: Literal["Update", "Message", "Info", "Signal"] = Field(
        ...,
        description="消息类型 Update: 更新数据, Message: 请求弹出对话框, Info: 需要在UI显示的消息, Signal: 程序信号",
    )
    data: Dict[str, Any] = Field(..., description="消息数据，具体内容根据type类型而定")


class SettingGetOut(OutBase):
    data: GlobalConfig = Field(..., description="全局设置数据")


class SettingUpdateIn(BaseModel):
    data: GlobalConfig = Field(..., description="全局设置需要更新的数据")
