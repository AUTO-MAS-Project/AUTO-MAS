from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.plugins.fields import PluginField


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Config(_ConfigModel):
    pass


class PluginConfig(_ConfigModel):
    """ok-script 插件实例配置。"""


class Config(PluginConfig):
    """插件实例配置入口。"""


class OkScriptInfo(_ConfigModel):
    Name: str = PluginField(default="ok-script 项目", title="脚本名称")
    ResourceName: str = PluginField(default="", title="资源名", readonly=True)
    ProjectLabel: str = PluginField(default="", title="项目标签", readonly=True)
    RootPath: str = PluginField(
        default="",
        title="项目目录",
        placeholder="请选择 ok-script 项目根目录",
        ui_type="path",
        path_kind="folder",
        required=True,
        json_schema_extra={"size": "large"},
    )


class OkScriptGame(_ConfigModel):
    Enabled: bool = PluginField(default=True, title="启用游戏管理")
    LaunchBeforeTask: bool = PluginField(default=True, title="任务前启动游戏")
    Path: str = PluginField(
        default="",
        title="游戏程序路径",
        ui_type="path",
        path_kind="file",
        json_schema_extra={"size": "large"},
    )
    Arguments: str = PluginField(default="", title="游戏启动参数")
    WaitTime: int = PluginField(default=60, title="等待启动时间", min=0, max=9999)
    KillGameOnManualStop: bool = PluginField(
        default=True, title="手动终止任务时关闭游戏"
    )


class OkScriptRun(_ConfigModel):
    ProxyTimesLimit: int = PluginField(default=0, title="每日代理次数限制", min=0, max=9999)
    RunTimesLimit: int = PluginField(default=1, title="失败重试次数", min=1, max=9999)
    RunTimeLimit: int = PluginField(default=60, title="单次运行超时（分钟）", min=1, max=9999)


class OkScriptConfig(_ConfigModel):
    Info: OkScriptInfo = PluginField(default_factory=OkScriptInfo, title="基础信息")
    Game: OkScriptGame = PluginField(default_factory=OkScriptGame, title="游戏配置")
    Run: OkScriptRun = PluginField(default_factory=OkScriptRun, title="运行配置")


class OkScriptUserInfo(_ConfigModel):
    Name: str = PluginField(default="新用户", title="用户名", validator="username")
    Status: bool = PluginField(default=True, title="启用用户")
    RemainedDay: int = PluginField(default=-1, title="剩余天数", min=-1, max=9999)
    IfScriptBeforeTask: bool = PluginField(default=False, title="启用前置脚本")
    ScriptBeforeTask: str = PluginField(default="", title="前置脚本", ui_type="path", path_kind="file")
    IfScriptAfterTask: bool = PluginField(default=False, title="启用后置脚本")
    ScriptAfterTask: str = PluginField(default="", title="后置脚本", ui_type="path", path_kind="file")
    Notes: str = PluginField(default="无", title="备注", format="textarea", rows=3)


class OkScriptUserTask(_ConfigModel):
    TaskIndex: int = PluginField(default=1, title="任务序号", min=1, max=9999)


class OkScriptUserData(_ConfigModel):
    LastProxyDate: str = PluginField(default="2000-01-01", title="上次代理日期", readonly=True)
    ProxyTimes: int = PluginField(default=0, title="今日代理次数", readonly=True)
    LastProxyStatus: str = PluginField(default="未知", title="上次代理状态", readonly=True)
    LastTaskIndex: int = PluginField(default=0, title="上次任务序号", readonly=True)


class OkScriptUserNotify(_ConfigModel):
    Enabled: bool = PluginField(default=False, title="启用单独通知")
    IfSendStatistic: bool = PluginField(default=False, title="发送统计")
    IfSendMail: bool = PluginField(default=False, title="发送邮件")
    ToAddress: str = PluginField(default="", title="收件地址")
    IfServerChan: bool = PluginField(default=False, title="启用 ServerChan")
    ServerChanKey: str = PluginField(default="", title="ServerChan Key", sensitive=True)
    CustomWebhooks: dict[str, Any] = PluginField(default_factory=dict, title="自定义 Webhook", ui_type="json")


class OkScriptUserConfig(_ConfigModel):
    Info: OkScriptUserInfo = PluginField(default_factory=OkScriptUserInfo, title="基础信息")
    Task: OkScriptUserTask = PluginField(default_factory=OkScriptUserTask, title="任务配置")
    Data: OkScriptUserData = PluginField(default_factory=OkScriptUserData, title="用户数据")
    Notify: OkScriptUserNotify = PluginField(default_factory=OkScriptUserNotify, title="单独通知")
