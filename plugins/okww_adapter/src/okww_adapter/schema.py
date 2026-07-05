from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.plugins.fields import PluginField


class PluginConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class Config(PluginConfig):
    """Plugin instance config entrypoint."""


class OkwwInfoConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    Name: str = PluginField(
        default="新 OK-WW 脚本",
        title="脚本名称",
        json_schema_extra={"size": "half"},
    )
    RootPath: str = PluginField(
        default="",
        title="ok-ww 路径",
        placeholder="请选择 ok-ww.exe 所在目录",
        ui_type="path",
        path_kind="folder",
        required=True,
        json_schema_extra={"size": "large"},
    )


class OkwwGameConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Enabled: bool = PluginField(
        default=False,
        title="启用游戏管理",
        description="任务开始前可由 MAS 启动鸣潮客户端。",
        json_schema_extra={"size": "half"},
    )
    CloseOnManualStop: bool = PluginField(
        default=False,
        title="手动终止时关闭游戏",
        json_schema_extra={"size": "half"},
    )
    Path: str = PluginField(
        default="",
        title="鸣潮游戏路径",
        placeholder="请选择 Client-Win64-Shipping.exe",
        ui_type="path",
        path_kind="file",
        json_schema_extra={"size": "large"},
    )
    Arguments: str = PluginField(
        default="",
        title="游戏启动参数",
        json_schema_extra={"size": "large"},
    )
    WaitTime: int = PluginField(
        default=60,
        title="等待启动时间",
        min=0,
        max=9999,
        json_schema_extra={"size": "half"},
    )


class OkwwRunConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    ProxyTimesLimit: int = PluginField(
        default=0,
        title="每日代理次数限制",
        min=0,
        max=9999,
        json_schema_extra={"size": "half"},
    )
    RunTimesLimit: int = PluginField(
        default=1,
        title="失败重试次数",
        min=1,
        max=9999,
        json_schema_extra={"size": "half"},
    )
    RunTimeLimit: int = PluginField(
        default=60,
        title="单次运行超时",
        min=1,
        max=9999,
        json_schema_extra={"size": "half"},
    )


class OkwwConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    Info: OkwwInfoConfig = PluginField(
        default_factory=OkwwInfoConfig,
        title="基础信息",
    )
    Game: OkwwGameConfig = PluginField(
        default_factory=OkwwGameConfig,
        title="游戏配置",
    )
    Run: OkwwRunConfig = PluginField(
        default_factory=OkwwRunConfig,
        title="运行配置",
    )


class OkwwUserInfoConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    Name: str = PluginField(
        default="新用户",
        title="用户名称",
        validator="username",
        json_schema_extra={"size": "half"},
    )
    Status: bool = PluginField(
        default=True,
        title="启用用户",
        json_schema_extra={"size": "half"},
    )
    Id: str = PluginField(default="", title="账号", json_schema_extra={"size": "half"})
    Password: str = PluginField(
        default="",
        title="密码",
        format="password",
        sensitive=True,
        json_schema_extra={"size": "half"},
    )
    Resource: Literal["官服"] = PluginField(
        default="官服",
        title="服务器",
        json_schema_extra={"size": "half"},
    )
    RemainedDay: int = PluginField(
        default=-1,
        title="剩余天数",
        min=-1,
        max=9999,
        json_schema_extra={"size": "half"},
    )
    Mode: Literal["简洁", "详细"] = PluginField(
        default="详细",
        title="配置模式",
        readonly=True,
        json_schema_extra={"size": "half"},
    )
    IfScriptBeforeTask: bool = PluginField(
        default=False,
        title="启用前置脚本",
        json_schema_extra={"size": "half"},
    )
    ScriptBeforeTask: str = PluginField(
        default="",
        title="前置脚本",
        ui_type="path",
        path_kind="file",
        json_schema_extra={"size": "large"},
    )
    IfScriptAfterTask: bool = PluginField(
        default=False,
        title="启用后置脚本",
        json_schema_extra={"size": "half"},
    )
    ScriptAfterTask: str = PluginField(
        default="",
        title="后置脚本",
        ui_type="path",
        path_kind="file",
        json_schema_extra={"size": "large"},
    )
    Notes: str = PluginField(
        default="无",
        title="备注",
        format="textarea",
        rows=3,
        json_schema_extra={"size": "large"},
    )


class OkwwUserTaskConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    TaskIndex: int = PluginField(
        default=1,
        title="任务序号",
        min=1,
        max=8,
        help="与 ok-ww 任务列表的 -t 序号一致。",
        json_schema_extra={"size": "half"},
    )


class OkwwUserDataConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    LastProxyDate: str = PluginField(
        default="2000-01-01",
        title="上次代理日期",
        readonly=True,
        json_schema_extra={"size": "half"},
    )
    ProxyTimes: int = PluginField(
        default=0,
        title="今日代理次数",
        min=0,
        max=9999,
        readonly=True,
        json_schema_extra={"size": "half"},
    )
    LastProxyStatus: Literal["未知", "成功", "失败"] = PluginField(
        default="未知",
        title="上次代理状态",
        readonly=True,
        json_schema_extra={"size": "half"},
    )
    LastTaskIndex: int = PluginField(
        default=0,
        title="上次任务序号",
        min=0,
        max=9999,
        readonly=True,
        json_schema_extra={"size": "half"},
    )


class OkwwUserNotifyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    Enabled: bool = PluginField(default=False, title="启用单独通知")
    IfSendStatistic: bool = PluginField(default=False, title="发送统计")
    IfSendMail: bool = PluginField(default=False, title="发送邮件")
    ToAddress: str = PluginField(default="", title="收件地址")
    IfServerChan: bool = PluginField(default=False, title="启用 ServerChan")
    ServerChanKey: str = PluginField(default="", title="ServerChan Key", sensitive=True)
    CustomWebhooks: dict[str, Any] = PluginField(
        default="{}",
        title="自定义 Webhook",
        ui_type="json",
        json_type="object",
    )


class OkwwUserConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    Info: OkwwUserInfoConfig = PluginField(
        default_factory=OkwwUserInfoConfig,
        title="基础信息",
    )
    Task: OkwwUserTaskConfig = PluginField(
        default_factory=OkwwUserTaskConfig,
        title="任务配置",
    )
    Data: OkwwUserDataConfig = PluginField(
        default_factory=OkwwUserDataConfig,
        title="用户数据",
    )
    Notify: OkwwUserNotifyConfig = PluginField(
        default_factory=OkwwUserNotifyConfig,
        title="单独通知",
    )
