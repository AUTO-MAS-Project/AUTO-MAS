#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


from pydantic import BaseModel, Field
from typing import Any, Dict, List, Union, Optional, Literal


class OutBase(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class InfoOut(OutBase):
    data: Dict[str, Any] = Field(..., description="收到的服务器数据")


class VersionOut(OutBase):
    if_need_update: bool = Field(..., description="后端代码是否需要更新")
    current_time: str = Field(..., description="后端代码当前时间戳")
    current_hash: str = Field(..., description="后端代码当前哈希值")


class NoticeOut(OutBase):
    if_need_show: bool = Field(..., description="是否需要显示公告")
    data: Dict[str, str] = Field(
        ..., description="公告信息, key为公告标题, value为公告内容"
    )


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")


class ComboBoxOut(OutBase):
    data: List[ComboBoxItem] = Field(..., description="下拉框选项")


class GetStageIn(BaseModel):
    type: Literal[
        "User",
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


class EmulatorConfigIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["EmulatorConfig"] = Field(..., description="配置类型")


class EmulatorConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="模拟器名称")
    Path: Optional[str] = Field(default=None, description="模拟器路径")


class EmulatorConfig_Data(BaseModel):
    Type: Optional[
        Literal["general", "mumu", "ldplayer", "nox", "memu", "blueStacks"]
    ] = Field(default=None, description="模拟器类型")
    BossKey: Optional[str] = Field(default=None, description="模拟器老板键")
    MaxWaitTime: Optional[int] = Field(default=None, description="最大等待时间")


class EmulatorConfig(BaseModel):
    Info: Optional[EmulatorConfig_Info] = Field(
        default=None, description="模拟器基础信息"
    )
    Data: Optional[EmulatorConfig_Data] = Field(
        default=None, description="模拟器配置数据"
    )


class WebhookIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["Webhook"] = Field(..., description="配置类型")


class Webhook_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="Webhook名称")
    Enabled: Optional[bool] = Field(default=None, description="是否启用")


class Webhook_Data(BaseModel):
    Url: Optional[str] = Field(default=None, description="Webhook URL")
    Template: Optional[str] = Field(default=None, description="消息模板")
    Headers: Optional[str] = Field(default=None, description="自定义请求头")
    Method: Optional[Literal["POST", "GET"]] = Field(
        default=None, description="请求方法"
    )


class Webhook(BaseModel):
    Info: Optional[Webhook_Info] = Field(default=None, description="Webhook基础信息")
    Data: Optional[Webhook_Data] = Field(default=None, description="Webhook配置数据")


class GlobalConfig_Function(BaseModel):
    HistoryRetentionTime: Optional[Literal[7, 15, 30, 60, 90, 180, 365, 0]] = Field(
        None, description="历史记录保留时间, 0表示永久保存"
    )
    IfAllowSleep: Optional[bool] = Field(default=None, description="允许休眠")
    IfSilence: Optional[bool] = Field(default=None, description="静默模式")
    IfAgreeBilibili: Optional[bool] = Field(
        default=None, description="同意哔哩哔哩用户协议"
    )
    IfBlockAd: Optional[bool] = Field(default=None, description="屏蔽模拟器广告")


class GlobalConfig_Voice(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="语音功能是否启用")
    Type: Optional[Literal["simple", "noisy"]] = Field(
        default=None, description="语音类型, simple为简洁, noisy为聒噪"
    )


class GlobalConfig_Start(BaseModel):
    IfSelfStart: Optional[bool] = Field(
        default=None, description="是否在系统启动时自动运行"
    )
    IfMinimizeDirectly: Optional[bool] = Field(
        default=None, description="启动时是否直接最小化到托盘而不显示主窗口"
    )


class GlobalConfig_UI(BaseModel):
    IfShowTray: Optional[bool] = Field(default=None, description="是否常态显示托盘图标")
    IfToTray: Optional[bool] = Field(default=None, description="是否最小化到托盘")


class GlobalConfig_Notify(BaseModel):
    SendTaskResultTime: Optional[Literal["不推送", "任何时刻", "仅失败时"]] = Field(
        default=None, description="任务结果推送时机"
    )
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendSixStar: Optional[bool] = Field(
        default=None, description="是否发送公招六星通知"
    )
    IfPushPlyer: Optional[bool] = Field(default=None, description="是否推送系统通知")
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件通知")
    IfKoishiSupport: Optional[bool] = Field(
        default=None, description="是否启用Koishi支持"
    )
    KoishiServerAddress: Optional[str] = Field(
        default=None, description="Koishi服务器地址"
    )
    KoishiToken: Optional[str] = Field(default=None, description="Koishi Token")
    SMTPServerAddress: Optional[str] = Field(default=None, description="SMTP服务器地址")
    AuthorizationCode: Optional[str] = Field(default=None, description="SMTP授权码")
    FromAddress: Optional[str] = Field(default=None, description="邮件发送地址")
    ToAddress: Optional[str] = Field(default=None, description="邮件接收地址")
    IfServerChan: Optional[bool] = Field(
        default=None, description="是否使用ServerChan推送"
    )
    ServerChanKey: Optional[str] = Field(default=None, description="ServerChan推送密钥")


class GlobalConfig_Update(BaseModel):
    IfAutoUpdate: Optional[bool] = Field(default=None, description="是否自动更新")
    Source: Optional[Literal["GitHub", "MirrorChyan", "AutoSite"]] = Field(
        default=None, description="更新源: GitHub源, Mirror酱源, 自建源"
    )
    Channel: Optional[Literal["stable", "beta"]] = Field(
        default=None, description="更新渠道: 稳定版, 测试版"
    )
    ProxyAddress: Optional[str] = Field(default=None, description="网络代理地址")
    MirrorChyanCDK: Optional[str] = Field(default=None, description="Mirror酱CDK")


class GlobalConfig(BaseModel):
    Function: Optional[GlobalConfig_Function] = Field(
        default=None, description="功能相关配置"
    )
    Voice: Optional[GlobalConfig_Voice] = Field(
        default=None, description="语音相关配置"
    )
    Start: Optional[GlobalConfig_Start] = Field(
        default=None, description="启动相关配置"
    )
    UI: Optional[GlobalConfig_UI] = Field(default=None, description="界面相关配置")
    Notify: Optional[GlobalConfig_Notify] = Field(
        default=None, description="通知相关配置"
    )
    Update: Optional[GlobalConfig_Update] = Field(
        default=None, description="更新相关配置"
    )


class QueueIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueConfig"] = Field(..., description="配置类型")


class QueueItemIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueItem"] = Field(..., description="配置类型")


class TimeSetIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["TimeSet"] = Field(..., description="配置类型")


class QueueItem_Info(BaseModel):
    ScriptId: Optional[str] = Field(
        default=None, description="任务所对应的脚本ID, 为None时表示未选择"
    )


class QueueItem(BaseModel):
    Info: Optional[QueueItem_Info] = Field(default=None, description="队列项")


class TimeSet_Info(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用")
    Days: Optional[
        List[
            Literal[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        ]
    ] = Field(default=None, description="执行周期, 可多选")
    Time: Optional[str] = Field(default=None, description="时间设置, 格式为HH:MM")


class TimeSet(BaseModel):
    Info: Optional[TimeSet_Info] = Field(default=None, description="时间项")


class QueueConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="队列名称")
    TimeEnabled: Optional[bool] = Field(default=None, description="是否启用定时")
    StartUpEnabled: Optional[bool] = Field(default=None, description="是否启动时运行")
    AfterAccomplish: Optional[
        Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
        ]
    ] = Field(default=None, description="完成后操作")


class QueueConfig(BaseModel):
    Info: Optional[QueueConfig_Info] = Field(default=None, description="队列信息")


class ScriptIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["MaaConfig", "GeneralConfig"] = Field(..., description="配置类型")


class UserIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["MaaUserConfig", "GeneralUserConfig"] = Field(
        ..., description="配置类型"
    )


class MaaUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名")
    Id: Optional[str] = Field(default=None, description="用户ID")
    Mode: Optional[Literal["简洁", "详细"]] = Field(
        default=None, description="用户配置模式"
    )
    StageMode: Optional[str] = Field(default=None, description="关卡配置模式")
    Server: Optional[
        Literal["Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"]
    ] = Field(default=None, description="服务器")
    Status: Optional[bool] = Field(default=None, description="用户状态")
    RemainedDay: Optional[int] = Field(default=None, description="剩余天数")
    Annihilation: Optional[
        Literal[
            "Close",
            "Annihilation",
            "Chernobog@Annihilation",
            "LungmenOutskirts@Annihilation",
            "LungmenDowntown@Annihilation",
        ]
    ] = Field(default=None, description="剿灭模式")
    InfrastMode: Optional[Literal["Normal", "Rotation", "Custom"]] = Field(
        default=None, description="基建模式"
    )
    InfrastName: Optional[str] = Field(default=None, description="基建方案名称")
    InfrastIndex: Optional[str] = Field(default=None, description="基建方案索引")
    Password: Optional[str] = Field(default=None, description="密码")
    Notes: Optional[str] = Field(default=None, description="备注")
    MedicineNumb: Optional[int] = Field(default=None, description="吃理智药数量")
    SeriesNumb: Optional[Literal["0", "6", "5", "4", "3", "2", "1", "-1"]] = Field(
        default=None, description="连战次数"
    )
    Stage: Optional[str] = Field(default=None, description="关卡选择")
    Stage_1: Optional[str] = Field(default=None, description="备选关卡 - 1")
    Stage_2: Optional[str] = Field(default=None, description="备选关卡 - 2")
    Stage_3: Optional[str] = Field(default=None, description="备选关卡 - 3")
    Stage_Remain: Optional[str] = Field(default=None, description="剩余理智关卡")
    IfSkland: Optional[bool] = Field(default=None, description="是否启用森空岛签到")
    SklandToken: Optional[str] = Field(default=None, description="SklandToken")


class MaaUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    LastAnnihilationDate: Optional[str] = Field(
        default=None, description="上次剿灭日期"
    )
    LastSklandDate: Optional[str] = Field(
        default=None, description="上次森空岛签到日期"
    )
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")
    IfPassCheck: Optional[bool] = Field(default=None, description="是否通过人工排查")


class MaaUserConfig_Task(BaseModel):
    IfStartUp: Optional[bool] = Field(default=None, description="开始唤醒")
    IfRecruit: Optional[bool] = Field(default=None, description="自动公招")
    IfInfrast: Optional[bool] = Field(default=None, description="基建换班")
    IfFight: Optional[bool] = Field(default=None, description="理智作战")
    IfMall: Optional[bool] = Field(default=None, description="信用收支")
    IfAward: Optional[bool] = Field(default=None, description="领取奖励")
    IfRoguelike: Optional[bool] = Field(default=None, description="自动肉鸽")
    IfReclamation: Optional[bool] = Field(default=None, description="生息演算")


class MaaUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendSixStar: Optional[bool] = Field(default=None, description="是否发送高资喜报")
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件通知")
    ToAddress: Optional[str] = Field(default=None, description="邮件接收地址")
    IfServerChan: Optional[bool] = Field(
        default=None, description="是否使用Server酱推送"
    )
    ServerChanKey: Optional[str] = Field(default=None, description="ServerChanKey")


class GeneralUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件通知")
    ToAddress: Optional[str] = Field(default=None, description="邮件接收地址")
    IfServerChan: Optional[bool] = Field(
        default=None, description="是否使用Server酱推送"
    )
    ServerChanKey: Optional[str] = Field(default=None, description="ServerChanKey")


class MaaUserConfig(BaseModel):
    Info: Optional[MaaUserConfig_Info] = Field(default=None, description="基础信息")
    Data: Optional[MaaUserConfig_Data] = Field(default=None, description="用户数据")
    Task: Optional[MaaUserConfig_Task] = Field(default=None, description="任务列表")
    Notify: Optional[MaaUserConfig_Notify] = Field(default=None, description="单独通知")


class MaaConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="脚本名称")
    Path: Optional[str] = Field(default=None, description="脚本路径")


class MaaConfig_Emulator(BaseModel):
    Id: Optional[str] = Field(default=None, description="模拟器ID")
    Index: Optional[str] = Field(default=None, description="模拟器多开实例索引")


class MaaConfig_Run(BaseModel):
    TaskTransitionMethod: Optional[Literal["NoAction", "ExitGame", "ExitEmulator"]] = (
        Field(default=None, description="简洁任务间切换方式")
    )
    ProxyTimesLimit: Optional[int] = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="重试次数限制")
    AnnihilationTimeLimit: Optional[int] = Field(
        default=None, description="剿灭超时限制"
    )
    RoutineTimeLimit: Optional[int] = Field(default=None, description="日常超时限制")
    AnnihilationWeeklyLimit: Optional[bool] = Field(
        default=None, description="剿灭每周仅代理至上限"
    )


class MaaConfig(BaseModel):
    Info: Optional[MaaConfig_Info] = Field(default=None, description="脚本基础信息")
    Emulator: Optional[MaaConfig_Emulator] = Field(
        default=None, description="模拟器配置"
    )
    Run: Optional[MaaConfig_Run] = Field(default=None, description="脚本运行配置")


class GeneralUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名")
    Status: Optional[bool] = Field(default=None, description="用户状态")
    RemainedDay: Optional[int] = Field(default=None, description="剩余天数")
    IfScriptBeforeTask: Optional[bool] = Field(
        default=None, description="是否在任务前执行脚本"
    )
    ScriptBeforeTask: Optional[str] = Field(default=None, description="任务前脚本路径")
    IfScriptAfterTask: Optional[bool] = Field(
        default=None, description="是否在任务后执行脚本"
    )
    ScriptAfterTask: Optional[str] = Field(default=None, description="任务后脚本路径")
    Notes: Optional[str] = Field(default=None, description="备注")


class GeneralUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")


class GeneralUserConfig(BaseModel):
    Info: Optional[GeneralUserConfig_Info] = Field(default=None, description="用户信息")
    Data: Optional[GeneralUserConfig_Data] = Field(default=None, description="用户数据")
    Notify: Optional[GeneralUserConfig_Notify] = Field(
        default=None, description="单独通知"
    )


class GeneralConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="脚本名称")
    RootPath: Optional[str] = Field(default=None, description="脚本根目录")


class GeneralConfig_Script(BaseModel):
    ScriptPath: Optional[str] = Field(default=None, description="脚本可执行文件路径")
    Arguments: Optional[str] = Field(default=None, description="脚本启动附加命令参数")
    IfTrackProcess: Optional[bool] = Field(
        default=None, description="是否追踪脚本子进程"
    )
    TrackProcessName: Optional[str] = Field(default=None, description="追踪进程名称")
    TrackProcessExe: Optional[str] = Field(default=None, description="追踪进程文件路径")
    TrackProcessCmdline: Optional[str] = Field(
        default=None, description="追踪进程启动命令行参数"
    )
    ConfigPath: Optional[str] = Field(default=None, description="配置文件路径")
    ConfigPathMode: Optional[Literal["File", "Folder"]] = Field(
        default=None, description="配置文件类型: 单个文件, 文件夹"
    )
    UpdateConfigMode: Optional[Literal["Never", "Success", "Failure", "Always"]] = (
        Field(
            default=None,
            description="更新配置时机, 从不, 仅成功时, 仅失败时, 任务结束时",
        )
    )
    LogPath: Optional[str] = Field(default=None, description="日志文件路径")
    LogPathFormat: Optional[str] = Field(default=None, description="日志文件名格式")
    LogTimeStart: Optional[int] = Field(default=None, description="日志时间戳开始位置")
    LogTimeEnd: Optional[int] = Field(default=None, description="日志时间戳结束位置")
    LogTimeFormat: Optional[str] = Field(default=None, description="日志时间戳格式")
    SuccessLog: Optional[str] = Field(default=None, description="成功时日志")
    ErrorLog: Optional[str] = Field(default=None, description="错误时日志")


class GeneralConfig_Game(BaseModel):
    Enabled: Optional[bool] = Field(
        default=None, description="游戏/模拟器相关功能是否启用"
    )
    Type: Optional[Literal["Emulator", "Client", "URL"]] = Field(
        default=None, description="类型: 模拟器, PC端, URL协议"
    )
    Path: Optional[str] = Field(default=None, description="游戏/模拟器程序路径")
    URL: Optional[str] = Field(default=None, description="自定义协议URL")
    ProcessName: Optional[str] = Field(default=None, description="游戏进程名称")
    Arguments: Optional[str] = Field(default=None, description="游戏/模拟器启动参数")
    WaitTime: Optional[int] = Field(default=None, description="游戏/模拟器等待启动时间")
    IfForceClose: Optional[bool] = Field(
        default=None, description="是否强制关闭游戏/模拟器进程"
    )
    EmulatorId: Optional[str] = Field(default=None, description="模拟器ID")
    EmulatorIndex: Optional[str] = Field(default=None, description="模拟器多开实例索引")


class GeneralConfig_Run(BaseModel):
    ProxyTimesLimit: Optional[int] = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="重试次数限制")
    RunTimeLimit: Optional[int] = Field(default=None, description="日志超时限制")


class GeneralConfig(BaseModel):
    Info: Optional[GeneralConfig_Info] = Field(default=None, description="脚本基础信息")
    Script: Optional[GeneralConfig_Script] = Field(default=None, description="脚本配置")
    Game: Optional[GeneralConfig_Game] = Field(default=None, description="游戏配置")
    Run: Optional[GeneralConfig_Run] = Field(default=None, description="运行配置")


class PlanIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["MaaPlanConfig"] = Field(..., description="配置类型")


class MaaPlanConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="计划表名称")
    Mode: Optional[Literal["ALL", "Weekly"]] = Field(
        default=None, description="计划表模式"
    )


class MaaPlanConfig_Item(BaseModel):
    MedicineNumb: Optional[int] = Field(default=None, description="吃理智药")
    SeriesNumb: Optional[Literal["0", "6", "5", "4", "3", "2", "1", "-1"]] = Field(
        None, description="连战次数"
    )
    Stage: Optional[str] = Field(default=None, description="关卡选择")
    Stage_1: Optional[str] = Field(default=None, description="备选关卡 - 1")
    Stage_2: Optional[str] = Field(default=None, description="备选关卡 - 2")
    Stage_3: Optional[str] = Field(default=None, description="备选关卡 - 3")
    Stage_Remain: Optional[str] = Field(default=None, description="剩余理智关卡")


class MaaPlanConfig(BaseModel):
    Info: Optional[MaaPlanConfig_Info] = Field(default=None, description="基础信息")
    ALL: Optional[MaaPlanConfig_Item] = Field(default=None, description="全局")
    Monday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周一")
    Tuesday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周二")
    Wednesday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周三")
    Thursday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周四")
    Friday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周五")
    Saturday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周六")
    Sunday: Optional[MaaPlanConfig_Item] = Field(default=None, description="周日")


class HistoryIndexItem(BaseModel):
    date: str = Field(..., description="日期")
    status: Literal["DONE", "ERROR"] = Field(..., description="状态")
    jsonFile: str = Field(..., description="对应JSON文件")


class HistoryData(BaseModel):
    index: Optional[List[HistoryIndexItem]] = Field(
        default=None, description="历史记录索引列表"
    )
    recruit_statistics: Optional[Dict[str, int]] = Field(
        default=None, description="公招统计数据, key为星级, value为对应的公招数量"
    )
    drop_statistics: Optional[Dict[str, Dict[str, int]]] = Field(
        default=None,
        description="掉落统计数据, 格式为 { '关卡号': { '掉落物': 数量 } }",
    )
    error_info: Optional[Dict[str, str]] = Field(
        default=None, description="报错信息, key为时间戳, value为错误描述"
    )
    log_content: Optional[str] = Field(
        default=None, description="日志内容, 仅在提取单条历史记录数据时返回"
    )


class ScriptCreateIn(BaseModel):
    type: Literal["MAA", "General"] = Field(
        ..., description="脚本类型: MAA脚本, 通用脚本"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Union[MaaConfig, GeneralConfig] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: List[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: Dict[str, Union[MaaConfig, GeneralConfig]] = Field(
        ..., description="脚本数据字典, key来自于index列表的uid"
    )


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Union[MaaConfig, GeneralConfig] = Field(..., description="脚本更新数据")


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表, 按新顺序排列")


class ScriptFileIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    jsonFile: str = Field(..., description="配置文件路径")


class ScriptUrlIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    url: str = Field(..., description="配置文件URL")


class ScriptUploadIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., description="配置名称")
    author: str = Field(..., description="作者")
    description: str = Field(..., description="描述")


class UserInBase(BaseModel):
    scriptId: str = Field(..., description="所属脚本ID")


class UserGetIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时表示获取所有用户数据"
    )


class UserGetOut(OutBase):
    index: List[UserIndexItem] = Field(..., description="用户索引列表")
    data: Dict[str, Union[MaaUserConfig, GeneralUserConfig]] = Field(
        ..., description="用户数据字典, key来自于index列表的uid"
    )


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Union[MaaUserConfig, GeneralUserConfig] = Field(
        ..., description="用户配置数据"
    )


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Union[MaaUserConfig, GeneralUserConfig] = Field(
        ..., description="用户更新数据"
    )


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="用户ID列表, 按新顺序排列")


class UserSetIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    jsonFile: str = Field(..., description="JSON文件路径, 用于导入自定义基建文件")


class EmulatorGetIn(BaseModel):
    emulatorId: Optional[str] = Field(
        default=None, description="模拟器ID, 未携带时表示获取所有模拟器数据"
    )


class EmulatorGetOut(OutBase):
    index: List[EmulatorConfigIndexItem] = Field(..., description="模拟器索引列表")
    data: Dict[str, EmulatorConfig] = Field(
        ..., description="模拟器数据字典, key来自于index列表的uid"
    )


class EmulatorCreateOut(OutBase):
    emulatorId: str = Field(..., description="新创建的模拟器 ID")
    data: EmulatorConfig = Field(..., description="模拟器配置数据")


class EmulatorUpdateIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器 ID")
    data: EmulatorConfig = Field(..., description="模拟器更新数据")


class EmulatorDeleteIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器 ID")


class EmulatorReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="模拟器 ID列表, 按新顺序排列")


class EmulatorOperateIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器 ID")
    operate: Literal["open", "close", "show"] = Field(..., description="操作类型")
    index: str = Field(..., description="模拟器索引")


class DeviceStatus(BaseModel):
    """设备状态枚举"""

    ONLINE: int = Field(default=0, description="设备在线")
    OFFLINE: int = Field(default=1, description="设备离线")
    STARTING: int = Field(default=2, description="设备开启中")
    CLOSEING: int = Field(default=3, description="设备关闭中")
    ERROR: int = Field(default=4, description="错误")
    NOT_FOUND: int = Field(default=5, description="未找到设备")
    UNKNOWN: int = Field(default=10, description="未知状态")


class DeviceInfo(BaseModel):
    """设备信息"""

    title: str = Field(..., description="设备标题/名称")
    status: int = Field(..., description="设备状态, 参考DeviceStatus枚举值")
    adb_address: str = Field(..., description="ADB连接地址")


class EmulatorStatusOut(OutBase):
    data: Dict[str, Dict[str, DeviceInfo]] = Field(
        ...,
        description="模拟器状态信息, 外层key为模拟器ID, 内层key为设备索引, value为设备信息",
    )


class EmulatorSearchResult(BaseModel):
    type: str = Field(..., description="模拟器类型")
    path: str = Field(..., description="模拟器路径")
    name: str = Field(..., description="模拟器名称")


class EmulatorSearchOut(OutBase):
    emulators: List[EmulatorSearchResult] = Field(
        default_factory=list, description="搜索到的模拟器列表"
    )


class WebhookInBase(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="所属脚本ID, 获取全局设置的Webhook数据时无需携带"
    )
    userId: Optional[str] = Field(
        default=None, description="所属用户ID, 获取全局设置的Webhook数据时无需携带"
    )


class WebhookGetIn(WebhookInBase):
    webhookId: Optional[str] = Field(
        default=None, description="Webhook ID, 未携带时表示获取所有Webhook数据"
    )


class WebhookGetOut(OutBase):
    index: List[WebhookIndexItem] = Field(..., description="Webhook索引列表")
    data: Dict[str, Webhook] = Field(
        ..., description="Webhook数据字典, key来自于index列表的uid"
    )


class WebhookCreateOut(OutBase):
    webhookId: str = Field(..., description="新创建的Webhook ID")
    data: Webhook = Field(..., description="Webhook配置数据")


class WebhookUpdateIn(WebhookInBase):
    webhookId: str = Field(..., description="Webhook ID")
    data: Webhook = Field(..., description="Webhook更新数据")


class WebhookDeleteIn(WebhookInBase):
    webhookId: str = Field(..., description="Webhook ID")


class WebhookReorderIn(WebhookInBase):
    indexList: List[str] = Field(..., description="Webhook ID列表, 按新顺序排列")


class WebhookTestIn(WebhookInBase):
    data: Webhook = Field(..., description="Webhook配置数据")


class PlanCreateIn(BaseModel):
    type: Literal["MaaPlan"]


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: MaaPlanConfig = Field(..., description="计划配置数据")


class PlanGetIn(BaseModel):
    planId: Optional[str] = Field(
        default=None, description="计划ID, 未携带时表示获取所有计划数据"
    )


class PlanGetOut(OutBase):
    index: List[PlanIndexItem] = Field(..., description="计划索引列表")
    data: Dict[str, MaaPlanConfig] = Field(..., description="计划列表或单个计划数据")


class PlanUpdateIn(BaseModel):
    planId: str = Field(..., description="计划ID")
    data: MaaPlanConfig = Field(..., description="计划更新数据")


class PlanDeleteIn(BaseModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="计划ID列表, 按新顺序排列")


class QueueCreateOut(OutBase):
    queueId: str = Field(..., description="新创建的队列ID")
    data: QueueConfig = Field(..., description="队列配置数据")


class QueueGetIn(BaseModel):
    queueId: Optional[str] = Field(
        default=None, description="队列ID, 未携带时表示获取所有队列数据"
    )


class QueueGetOut(OutBase):
    index: List[QueueIndexItem] = Field(..., description="队列索引列表")
    data: Dict[str, QueueConfig] = Field(
        ..., description="队列数据字典, key来自于index列表的uid"
    )


class QueueUpdateIn(BaseModel):
    queueId: str = Field(..., description="队列ID")
    data: QueueConfig = Field(..., description="队列更新数据")


class QueueDeleteIn(BaseModel):
    queueId: str = Field(..., description="队列ID")


class QueueReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="按新顺序排列的调度队列UID列表")


class QueueSetInBase(BaseModel):
    queueId: str = Field(..., description="所属队列ID")


class TimeSetGetIn(QueueSetInBase):
    timeSetId: Optional[str] = Field(
        default=None, description="时间设置ID, 未携带时表示获取所有时间设置数据"
    )


class TimeSetGetOut(OutBase):
    index: List[TimeSetIndexItem] = Field(..., description="时间设置索引列表")
    data: Dict[str, TimeSet] = Field(
        ..., description="时间设置数据字典, key来自于index列表的uid"
    )


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(..., description="新创建的时间设置ID")
    data: TimeSet = Field(..., description="时间设置配置数据")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")
    data: TimeSet = Field(..., description="时间设置更新数据")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="时间设置ID列表, 按新顺序排列")


class QueueItemGetIn(QueueSetInBase):
    queueItemId: Optional[str] = Field(
        default=None, description="队列项ID, 未携带时表示获取所有队列项数据"
    )


class QueueItemGetOut(OutBase):
    index: List[QueueItemIndexItem] = Field(..., description="队列项索引列表")
    data: Dict[str, QueueItem] = Field(
        ..., description="队列项数据字典, key来自于index列表的uid"
    )


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(..., description="新创建的队列项ID")
    data: QueueItem = Field(..., description="队列项配置数据")


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")
    data: QueueItem = Field(..., description="队列项更新数据")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="队列项ID列表, 按新顺序排列")


class DispatchIn(BaseModel):
    taskId: str = Field(
        ...,
        description="目标任务ID, 设置类任务可选对应脚本ID或用户ID, 代理类任务可选对应队列ID或脚本ID",
    )


class TaskCreateIn(DispatchIn):
    mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"] = Field(
        ..., description="任务模式"
    )


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class WebSocketMessage(BaseModel):
    id: str = Field(..., description="消息ID, 为Main时表示消息来自主进程")
    type: Literal["Update", "Message", "Info", "Signal"] = Field(
        ...,
        description="消息类型 Update: 更新数据, Message: 请求弹出对话框, Info: 需要在UI显示的消息, Signal: 程序信号",
    )
    data: Dict[str, Any] = Field(..., description="消息数据, 具体内容根据type类型而定")


class PowerIn(BaseModel):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] = Field(..., description="电源操作信号")


class PowerOut(OutBase):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] = Field(..., description="电源操作信号")


class HistorySearchIn(BaseModel):
    mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field(..., description="合并模式")
    start_date: str = Field(..., description="开始日期, 格式YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期, 格式YYYY-MM-DD")


class HistorySearchOut(OutBase):
    data: Dict[str, Dict[str, HistoryData]] = Field(
        ...,
        description="历史记录索引数据字典, 格式为 { '日期': { '用户名': [历史记录信息] } }",
    )


class HistoryDataGetIn(BaseModel):
    jsonPath: str = Field(..., description="需要提取数据的历史记录JSON文件")


class HistoryDataGetOut(OutBase):
    data: HistoryData = Field(..., description="历史记录数据")


class SettingGetOut(OutBase):
    data: GlobalConfig = Field(..., description="全局设置数据")


class SettingUpdateIn(BaseModel):
    data: GlobalConfig = Field(..., description="全局设置需要更新的数据")


class UpdateCheckIn(BaseModel):
    current_version: str = Field(..., description="当前前端版本号")
    if_force: bool = Field(default=False, description="是否强制拉取更新信息")


class UpdateCheckOut(OutBase):
    if_need_update: bool = Field(..., description="是否需要更新前端")
    latest_version: str = Field(..., description="最新前端版本号")
    update_info: Dict[str, List[str]] = Field(..., description="版本更新信息字典")


# ============== WebSocket 调试相关模型 ==============


class WSClientCreateIn(BaseModel):
    """创建 WebSocket 客户端请求"""

    name: str = Field(..., description="客户端名称，用于标识")
    url: str = Field(
        ..., description="WebSocket 服务器地址，如 ws://localhost:5140/path"
    )
    ping_interval: float = Field(default=15.0, description="心跳发送间隔（秒）")
    ping_timeout: float = Field(default=30.0, description="心跳超时时间（秒）")
    reconnect_interval: float = Field(default=5.0, description="重连间隔（秒）")
    max_reconnect_attempts: int = Field(
        default=-1, description="最大重连次数，-1为无限"
    )


class WSClientCreateOut(OutBase):
    """创建客户端响应"""

    data: Optional[Dict[str, Any]] = Field(default=None, description="返回数据")


class WSClientConnectIn(BaseModel):
    """连接请求"""

    name: str = Field(..., description="客户端名称")


class WSClientDisconnectIn(BaseModel):
    """断开连接请求"""

    name: str = Field(..., description="客户端名称")


class WSClientRemoveIn(BaseModel):
    """删除客户端请求"""

    name: str = Field(..., description="客户端名称")


class WSClientSendIn(BaseModel):
    """发送消息请求"""

    name: str = Field(..., description="客户端名称")
    message: Dict[str, Any] = Field(..., description="要发送的 JSON 消息")


class WSClientSendJsonIn(BaseModel):
    """发送自定义 JSON 消息请求"""

    name: str = Field(..., description="客户端名称")
    msg_id: str = Field(default="Client", description="消息 ID")
    msg_type: str = Field(..., description="消息类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="消息数据")


class WSClientAuthIn(BaseModel):
    """发送认证请求"""

    name: str = Field(..., description="客户端名称")
    token: str = Field(..., description="认证 Token")
    auth_type: str = Field(default="auth", description="认证消息类型")
    extra_data: Optional[Dict[str, Any]] = Field(
        default=None, description="额外认证数据"
    )


class WSClientStatusIn(BaseModel):
    """获取客户端状态请求"""

    name: str = Field(..., description="客户端名称")


class WSClientStatusOut(OutBase):
    """客户端状态响应"""

    data: Optional[Dict[str, Any]] = Field(default=None, description="状态数据")


class WSClientListOut(OutBase):
    """客户端列表响应"""

    data: Optional[Dict[str, Any]] = Field(default=None, description="客户端列表")


class WSMessageHistoryOut(OutBase):
    """消息历史响应"""

    data: Optional[Dict[str, Any]] = Field(default=None, description="消息历史")


class WSClearHistoryIn(BaseModel):
    """清空消息历史请求"""

    name: Optional[str] = Field(default=None, description="客户端名称，为空则清空所有")


class WSCommandsOut(OutBase):
    """可用命令列表响应"""

    data: Optional[Dict[str, Any]] = Field(default=None, description="命令列表")
