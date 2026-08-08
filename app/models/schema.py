#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from pydantic import BaseModel, Field, JsonValue, field_validator
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


class TagItem(BaseModel):
    text: str = Field(..., description="标签文本")
    color: Literal[
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "brown",
        "black",
        "white",
        "gray",
        "silver",
        "gold",
    ] = Field(..., description="标签颜色")


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")
    supported_modes: Optional[
        List[Literal["AutoProxy", "ManualReview", "ScriptConfig"]]
    ] = Field(default=None, description="任务项支持的执行模式；非脚本项为空")


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
    Type: Optional[Literal["general", "mumu", "ldplayer"]] = Field(
        default=None, description="模拟器类型"
    )
    Path: Optional[str] = Field(default=None, description="模拟器路径")
    BossKey: Optional[str] = Field(default=None, description="老板键快捷键配置")
    MaxWaitTime: Optional[int] = Field(default=None, description="最大等待时间（秒）")
    ForceKillOnClose: Optional[bool] = Field(
        default=None, description="关闭 MuMu 时强力清理残留进程"
    )


class EmulatorConfig(BaseModel):
    Info: Optional[EmulatorConfig_Info] = Field(
        default=None, description="模拟器基础信息"
    )


class ToolsConfig_ArknightsPC(BaseModel):
    Enabled: bool | None = Field(default=None, description="是否启用 ArknightsPC 工具")
    PauseKey: str | None = Field(default=None, description="暂停键位")
    SelectDeployedKey: str | None = Field(
        default=None, description="选中已部署干员键位"
    )
    UseSkillKey: str | None = Field(default=None, description="释放技能键位")
    RetreatKey: str | None = Field(default=None, description="撤退键位")
    NextFrameKey: str | None = Field(default=None, description="下一帧键位")
    AnotherQuitKey: str | None = Field(default=None, description="自定义退出、暂停键位")
    Status: str | None = Field(default=None, description="工具状态 Tag")


class ToolsConfig_GameSign(BaseModel):
    Enabled: bool | None = Field(default=None, description="是否启用游戏签到")
    NotifyEnabled: bool | None = Field(default=None, description="签到后是否发送通知")
    WindowStart: str | None = Field(default=None, description="签到窗口起点 HH:mm")
    WindowEnd: str | None = Field(default=None, description="签到窗口终点 HH:mm")
    RunOnStartup: bool | None = Field(default=None, description="启动时运行")
    ScheduledRun: bool | None = Field(default=None, description="定时运行")
    AutoStart: bool | None = Field(default=None, description="是否立即开始")
    LastSignDate: str | None = Field(default=None, description="上次签到日期")
    ScheduledTime: str | None = Field(default=None, description="今日计划签到时间")
    Status: str | None = Field(default=None, description="签到状态标签")
    Result: str | None = Field(default=None, description="签到结果 JSON")


class GameSignAccountGroupConfig(BaseModel):
    """游戏签到账号组配置"""

    Name: str | None = Field(default=None, description="账号组名称")
    Enabled: bool | None = Field(default=None, description="是否启用")
    MiyousheToken: str | None = Field(default=None, description="米游社登录凭证")
    KuroToken: str | None = Field(default=None, description="库街区登录凭证")
    SklandToken: str | None = Field(default=None, description="森空岛登录凭证")


class GameSignAccountCreateOut(OutBase):
    """游戏签到账号组创建响应"""

    accountId: str = Field(default="", description="账号组 UUID")
    data: GameSignAccountGroupConfig = Field(
        default_factory=GameSignAccountGroupConfig, description="账号组配置"
    )


class GameSignAccountGetIn(BaseModel):
    """游戏签到账号组查询请求"""

    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountsListOut(OutBase):
    """游戏签到账号组列表响应"""

    data: Dict[str, Any] = Field(default_factory=dict, description="账号组列表")


class GameSignAccountUpdateIn(BaseModel):
    """游戏签到账号组更新请求"""

    accountId: str = Field(..., description="账号组 UUID")
    data: GameSignAccountGroupConfig = Field(..., description="账号组配置")


class GameSignAccountDeleteIn(BaseModel):
    """游戏签到账号组删除请求"""

    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountReorderIn(BaseModel):
    """游戏签到账号组排序请求"""

    order: list[str] = Field(..., description="账号组 UUID 顺序列表")


class ToolsConfig(BaseModel):
    ArknightsPC: ToolsConfig_ArknightsPC | None = Field(
        default=None, description="明日方舟PC工具配置"
    )
    GameSign: ToolsConfig_GameSign | None = Field(
        default=None, description="游戏社区签到配置"
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
    IfHideCloseButton: Optional[bool] = Field(
        default=None, description="是否隐藏主窗口关闭按钮"
    )


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
    Source: Optional[Literal["GitHub", "MirrorChyan", "AutoSite", "CNB"]] = Field(
        default=None, description="更新源: GitHub源, Mirror酱源, 自建源, CNB 镜像源"
    )
    Channel: Optional[Literal["stable", "beta"]] = Field(
        default=None, description="更新渠道: 稳定版, 测试版"
    )
    ProxyAddress: Optional[str] = Field(default=None, description="网络代理地址")
    MirrorChyanCDK: Optional[str] = Field(default=None, description="Mirror酱CDK")
    GitHubToken: Optional[str] = Field(default=None, description="GitHub token/API key")


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
            "Logoff",
        ]
    ] = Field(default=None, description="完成后操作")


class QueueConfig(BaseModel):
    Info: Optional[QueueConfig_Info] = Field(default=None, description="队列信息")


class ScriptIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaConfig",
        "GeneralConfig",
        "SrcConfig",
        "MaaEndConfig",
        "M9AConfig",
        "MaaFWConfig",
        "PluginScriptConfig",
    ] = Field(
        ..., description="配置类型"
    )


class UserIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaUserConfig",
        "GeneralUserConfig",
        "SrcUserConfig",
        "MaaEndUserConfig",
        "M9AUserConfig",
        "MaaFWUserConfig",
        "PluginUserConfig",
    ] = Field(..., description="配置类型")


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
    IfScriptBeforeTask: Optional[bool] = Field(
        default=None, description="是否在任务前执行脚本"
    )
    ScriptBeforeTask: Optional[str] = Field(default=None, description="任务前脚本路径")
    IfScriptAfterTask: Optional[bool] = Field(
        default=None, description="是否在任务后执行脚本"
    )
    ScriptAfterTask: Optional[str] = Field(default=None, description="任务后脚本路径")
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
    Tag: Optional[str] = Field(default=None, description="状态标签列表")


class MaaUserConfig_Data(BaseModel):
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
    IfDepotMaintain: Optional[bool] = Field(default=None, description="库存保持")
    DepotMaintainPlans: Optional[str] = Field(
        default=None, description="库存保持计划 JSON"
    )


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
    AnnihilationAvoidWaste: Optional[bool] = Field(
        default=None, description="剿灭避免无代理卡浪费理智"
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
    Tag: Optional[str] = Field(
        default=None, description="用户标签列表（JSON字符串，TagItem的dict列表）"
    )


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


class MaaEndUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名")
    Status: Optional[bool] = Field(default=None, description="用户状态")
    Id: Optional[str] = Field(default=None, description="用户ID")
    Password: Optional[str] = Field(default=None, description="密码")
    Mode: Optional[Literal["简洁", "详细"]] = Field(
        default=None, description="配置文件来源"
    )
    IfQuickConfig: Optional[bool] = Field(default=None, description="是否启用快速配置")
    SanityMode: Optional[str] = Field(default=None, description="理智任务配置模式")
    Resource: Optional[Literal["官服"]] = Field(default=None, description="资源名称")
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
    IfSkland: Optional[bool] = Field(default=None, description="是否启用森空岛签到")
    SklandToken: Optional[str] = Field(default=None, description="SklandToken")
    Tag: Optional[str] = Field(default=None, description="用户标签信息")


class MaaEndUserConfig_Task(BaseModel):
    SanityTaskType: Optional[
        Literal["OperatorProgression", "WeaponProgression", "CrisisDrills", "Essence"]
    ] = Field(default=None, description="理智任务类型")
    OperatorProgression: Optional[
        Literal["OperatorEXP", "Promotions", "T-Creds", "SkillUp"]
    ] = Field(default=None, description="干员养成任务")
    WeaponProgression: Optional[Literal["WeaponEXP", "WeaponTune"]] = Field(
        default=None, description="武器养成任务"
    )
    CrisisDrills: Optional[
        Literal[
            "AdvancedProgression1",
            "AdvancedProgression2",
            "AdvancedProgression3",
            "AdvancedProgression4",
            "AdvancedProgression5",
        ]
    ] = Field(default=None, description="危境预演任务")
    RewardsSetOption: Optional[Literal["RewardsSetA", "RewardsSetB"]] = Field(
        default=None, description="奖励组选项"
    )
    AutoEssenceSpecifiedLocation: Optional[
        Literal[
            "VFTheHub",
            "VFOriginiumSciencePark",
            "VFOriginLodespring",
            "VFPowerPlateau",
            "WLWulingCity",
            "WLQingboStockade",
            "WLMarkerStone",
        ]
    ] = Field(default=None, description="基质刷取指定地点")
    IfSanity: Optional[bool] = Field(default=None, description="理智任务")
    IfAutoUseSpMedication: Optional[bool] = Field(
        default=None, description="应急理智加强剂"
    )
    IfDijiangRewards: Optional[bool] = Field(default=None, description="基建任务")
    IfDeliveryJobs: Optional[bool] = Field(default=None, description="转交委托")
    IfSellProduct: Optional[bool] = Field(default=None, description="售卖产品")
    IfAutoStockpile: Optional[bool] = Field(default=None, description="自动囤货")
    IfAutoStockStaple: Optional[bool] = Field(default=None, description="购买稳定物资")
    IfVisitFriends: Optional[bool] = Field(default=None, description="拜访好友")
    IfCreditShoppingN2: Optional[bool] = Field(default=None, description="信用点购物")
    IfSeizeEntrustTask: Optional[bool] = Field(default=None, description="抢委托")
    IfAutoEcoFarm: Optional[bool] = Field(default=None, description="生态农场")
    IfAutoSell: Optional[bool] = Field(default=None, description="售卖弹性物资")
    IfEnvironmentMonitoring: Optional[bool] = Field(
        default=None, description="环境监测"
    )
    IfAutoCollect: Optional[bool] = Field(default=None, description="自动采集")
    IfDailyRewards: Optional[bool] = Field(default=None, description="日常奖励领取")
    IfResourceRecycleStation: Optional[bool] = Field(
        default=None, description="资源回收站"
    )


class MaaEndUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件")
    ToAddress: Optional[str] = Field(default=None, description="收件地址")
    IfServerChan: Optional[bool] = Field(default=None, description="是否启用Server酱")
    ServerChanKey: Optional[str] = Field(default=None, description="Server酱密钥")


class MaaEndUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")
    LastProxyStatus: Optional[Literal["未知", "成功", "失败"]] = Field(
        default=None, description="上次代理状态"
    )
    LastSklandDate: Optional[str] = Field(default=None, description="上次森空岛签到日期")
    IfPassCheck: Optional[bool] = Field(default=None, description="是否通过检查")


class MaaEndUserConfig(BaseModel):
    Info: Optional[MaaEndUserConfig_Info] = Field(default=None, description="用户信息")
    Task: Optional[MaaEndUserConfig_Task] = Field(default=None, description="任务配置")
    Data: Optional[MaaEndUserConfig_Data] = Field(default=None, description="运行数据")
    Notify: Optional[MaaEndUserConfig_Notify] = Field(
        default=None, description="通知配置"
    )


class MaaEndConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="脚本名称")
    Path: Optional[str] = Field(default=None, description="脚本路径")


class MaaEndConfig_Run(BaseModel):
    RunTimeLimit: Optional[int] = Field(
        default=None, description="运行时间限制（分钟）"
    )
    ProxyTimesLimit: Optional[int] = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="重试次数限制")


class MaaEndConfig_Game(BaseModel):
    ControllerType: Optional[Literal["Win32-Front", "ADB"]] = Field(
        default=None, description="控制器类型"
    )
    Path: Optional[str] = Field(default=None, description="终末地客户端路径")
    Arguments: Optional[str] = Field(default=None, description="游戏启动参数")
    WaitTime: Optional[int] = Field(default=None, ge=60, description="游戏等待时间")
    EmulatorId: Optional[str] = Field(default=None, description="模拟器ID")
    EmulatorIndex: Optional[str] = Field(default=None, description="模拟器索引")
    CloseOnFinish: Optional[bool] = Field(default=None, description="结束后关闭游戏")


class MaaEndConfig(BaseModel):
    Info: Optional[MaaEndConfig_Info] = Field(default=None, description="脚本信息")
    Run: Optional[MaaEndConfig_Run] = Field(default=None, description="运行配置")
    Game: Optional[MaaEndConfig_Game] = Field(default=None, description="游戏配置")


class SrcUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名称")
    Status: Optional[bool] = Field(default=None, description="是否启用")
    Id: Optional[str] = Field(default=None, description="用户ID")
    Password: Optional[str] = Field(default=None, description="密码")
    Mode: Optional[Literal["简洁", "详细"]] = Field(
        default=None, description="脚本模式"
    )
    Server: Optional[
        Literal[
            "CN-Official",
            "CN-Bilibili",
            "VN-Official",
            "OVERSEA-America",
            "OVERSEA-Asia",
            "OVERSEA-Europe",
            "OVERSEA-TWHKMO",
        ]
    ] = Field(default=None, description="游戏服务器")
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
    Tag: Optional[str] = Field(default=None, description="用户标签信息")


class SrcUserConfig_Stage(BaseModel):
    Channel: Literal["Relic", "Materials", "Ornament"] | None = Field(
        default=None, description="关卡通道"
    )
    Relic: (
        Literal[
            "-",
            "Cavern_of_Corrosion_Path_of_Possession",
            "Cavern_of_Corrosion_Path_of_Hidden_Salvation",
            "Cavern_of_Corrosion_Path_of_Thundersurge",
            "Cavern_of_Corrosion_Path_of_Aria",
            "Cavern_of_Corrosion_Path_of_Uncertainty",
            "Cavern_of_Corrosion_Path_of_Cavalier",
            "Cavern_of_Corrosion_Path_of_Dreamdive",
            "Cavern_of_Corrosion_Path_of_Darkness",
            "Cavern_of_Corrosion_Path_of_Elixir_Seekers",
            "Cavern_of_Corrosion_Path_of_Conflagration",
            "Cavern_of_Corrosion_Path_of_Holy_Hymn",
            "Cavern_of_Corrosion_Path_of_Providence",
            "Cavern_of_Corrosion_Path_of_Drifting",
            "Cavern_of_Corrosion_Path_of_Jabbing_Punch",
            "Cavern_of_Corrosion_Path_of_Gelid_Wind",
        ]
        | None
    ) = Field(default=None, description="遗器关卡")
    Materials: (
        Literal[
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
        | None
    ) = Field(default=None, description="材料关卡")
    Ornament: (
        Literal[
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
        | None
    ) = Field(default=None, description="饰品关卡")
    ExtractReservedTrailblazePower: Optional[bool] = Field(
        default=None, description="使用储备开拓力"
    )
    UseFuel: Optional[bool] = Field(default=None, description="使用燃料")
    FuelReserve: Optional[int] = Field(default=None, description="保留的燃料数量")
    EchoOfWar: Optional[str] = Field(default=None, description="历战余响关卡")
    SimulatedUniverseWorld: Optional[str] = Field(
        default=None, description="模拟宇宙关卡"
    )


class SrcUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")
    IfPassCheck: Optional[bool] = Field(default=None, description="是否通过检查")


class SrcUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件")
    ToAddress: Optional[str] = Field(default=None, description="收件地址")
    IfServerChan: Optional[bool] = Field(default=None, description="是否启用Server酱")
    ServerChanKey: Optional[str] = Field(default=None, description="Server酱密钥")


class SrcUserConfig(BaseModel):
    Info: Optional[SrcUserConfig_Info] = Field(default=None, description="基础信息")
    Stage: Optional[SrcUserConfig_Stage] = Field(default=None, description="关卡配置")
    Data: Optional[SrcUserConfig_Data] = Field(default=None, description="用户数据")
    Notify: Optional[SrcUserConfig_Notify] = Field(default=None, description="单独通知")


class SrcConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="SRC脚本名称")
    Path: Optional[str] = Field(default=None, description="SRC路径")


class SrcConfig_Emulator(BaseModel):
    Id: Optional[str] = Field(default=None, description="模拟器ID")
    Index: Optional[str] = Field(default=None, description="模拟器索引")


class SrcConfig_Run(BaseModel):
    TaskTransitionMethod: Optional[Literal["ExitGame", "ExitEmulator"]] = Field(
        default=None, description="任务切换方式"
    )
    ProxyTimesLimit: Optional[int] = Field(default=None, description="代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="运行次数限制")
    RunTimeLimit: Optional[int] = Field(
        default=None, description="运行时间限制（分钟）"
    )


class SrcConfig(BaseModel):
    Info: Optional[SrcConfig_Info] = Field(default=None, description="脚本基础信息")
    Emulator: Optional[SrcConfig_Emulator] = Field(
        default=None, description="模拟器配置"
    )
    Run: Optional[SrcConfig_Run] = Field(default=None, description="脚本运行配置")


class M9AUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名称")
    Status: Optional[bool] = Field(default=None, description="是否启用")
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
    Tag: Optional[str] = Field(default=None, description="用户标签信息")
    Resource: Optional[str] = Field(default=None, description="服务器资源名称")
    Account: Optional[str] = Field(default=None, description="账号信息（用于切换账号，仅官服生效）")


class M9AUserConfig_Task(BaseModel):
    AvailableTasks: Optional[Union[str, List]] = Field(default=None, description="可用任务列表 JSON 数组字符串或数组")
    Queue: Optional[Union[str, List]] = Field(default=None, description="运行任务队列 JSON 数组字符串或数组")

class M9AUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    LastPsychubeDate: Optional[str] = Field(default=None, description="上次完成每日心相日期，格式 YYYY-MM-DD")
    LastLimboMonth: Optional[str] = Field(default=None, description="上次完成自动深眠月份，格式 YYYY-MM")
    LastLucidscapeMonth: Optional[str] = Field(default=None, description="上次完成自动醒梦月份，格式 YYYY-MM")
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")
    IfPassCheck: Optional[bool] = Field(default=None, description="是否通过检查")


class M9AUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件")
    ToAddress: Optional[str] = Field(default=None, description="收件地址")
    IfServerChan: Optional[bool] = Field(default=None, description="是否启用 Server 酱")
    ServerChanKey: Optional[str] = Field(default=None, description="Server 酱密钥")


class M9AUserConfig(BaseModel):
    Info: Optional[M9AUserConfig_Info] = Field(default=None, description="基础信息")
    Task: Optional[M9AUserConfig_Task] = Field(default=None, description="任务配置")
    Data: Optional[M9AUserConfig_Data] = Field(default=None, description="用户数据")
    Notify: Optional[M9AUserConfig_Notify] = Field(default=None, description="单独通知")


class M9AConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="M9A 脚本名称")
    Path: Optional[str] = Field(default=None, description="M9A 路径")


class M9AConfig_Emulator(BaseModel):
    Id: Optional[str] = Field(default=None, description="模拟器 ID")
    Index: Optional[str] = Field(default=None, description="模拟器索引")


class M9AConfig_Run(BaseModel):
    ProxyTimesLimit: Optional[int] = Field(default=None, description="代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="运行次数限制")
    RunTimeLimit: Optional[int] = Field(default=None, description="运行时间限制（分钟）")
    IfAutoUpdateAfterQueue: Optional[bool] = Field(default=None, description="是否在队列结束后自动更新M9A")
    IfPsychubeDailyOnce: Optional[bool] = Field(default=None, description="每日心相每日只执行一次")
    IfSleepDreamMonthlyOnce: Optional[bool] = Field(default=None, description="深眠浅梦每月只执行一次")


class M9AConfig(BaseModel):
    Info: Optional[M9AConfig_Info] = Field(default=None, description="脚本基础信息")
    Emulator: Optional[M9AConfig_Emulator] = Field(default=None, description="模拟器配置")
    Run: Optional[M9AConfig_Run] = Field(default=None, description="脚本运行配置")


class MaaFWUserConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="用户名称")
    Status: Optional[bool] = Field(default=None, description="是否启用")
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
    Tag: Optional[str] = Field(default=None, description="用户标签信息")
    Account: Optional[str] = Field(
        default=None, description="账号信息，仅用于 AUTO-MAS 记录"
    )
    Password: Optional[str] = Field(
        default=None, description="密码信息，仅用于 AUTO-MAS 记录"
    )


class MaaFWUserConfig_Task(BaseModel):
    SelectedPreset: Optional[str] = Field(default=None, description="选中的 interface preset")
    TaskSnapshot: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None, description="任务快照 JSON 字符串或对象"
    )


class MaaFWUserConfig_Device(BaseModel):
    AdbAddress: Optional[str] = Field(default=None, description="用户覆盖 ADB 地址")
    HWnd: Optional[int] = Field(default=None, description="窗口句柄")
    PlayCoverAddress: Optional[str] = Field(default=None, description="PlayCover 地址")
    PlayCoverUuid: Optional[str] = Field(default=None, description="PlayCover UUID")


class MaaFWUserConfig_Data(BaseModel):
    LastProxyDate: Optional[str] = Field(default=None, description="上次代理日期")
    ProxyTimes: Optional[int] = Field(default=None, description="代理次数")
    IfPassCheck: Optional[bool] = Field(default=None, description="是否通过检查")
    LastProxyStatus: Optional[str] = Field(default=None, description="上次运行状态")
    PeriodTaskRecords: Optional[str] = Field(
        default=None, description="MaaFW 周期任务完成记录"
    )


class MaaFWUserConfig_Notify(BaseModel):
    Enabled: Optional[bool] = Field(default=None, description="是否启用通知")
    IfSendStatistic: Optional[bool] = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: Optional[bool] = Field(default=None, description="是否发送邮件")
    ToAddress: Optional[str] = Field(default=None, description="收件地址")
    IfServerChan: Optional[bool] = Field(default=None, description="是否启用 Server 酱")
    ServerChanKey: Optional[str] = Field(default=None, description="Server 酱密钥")


class MaaFWUserConfig(BaseModel):
    Info: Optional[MaaFWUserConfig_Info] = Field(default=None, description="基础信息")
    Task: Optional[MaaFWUserConfig_Task] = Field(default=None, description="任务配置")
    Device: Optional[MaaFWUserConfig_Device] = Field(default=None, description="设备覆盖配置")
    Data: Optional[MaaFWUserConfig_Data] = Field(default=None, description="用户数据")
    Notify: Optional[MaaFWUserConfig_Notify] = Field(default=None, description="单独通知")


class MaaFWConfig_Info(BaseModel):
    Name: Optional[str] = Field(default=None, description="MaaFW 脚本名称")
    ProjectLabel: Optional[str] = Field(default=None, description="MaaFW 项目显示标签")
    Path: Optional[str] = Field(default=None, description="MaaFW 项目根目录")
    Controller: Optional[str] = Field(default=None, description="MaaFW controller 名称")
    Resource: Optional[str] = Field(default=None, description="MaaFW resource 名称")


class MaaFWConfig_Emulator(BaseModel):
    Id: Optional[str] = Field(default=None, description="模拟器 ID")
    Index: Optional[str] = Field(default=None, description="模拟器索引")


class MaaFWConfig_Device(BaseModel):
    AdbPath: Optional[str] = Field(default=None, description="ADB 路径")
    AdbAddress: Optional[str] = Field(default=None, description="ADB 地址")
    AdbScreencapMethods: Optional[int] = Field(default=None, description="ADB 截图方法")
    AdbInputMethods: Optional[int] = Field(default=None, description="ADB 输入方法")
    HWnd: Optional[int] = Field(default=None, description="窗口句柄")
    Win32ScreencapMethod: Optional[int] = Field(default=None, description="Win32 截图方法")
    Win32MouseMethod: Optional[int] = Field(default=None, description="Win32 鼠标方法")
    Win32KeyboardMethod: Optional[int] = Field(default=None, description="Win32 键盘方法")
    GamepadType: Optional[int] = Field(default=None, description="Gamepad 类型")
    PlayCoverAddress: Optional[str] = Field(default=None, description="PlayCover 地址")
    PlayCoverUuid: Optional[str] = Field(default=None, description="PlayCover UUID")


class MaaFWConfig_Game(BaseModel):
    Path: Optional[str] = Field(default=None, description="桌面控制器使用的实际游戏可执行文件路径")
    Arguments: Optional[str] = Field(default=None, description="游戏启动参数")
    WaitTime: Optional[int] = Field(default=None, description="游戏启动后等待窗口就绪的时间（秒）")
    CloseOnFinish: Optional[bool] = Field(
        default=None, description="任务结束后是否关闭由 MAS 启动的游戏"
    )


class MaaFWConfig_Update(BaseModel):
    IfAutoUpdate: Optional[bool] = Field(default=None, description="是否在运行前自动更新 MaaFW 项目")
    Source: Optional[Literal["MirrorChyan"]] = Field(
        default=None, description="项目更新源，暂仅支持 MirrorChyan"
    )
    Channel: Optional[Literal["", "stable", "beta"]] = Field(
        default=None, description="项目更新渠道，留空时使用全局更新渠道"
    )
    MirrorChyanCDK: Optional[str] = Field(
        default=None, description="Mirror 酱 CDK，留空时使用全局项目更新 CDK"
    )


class MaaFWConfig_Run(BaseModel):
    ProxyTimesLimit: Optional[int] = Field(default=None, description="代理次数限制")
    RunTimesLimit: Optional[int] = Field(default=None, description="运行次数限制")
    RunTimeLimit: Optional[int] = Field(default=None, description="运行时间限制（分钟）")
    DailyOnceTasks: Optional[str] = Field(
        default=None, description="每日正常完成一次后今日跳过的 MaaFW 任务名列表"
    )
    WeeklyOnceTasks: Optional[str] = Field(
        default=None, description="每周正常完成一次后本周跳过的 MaaFW 任务名列表"
    )
    MonthlyOnceTasks: Optional[str] = Field(
        default=None, description="每月正常完成一次后本月跳过的 MaaFW 任务名列表"
    )


class MaaFWConfig(BaseModel):
    Info: Optional[MaaFWConfig_Info] = Field(default=None, description="脚本基础信息")
    Emulator: Optional[MaaFWConfig_Emulator] = Field(default=None, description="模拟器配置")
    Device: Optional[MaaFWConfig_Device] = Field(default=None, description="设备配置")
    Game: Optional[MaaFWConfig_Game] = Field(default=None, description="游戏生命周期配置")
    Update: Optional[MaaFWConfig_Update] = Field(default=None, description="项目更新配置")
    Run: Optional[MaaFWConfig_Run] = Field(default=None, description="脚本运行配置")


class MaaFWProjectUpdateIn(BaseModel):
    scriptId: str = Field(..., description="MaaFW 脚本 ID")


class MaaFWProjectUpdateData(BaseModel):
    checked: bool = Field(..., description="是否完成更新检查")
    updated: bool = Field(..., description="是否实际更新了 MaaFW 项目资源")
    currentVersion: str = Field(..., description="更新前的项目版本")
    latestVersion: Optional[str] = Field(default=None, description="最新项目版本")
    source: Optional[str] = Field(default=None, description="实际使用的更新源")
    logs: List[str] = Field(default_factory=list, description="项目更新日志")


class MaaFWProjectUpdateOut(OutBase):
    data: Optional[MaaFWProjectUpdateData] = Field(default=None, description="MaaFW 项目更新结果")


class MaaFWInterfacePreviewIn(BaseModel):
    path: str = Field(..., description="MaaFW 项目根目录，应包含 interface.json")


class MaaFWAdbEmulatorExtraCapabilityInfo(BaseModel):
    screencap: bool = Field(default=False, description="MaaFW ADB EmulatorExtras screencap")
    input: bool = Field(default=False, description="MaaFW ADB EmulatorExtras input")


class MaaFWControlCapabilitiesInfo(BaseModel):
    emulatorExtras: Dict[str, MaaFWAdbEmulatorExtraCapabilityInfo] = Field(
        default_factory=dict,
        description="MaaFW ADB EmulatorExtras capabilities by emulator type",
    )


class MaaFWProjectInfo(BaseModel):
    name: str = Field(..., description="项目标识")
    label: Optional[str] = Field(default=None, description="项目显示名称")
    title: Optional[str] = Field(default=None, description="项目标题")
    version: Optional[str] = Field(default=None, description="项目版本")
    github: Optional[str] = Field(default=None, description="项目 GitHub 地址")
    mirrorchyanRid: Optional[str] = Field(default=None, description="MirrorChyan RID")
    mirrorchyanMultiplatform: Optional[bool] = Field(
        default=None, description="MirrorChyan 是否多平台"
    )
    description: Optional[str] = Field(default=None, description="项目描述")
    icon: Optional[str] = Field(default=None, description="项目图标路径")


class MaaFWControllerInfo(BaseModel):
    name: str = Field(..., description="控制器名称")
    label: Optional[str] = Field(default=None, description="控制器显示名称")
    type: str = Field(..., description="控制器类型")
    description: Optional[str] = Field(default=None, description="控制器描述")
    icon: Optional[str] = Field(default=None, description="控制器图标路径")
    option: List[str] = Field(default_factory=list, description="控制器选项")
    permissionRequired: bool = Field(default=False, description="是否需要管理员权限")


class MaaFWResourceInfo(BaseModel):
    name: str = Field(..., description="资源名称")
    label: Optional[str] = Field(default=None, description="资源显示名称")
    description: Optional[str] = Field(default=None, description="资源描述")
    icon: Optional[str] = Field(default=None, description="资源图标路径")
    path: List[str] = Field(default_factory=list, description="资源路径列表")
    controller: List[str] = Field(default_factory=list, description="适用控制器列表")
    option: List[str] = Field(default_factory=list, description="资源选项")


class MaaFWGroupInfo(BaseModel):
    name: str = Field(..., description="任务分组名称")
    label: Optional[str] = Field(default=None, description="任务分组显示名称")
    description: Optional[str] = Field(default=None, description="任务分组描述")
    icon: Optional[str] = Field(default=None, description="任务分组图标路径")
    defaultExpand: bool = Field(default=True, description="是否默认展开")


class MaaFWTaskInfo(BaseModel):
    name: str = Field(..., description="任务名称")
    label: Optional[str] = Field(default=None, description="任务显示名称")
    entry: str = Field(..., description="MaaFW pipeline 入口")
    description: Optional[str] = Field(default=None, description="任务描述")
    icon: Optional[str] = Field(default=None, description="任务图标路径")
    group: List[str] = Field(default_factory=list, description="所属分组")
    controller: List[str] = Field(default_factory=list, description="适用控制器")
    resource: List[str] = Field(default_factory=list, description="适用资源")
    option: List[str] = Field(default_factory=list, description="任务选项")
    defaultCheck: bool = Field(default=False, description="是否默认勾选")


class MaaFWOptionCaseInfo(BaseModel):
    name: str = Field(..., description="选项 case 名称")
    label: Optional[str] = Field(default=None, description="选项 case 显示名称")
    description: Optional[str] = Field(default=None, description="选项 case 描述")
    icon: Optional[str] = Field(default=None, description="选项 case 图标路径")
    option: List[str] = Field(default_factory=list, description="子选项列表")


class MaaFWOptionInputInfo(BaseModel):
    name: str = Field(..., description="输入项名称")
    label: Optional[str] = Field(default=None, description="输入项显示名称")
    description: Optional[str] = Field(default=None, description="输入项描述")
    icon: Optional[str] = Field(default=None, description="输入项图标路径")
    default: Optional[str] = Field(default=None, description="默认值")
    pipelineType: Optional[str] = Field(default=None, description="pipeline 覆盖值类型")
    verify: Optional[str] = Field(default=None, description="输入校验正则")
    verifyError: Optional[str] = Field(default=None, description="输入校验提示")
    patternMsg: Optional[str] = Field(default=None, description="输入校验提示")


class MaaFWOptionInfo(BaseModel):
    name: str = Field(..., description="选项名称")
    type: str = Field(..., description="选项类型")
    label: Optional[str] = Field(default=None, description="选项显示名称")
    description: Optional[str] = Field(default=None, description="选项描述")
    icon: Optional[str] = Field(default=None, description="选项图标路径")
    controller: List[str] = Field(default_factory=list, description="适用控制器")
    resource: List[str] = Field(default_factory=list, description="适用资源")
    cases: List[MaaFWOptionCaseInfo] = Field(default_factory=list, description="可选 case")
    inputs: List[MaaFWOptionInputInfo] = Field(default_factory=list, description="输入项")
    defaultCase: Optional[Union[str, List[str]]] = Field(
        default=None, description="默认 case"
    )


class MaaFWTaskSnapshot(BaseModel):
    taskOrder: List[str] = Field(default_factory=list, description="任务 name 顺序")
    taskChecked: Dict[str, bool] = Field(default_factory=dict, description="任务勾选状态")
    taskOptions: Dict[str, Dict[str, Union[str, List[str], Dict[str, str]]]] = Field(
        default_factory=dict, description="任务选项值"
    )


class MaaFWPresetInfo(BaseModel):
    name: str = Field(..., description="预设名称")
    label: Optional[str] = Field(default=None, description="预设显示名称")
    description: Optional[str] = Field(default=None, description="预设描述")
    taskCount: int = Field(default=0, description="预设声明任务数")
    checkedCount: int = Field(default=0, description="转换后勾选任务数")
    snapshot: MaaFWTaskSnapshot = Field(..., description="预设转换后的任务快照")


class MaaFWInterfacePreviewData(BaseModel):
    path: str = Field(..., description="MaaFW 项目根目录")
    project: MaaFWProjectInfo = Field(..., description="项目基础信息")
    globalOption: List[str] = Field(default_factory=list, description="全局选项")
    controlCapabilities: MaaFWControlCapabilitiesInfo = Field(
        default_factory=MaaFWControlCapabilitiesInfo,
        description="MaaFW control capabilities",
    )
    controllers: List[MaaFWControllerInfo] = Field(default_factory=list, description="控制器列表")
    resources: List[MaaFWResourceInfo] = Field(default_factory=list, description="资源列表")
    groups: List[MaaFWGroupInfo] = Field(default_factory=list, description="任务分组列表")
    tasks: List[MaaFWTaskInfo] = Field(default_factory=list, description="任务列表")
    options: List[MaaFWOptionInfo] = Field(default_factory=list, description="选项列表")
    presets: List[MaaFWPresetInfo] = Field(default_factory=list, description="预设列表")
    importCount: int = Field(default=0, description="根 interface import 数量")
    agentCount: int = Field(default=0, description="agent 配置数量")


class MaaFWInterfacePreviewOut(OutBase):
    data: Optional[MaaFWInterfacePreviewData] = Field(
        default=None, description="MaaFW interface 预览数据"
    )


class MaaFWAgentEnvPrepareIn(BaseModel):
    path: str = Field(..., description="MaaFW project root path")


class MaaFWAgentEnvInfo(BaseModel):
    childExec: str = Field(..., description="Agent child_exec declared by interface")
    executable: str = Field(..., description="Actual executable used by agent")
    runtimeKind: Optional[str] = Field(default=None, description="Agent runtime kind")
    isolatedVenvPath: Optional[str] = Field(default=None, description="Isolated venv path")
    fallbackReason: Optional[str] = Field(default=None, description="Agent runtime fallback reason")


class MaaFWAgentEnvPrepareData(BaseModel):
    path: str = Field(..., description="MaaFW project root path")
    agentCount: int = Field(default=0, description="Agent count")
    agents: List[MaaFWAgentEnvInfo] = Field(default_factory=list, description="Agent env info")
    logs: List[str] = Field(default_factory=list, description="Preparation logs")


class MaaFWAgentEnvPrepareOut(OutBase):
    data: Optional[MaaFWAgentEnvPrepareData] = Field(
        default=None, description="MaaFW agent Python env preparation result"
    )


class MaaFWWindowPreviewIn(BaseModel):
    path: str = Field(..., description="MaaFW 项目根目录，应包含 interface.json")
    controllerName: Optional[str] = Field(
        default=None, description="指定 controller 名称；留空时扫描全部 Win32 controller"
    )


class MaaFWDesktopWindowInfo(BaseModel):
    hWnd: int = Field(..., description="窗口句柄")
    className: str = Field(default="", description="窗口类名")
    windowName: str = Field(default="", description="窗口标题")
    controllerName: str = Field(..., description="匹配到的 controller 名称")
    controllerType: str = Field(..., description="匹配到的 controller 类型")


class MaaFWWindowPreviewData(BaseModel):
    path: str = Field(..., description="MaaFW 项目根目录")
    controllerName: Optional[str] = Field(default=None, description="请求指定的 controller 名称")
    windows: List[MaaFWDesktopWindowInfo] = Field(
        default_factory=list, description="匹配到的桌面窗口"
    )


class MaaFWWindowPreviewOut(OutBase):
    data: Optional[MaaFWWindowPreviewData] = Field(
        default=None, description="MaaFW 桌面窗口预览数据"
    )


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
    matrix_statistics: Optional[Dict[str, str]] = Field(
        default=None, description="基质统计数据, key为技能组合, value为符合武器名称"
    )
    error_info: Optional[Dict[str, str]] = Field(
        default=None, description="报错信息, key为时间戳, value为错误描述"
    )
    log_content: Optional[str] = Field(
        default=None, description="日志内容, 仅在提取单条历史记录数据时返回"
    )


class ScriptCreateIn(BaseModel):
    type: Literal[
        "MAA",
        "SRC",
        "General",
        "Okww",
        "MaaEnd",
        "M9A",
        "MaaFW",
    ] = Field(
        ..., description="脚本类型: MAA脚本, 通用脚本, OK-WW脚本, SRC脚本, MaaEnd脚本, M9A脚本, MaaFW脚本"
    )
    scriptId: str | None = Field(
        default=None, description="直接从该脚本ID复制创建, 仅在复制创建时使用"
    )


class PluginScriptConfig(BaseModel):
    Meta: Optional[Dict[str, Any]] = Field(default=None, description="插件脚本元数据")
    Info: Optional[Dict[str, Any]] = Field(default=None, description="插件脚本基本信息")
    PluginData: Optional[Dict[str, Any]] = Field(default=None, description="插件脚本存储数据")


class PluginUserConfig(BaseModel):
    Meta: Optional[Dict[str, Any]] = Field(default=None, description="插件用户元数据")
    Info: Optional[Dict[str, Any]] = Field(default=None, description="插件用户基本信息")
    PluginData: Optional[Dict[str, Any]] = Field(default=None, description="插件用户存储数据")


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Union[
        MaaConfig,
        SrcConfig,
        GeneralConfig,
        MaaEndConfig,
        M9AConfig,
        MaaFWConfig,
        PluginScriptConfig,
    ] = Field(
        ..., description="脚本配置数据"
    )


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: List[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: Dict[
        str,
        Union[
            MaaConfig,
            SrcConfig,
            GeneralConfig,
            MaaEndConfig,
            M9AConfig,
            MaaFWConfig,
            PluginScriptConfig,
        ],
    ] = Field(
        ..., description="脚本数据字典, key来自于index列表的uid"
    )


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Union[
        MaaConfig,
        SrcConfig,
        GeneralConfig,
        MaaEndConfig,
        M9AConfig,
        MaaFWConfig,
        PluginScriptConfig,
    ] = Field(
        ..., description="脚本更新数据"
    )


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


class ScriptConfigImportIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时导入到脚本级配置文件"
    )


class UserGetIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时表示获取所有用户数据"
    )


class UserGetOut(OutBase):
    index: List[UserIndexItem] = Field(..., description="用户索引列表")
    data: Dict[
        str,
        Union[
            MaaUserConfig,
            SrcUserConfig,
            GeneralUserConfig,
            MaaEndUserConfig,
            M9AUserConfig,
            MaaFWUserConfig,
            PluginUserConfig,
        ],
    ] = Field(..., description="用户数据字典, key来自于index列表的uid")


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Union[
        MaaUserConfig,
        SrcUserConfig,
        GeneralUserConfig,
        MaaEndUserConfig,
        M9AUserConfig,
        MaaFWUserConfig,
        PluginUserConfig,
    ] = (
        Field(..., description="用户配置数据")
    )


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Union[
        MaaUserConfig,
        SrcUserConfig,
        GeneralUserConfig,
        MaaEndUserConfig,
        M9AUserConfig,
        MaaFWUserConfig,
        PluginUserConfig,
    ] = (
        Field(..., description="用户更新数据")
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
    resumeFromScriptId: str | None = Field(
        default=None,
        description="可选：仅对队列任务生效；从指定脚本ID开始执行（之前的脚本将被标记为跳过）",
    )


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class PluginMarketItem(BaseModel):
    """插件市场中的一个 PyPI 项目。"""

    package: str = Field(..., description="PyPI 包名")
    version: str = Field(default="", description="最新版本")
    summary: str = Field(default="", description="项目简介")
    project_url: str = Field(..., description="PyPI 项目页")
    prefix_tag: str = Field(..., description="匹配到的 AUTO-MAS 包名前缀")


class PluginMarketSnapshot(BaseModel):
    """插件市场 HTTP 初始快照。"""

    schema_version: Literal[1] = Field(default=1, description="快照结构版本")
    prefix_tags: List[str] = Field(default_factory=list, description="支持的包名前缀")
    fetched_at: str = Field(..., description="UTC ISO-8601 拉取时间")
    items: List[PluginMarketItem] = Field(default_factory=list, description="市场项目")
    installed_map: Dict[str, bool] = Field(
        default_factory=dict, description="包名到本地安装状态的映射"
    )
    total: int = Field(ge=0, description="项目总数")


class WSEnvelope(BaseModel):
    """主 WebSocket 统一消息信封, 前后端均按 id + type 路由"""

    id: str = Field(
        ...,
        description="路由ID, 标识任务、请求或业务会话, 如 Main、TaskManager、任务UUID",
    )
    type: str = Field(
        ...,
        description="消息类别, 点分小写命名, 如 task.info.updated、backend.shutdown.ready",
    )
    data: Dict[str, JsonValue] = Field(
        default_factory=dict, description="消息数据, 关键消息使用对应的 WS*Data 模型构造"
    )

    @field_validator("id", "type")
    @classmethod
    def validate_route_field(cls, value: str) -> str:
        """路由字段必须为非空字符串，并统一去除首尾空白。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("WebSocket 路由 id/type 不能为空")
        return normalized


class WSTaskNoticeData(BaseModel):
    """任务提示消息数据 (type=task.notice)"""

    level: Literal["info", "warning", "error"] = Field(..., description="提示级别")
    message: str = Field(..., description="提示内容")


class WSTaskUserInfoData(BaseModel):
    """任务快照中的用户状态。"""

    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="用户名称")
    status: str = Field(..., description="用户执行状态")


class WSTaskScriptInfoData(BaseModel):
    """任务快照中的脚本状态。"""

    script_id: str = Field(..., description="脚本 ID")
    name: str = Field(..., description="脚本名称")
    status: str = Field(..., description="脚本执行状态")
    userList: List[WSTaskUserInfoData] = Field(
        default_factory=list, description="脚本下的用户状态"
    )


class WSTaskInfoUpdatedData(BaseModel):
    """任务信息全量快照 (type=task.info.updated)。"""

    task_info: List[WSTaskScriptInfoData] = Field(
        default_factory=list, description="任务脚本与用户状态"
    )


class WSTaskLogUpdatedData(BaseModel):
    """任务当前日志 (type=task.log.updated)。"""

    log: str = Field(default="", description="当前脚本日志")


class WSTaskScriptIdentityData(BaseModel):
    """任务关联的脚本静态标识。"""

    scriptId: str = Field(..., description="脚本 ID")
    scriptType: str = Field(..., description="脚本类型键")


class TaskRuntimeSnapshotItem(BaseModel):
    """一个运行中任务的 HTTP 初始快照。"""

    taskId: str = Field(..., description="任务 ID")
    mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"] = Field(
        ..., description="任务模式"
    )
    queueId: Optional[str] = Field(default=None, description="调度队列 ID")
    scriptId: Optional[str] = Field(default=None, description="脚本 ID")
    userId: Optional[str] = Field(default=None, description="用户 ID")
    stopping: bool = Field(default=False, description="任务是否正在停止")
    scripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="任务关联的脚本静态标识"
    )
    task_info: List[WSTaskScriptInfoData] = Field(
        default_factory=list, description="任务脚本与用户状态"
    )
    log: str = Field(default="", description="当前脚本日志")


class TaskRuntimeSnapshot(BaseModel):
    """任务运行与定时队列 HTTP 初始快照。"""

    tasks: List[TaskRuntimeSnapshotItem] = Field(default_factory=list)
    scheduledScripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="已启用定时队列关联的脚本静态标识"
    )


class WSTaskCompletedData(BaseModel):
    """任务完成消息数据 (type=task.completed)"""

    result: str = Field(..., description="任务结果描述")
    outcome: Literal["success", "error", "cancelled"] = Field(
        ..., description="机器可读的任务结果"
    )
    error: Optional[str] = Field(default=None, description="任务错误信息")
    task_info: List[WSTaskScriptInfoData] = Field(
        ..., description="任务信息全量快照"
    )


class WSTaskCreatedData(BaseModel):
    """新任务创建通知数据 (id=TaskManager, type=task.created)"""

    taskId: str = Field(..., description="新任务ID")
    mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"] = Field(
        ..., description="任务模式"
    )
    scripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="任务关联的脚本静态标识"
    )
    queueId: Optional[str] = Field(default=None, description="所属调度队列ID")
    taskName: Optional[str] = Field(default=None, description="任务名称")
    taskType: Optional[str] = Field(default=None, description="任务类型")


class WSPowerCountdownData(BaseModel):
    """电源倒计时更新数据 (id=Main, type=power.countdown.updated)"""

    operation: str = Field(..., description="待执行的电源操作")
    remaining: int = Field(..., description="剩余秒数")


class PowerCountdownSnapshot(BaseModel):
    """当前电源倒计时 HTTP 初始快照。"""

    active: bool = Field(default=False, description="是否正在倒计时")
    operation: Optional[str] = Field(default=None, description="待执行电源操作")
    remaining: int = Field(default=0, ge=0, description="剩余秒数")


class WSPowerSignData(BaseModel):
    """电源标志更新数据 (id=Main, type=power.sign.updated)"""

    signal: str = Field(..., description="电源操作信号")


class WSDialogRequestData(BaseModel):
    """应用内弹窗请求数据 (id=Main, type=dialog.request)"""

    requestId: str = Field(..., description="弹窗请求ID, 响应使用相同ID关联")
    taskId: Optional[str] = Field(default=None, description="关联的任务ID")
    title: str = Field(..., description="弹窗标题")
    message: str = Field(..., description="弹窗内容")
    options: List[str] = Field(default_factory=lambda: ["是", "否"], description="选项文案")


class WSDialogResponseData(BaseModel):
    """应用内弹窗响应数据 (id=Main, type=dialog.response)"""

    requestId: str = Field(..., description="对应弹窗请求ID")
    choice: bool = Field(..., description="用户是否选择第一个选项")


class WSUpdateProgressData(BaseModel):
    """更新下载进度数据 (id=Update, type=update.progress)"""

    downloaded_size: int = Field(..., description="已下载字节数")
    file_size: int = Field(..., description="文件总字节数")
    speed: float = Field(..., description="下载速度 (B/s)")
    source: str = Field(..., description="下载源")


class WSUpdateCompletedData(BaseModel):
    """更新下载完成数据 (id=Update, type=update.completed)。"""

    file: str = Field(..., description="已下载更新包路径")


class WSUpdateFailedData(BaseModel):
    """更新下载失败数据 (id=Update, type=update.failed)。"""

    message: str = Field(..., description="失败原因")


class UpdateDownloadSnapshot(BaseModel):
    """更新下载 HTTP 初始快照。"""

    status: Literal[
        "idle",
        "downloading",
        "switchingSource",
        "completed",
        "failed",
        "cancelled",
    ] = Field(default="idle")
    version: Optional[str] = Field(default=None, description="当前下载版本")
    source: Optional[str] = Field(default=None, description="当前下载源")
    downloaded_size: int = Field(default=0, ge=0)
    file_size: int = Field(default=0, ge=0)
    speed: float = Field(default=0, ge=0)
    file: Optional[str] = Field(default=None, description="完成后的更新包路径")
    message: Optional[str] = Field(default=None, description="失败或状态说明")


class WSPluginPackageRequestData(BaseModel):
    """插件市场安装、卸载或状态查询请求。"""

    requestId: Optional[str] = Field(default=None, description="会话内请求关联 ID")
    package: str = Field(default="", description="PyPI 包名")


class WSPluginInstallProgressData(BaseModel):
    """插件安装进度事件。"""

    requestId: Optional[str] = Field(default=None, description="会话内请求关联 ID")
    status: Literal["success", "error"] = Field(default="success")
    message: str = Field(default="")
    package: str = Field(..., description="PyPI 包名")
    progress: int = Field(ge=0, le=100, description="安装进度百分比")
    stage: Literal["queued", "installing", "completed"] = Field(
        ..., description="安装阶段"
    )


class WSPluginOperationResultData(BaseModel):
    """插件安装或卸载结果事件。"""

    requestId: Optional[str] = Field(default=None, description="会话内请求关联 ID")
    status: Literal["success", "error"] = Field(default="success")
    message: str = Field(default="")
    package: str = Field(..., description="PyPI 包名")
    success: bool = Field(..., description="操作是否成功")


class WSPluginInstalledSyncData(BaseModel):
    """插件本地安装状态同步事件。"""

    requestId: Optional[str] = Field(default=None, description="会话内请求关联 ID")
    status: Literal["success", "error"] = Field(default="success")
    message: str = Field(default="")
    package: str = Field(..., description="PyPI 包名")
    installed: bool = Field(..., description="当前是否已安装")


class WSMarketErrorData(BaseModel):
    """插件市场 WS 实时操作错误。"""

    requestId: Optional[str] = Field(default=None, description="会话内请求关联 ID")
    status: Literal["error"] = Field(default="error")
    message: str = Field(..., description="错误原因")


class PowerIn(BaseModel):
    signal: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
        "Logoff",
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
        "Logoff",
    ] = Field(..., description="电源操作信号")


class ToolsGetOut(OutBase):
    data: ToolsConfig = Field(..., description="工具配置数据")


class ToolsUpdateIn(BaseModel):
    data: ToolsConfig = Field(..., description="工具配置需要更新的数据")


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
