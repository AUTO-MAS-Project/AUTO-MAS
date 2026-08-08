from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

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
    Path: str = PluginField(
        default="",
        title="鸣潮启动器路径",
        placeholder="请选择 launcher.exe 或 WeGame.exe",
        ui_type="path",
        path_kind="file",
        filters=[
            {"name": "鸣潮启动器", "extensions": ["exe"]},
        ],
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
    Resource: Literal["官服", "国际服"] = PluginField(
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
        default="简洁",
        title="配置模式",
        help="简洁模式共享一份设置；详细模式为当前用户保存独立设置。",
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

    TaskIndex: Literal[1, 7] = PluginField(
        default=1,
        title="启动任务",
        option_labels={1: "DailyTask（日常任务）", 7: "MultiAccountDailyTask（多账号日常）"},
        help="启动参数固定为 -t N -e。",
        json_schema_extra={"size": "half"},
    )
    WhichToFarm: Literal[
        "Tacet Suppression", "Forgery Challenge", "Simulation Challenge"
    ] = PluginField(
        default="Tacet Suppression",
        title="每日任务体力用途",
        option_labels={
            "Tacet Suppression": "无音区",
            "Forgery Challenge": "凝素领域",
            "Simulation Challenge": "模拟领域",
        },
        json_schema_extra={"size": "half"},
    )
    WhichTacetSuppressionToFarm: int = PluginField(
        default=1,
        title="无音区序号",
        min=1,
        max=99,
        json_schema_extra={
            "size": "half",
            "disabled_when": {"field": "Task.WhichToFarm", "not_equals": "Tacet Suppression"},
        },
    )
    WhichForgeryChallengeToFarm: int = PluginField(
        default=1,
        title="凝素领域序号",
        min=1,
        max=99,
        json_schema_extra={
            "size": "half",
            "disabled_when": {"field": "Task.WhichToFarm", "not_equals": "Forgery Challenge"},
        },
    )
    MaterialSelection: Literal["Resonator EXP", "Weapon EXP", "Shell Credit"] = PluginField(
        default="Shell Credit",
        title="模拟领域材料",
        option_labels={
            "Resonator EXP": "共鸣者经验",
            "Weapon EXP": "武器经验",
            "Shell Credit": "贝币",
        },
        json_schema_extra={
            "size": "half",
            "disabled_when": {"field": "Task.WhichToFarm", "not_equals": "Simulation Challenge"},
        },
    )
    FarmNightmareNestForDailyEcho: bool = PluginField(
        default=True,
        title="使用梦魇巢穴完成日常声骸",
        json_schema_extra={"size": "half"},
    )
    AdditionalTasks: list[
        Literal[
            "Check Weekly Garden",
            "Auto Farm all Nightmare Nest",
            "Merge Echo If discarded > 1000",
            "Teleport and Farm 4C Echo",
        ]
    ] = PluginField(
        default_factory=lambda: ["Check Weekly Garden"],
        title="每日任务后运行的附加任务",
        options=[
            "Check Weekly Garden",
            "Auto Farm all Nightmare Nest",
            "Merge Echo If discarded > 1000",
            "Teleport and Farm 4C Echo",
        ],
        option_labels={
            "Check Weekly Garden": "检查周常苗圃",
            "Auto Farm all Nightmare Nest": "自动刷取全部梦魇巢穴",
            "Merge Echo If discarded > 1000": "废弃声骸超过 1000 时合成",
            "Teleport and Farm 4C Echo": "传送并刷取 4C 声骸",
        },
        item_type="string",
        json_schema_extra={"size": "large"},
    )

    @field_validator("TaskIndex", mode="before")
    @classmethod
    def normalize_task_index(cls, value: Any) -> int:
        try:
            task_index = int(value)
        except (TypeError, ValueError):
            return 1
        if task_index == 2:
            return 7
        return task_index if task_index in (1, 7) else 1


class OkwwUserActionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Configure: bool = PluginField(
        default=False,
        title="ok-ww 设置",
        ui_type="action",
        configurable=False,
        action={
            "label": "打开 ok-ww 设置",
            "icon": "SettingOutlined",
            "path": "/api/dispatch/start",
            "method": "POST",
            "payload": {"taskId": "{{userId}}", "mode": "ScriptConfig"},
            "session": {
                "stop_path": "/api/dispatch/stop",
                "stop_method": "POST",
                "stop_payload": {"taskId": "{{session.taskId}}"},
                "overlay_title": "正在配置 ok-ww",
                "overlay_description": "请在 ok-ww 窗口中保存设置，然后回到这里结束会话。",
                "stop_label": "保存并结束",
                "start_message": "已打开 ok-ww 设置",
                "stop_message": "ok-ww 设置已保存",
                "timeout_ms": 1800000,
                "timeout_auto_stop": True,
                "timeout_message": "ok-ww 设置会话已超时，正在保存并结束",
            },
        },
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
    Action: OkwwUserActionConfig = PluginField(
        default_factory=OkwwUserActionConfig,
        title="操作",
    )
    Data: OkwwUserDataConfig = PluginField(
        default_factory=OkwwUserDataConfig,
        title="用户数据",
    )
    Notify: OkwwUserNotifyConfig = PluginField(
        default_factory=OkwwUserNotifyConfig,
        title="单独通知",
    )
