from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel


class GeneralUserConfigNotify(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用通知")
    IfSendStatistic: bool | None = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: bool | None = Field(default=None, description="是否发送邮件通知")
    ToAddress: str | None = Field(default=None, description="邮件接收地址")
    IfServerChan: bool | None = Field(
        default=None, description="是否使用Server酱推送"
    )
    ServerChanKey: str | None = Field(default=None, description="ServerChanKey")


class GeneralUserConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="用户名")
    Status: bool | None = Field(default=None, description="用户状态")
    RemainedDay: int | None = Field(default=None, description="剩余天数")
    IfScriptBeforeTask: bool | None = Field(
        default=None, description="是否在任务前执行脚本"
    )
    ScriptBeforeTask: str | None = Field(default=None, description="任务前脚本路径")
    IfScriptAfterTask: bool | None = Field(
        default=None, description="是否在任务后执行脚本"
    )
    ScriptAfterTask: str | None = Field(default=None, description="任务后脚本路径")
    Notes: str | None = Field(default=None, description="备注")
    Tag: str | None = Field(
        default=None, description="用户标签列表（JSON字符串，TagItem的dict列表）"
    )


class GeneralUserConfigData(ApiModel):
    LastProxyDate: str | None = Field(default=None, description="上次代理日期")
    ProxyTimes: int | None = Field(default=None, description="代理次数")


class GeneralUserConfig(ApiModel):
    type: Literal["GeneralUserConfig"] = Field(
        default="GeneralUserConfig", description="配置类型"
    )
    Info: GeneralUserConfigInfo | None = Field(default=None, description="用户信息")
    Data: GeneralUserConfigData | None = Field(default=None, description="用户数据")
    Notify: GeneralUserConfigNotify | None = Field(
        default=None, description="单独通知"
    )


class GeneralConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="脚本名称")
    RootPath: str | None = Field(default=None, description="脚本根目录")


class GeneralConfigScript(ApiModel):
    ScriptPath: str | None = Field(default=None, description="脚本可执行文件路径")
    Arguments: str | None = Field(default=None, description="脚本启动附加命令参数")
    IfTrackProcess: bool | None = Field(
        default=None, description="是否追踪脚本子进程"
    )
    TrackProcessName: str | None = Field(default=None, description="追踪进程名称")
    TrackProcessExe: str | None = Field(default=None, description="追踪进程文件路径")
    TrackProcessCmdline: str | None = Field(
        default=None, description="追踪进程启动命令行参数"
    )
    ConfigPath: str | None = Field(default=None, description="配置文件路径")
    ConfigPathMode: Literal["File", "Folder"] | None = Field(
        default=None, description="配置文件类型: 单个文件, 文件夹"
    )
    UpdateConfigMode: Literal["Never", "Success", "Failure", "Always"] | None = Field(
        default=None,
        description="更新配置时机, 从不, 仅成功时, 仅失败时, 任务结束时",
    )
    LogPath: str | None = Field(default=None, description="日志文件路径")
    LogPathFormat: str | None = Field(default=None, description="日志文件名格式")
    LogTimeStart: int | None = Field(default=None, description="日志时间戳开始位置")
    LogTimeEnd: int | None = Field(default=None, description="日志时间戳结束位置")
    LogTimeFormat: str | None = Field(default=None, description="日志时间戳格式")
    SuccessLog: str | None = Field(default=None, description="成功时日志")
    ErrorLog: str | None = Field(default=None, description="错误时日志")


class GeneralConfigGame(ApiModel):
    Enabled: bool | None = Field(default=None, description="游戏/模拟器相关功能是否启用")
    Type: Literal["Emulator", "Client", "URL"] | None = Field(
        default=None, description="类型: 模拟器, PC端, URL协议"
    )
    Path: str | None = Field(default=None, description="游戏/模拟器程序路径")
    URL: str | None = Field(default=None, description="自定义协议URL")
    ProcessName: str | None = Field(default=None, description="游戏进程名称")
    Arguments: str | None = Field(default=None, description="游戏/模拟器启动参数")
    WaitTime: int | None = Field(default=None, description="游戏/模拟器等待启动时间")
    IfForceClose: bool | None = Field(
        default=None, description="是否强制关闭游戏/模拟器进程"
    )
    EmulatorId: str | None = Field(default=None, description="模拟器ID")
    EmulatorIndex: str | None = Field(default=None, description="模拟器多开实例索引")


class GeneralConfigRun(ApiModel):
    ProxyTimesLimit: int | None = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: int | None = Field(default=None, description="重试次数限制")
    RunTimeLimit: int | None = Field(default=None, description="日志超时限制")


class GeneralConfig(ApiModel):
    type: Literal["GeneralConfig"] = Field(default="GeneralConfig", description="配置类型")
    Info: GeneralConfigInfo | None = Field(default=None, description="脚本基础信息")
    Script: GeneralConfigScript | None = Field(default=None, description="脚本配置")
    Game: GeneralConfigGame | None = Field(default=None, description="游戏配置")
    Run: GeneralConfigRun | None = Field(default=None, description="运行配置")


__all__ = [
    "GeneralUserConfigNotify",
    "GeneralUserConfigInfo",
    "GeneralUserConfigData",
    "GeneralUserConfig",
    "GeneralConfigInfo",
    "GeneralConfigScript",
    "GeneralConfigGame",
    "GeneralConfigRun",
    "GeneralConfig",
]
