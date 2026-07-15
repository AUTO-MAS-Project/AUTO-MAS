from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.plugins.fields import PluginField
from app.utils.constants import UTC4, UTC8


class HSRModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class HSRInfoConfig(HSRModel):
    Name: str = PluginField(default="新 HSR 脚本", title="脚本名称")


class HSRSRAConfig(HSRModel):
    Path: str = PluginField(
        default="",
        title="SRA 路径",
        ui_type="path",
        path_kind="folder",
    )


class HSRM7AConfig(HSRModel):
    Path: str = PluginField(
        default="",
        title="三月七助手路径",
        ui_type="path",
        path_kind="folder",
    )
    LowPerformanceMode: bool = PluginField(
        default=False,
        title="低性能兼容模式",
        help="仅用于三月七助手差分宇宙稳定模式。",
    )


class HSRGameConfig(HSRModel):
    Path: str = PluginField(
        default="",
        title="游戏路径",
        ui_type="path",
        path_kind="file",
    )
    Arguments: str = PluginField(default="", title="游戏启动参数")
    WaitTime: int = PluginField(
        default=60,
        title="等待启动时间（秒）",
        min=0,
        max=9999,
    )


class HSRRunConfig(HSRModel):
    RunTimesLimit: int = PluginField(
        default=3,
        title="失败任务最大尝试次数",
        min=1,
        max=9999,
    )
    DailyTimeLimit: int = PluginField(
        default=20,
        title="日常任务超时（分钟）",
        min=1,
        max=9999,
    )
    WeeklyTimeLimit: int = PluginField(
        default=60,
        title="周常任务超时（分钟）",
        min=1,
        max=9999,
    )


class HSRTaskMappingConfig(HSRModel):
    Daily: Literal["SRA", "M7A"] = PluginField(default="SRA", title="日常")
    ReceiveRewards: Literal["SRA", "M7A"] = PluginField(
        default="SRA",
        title="领取奖励",
    )
    DivergentUniverse: Literal["SRA", "M7A"] = PluginField(
        default="SRA",
        title="差分宇宙",
    )
    CurrencyWars: Literal["SRA", "M7A"] = PluginField(
        default="SRA",
        title="货币战争",
    )


class HSRConfig(HSRModel):
    Info: HSRInfoConfig = PluginField(default_factory=HSRInfoConfig, title="基础信息")
    SRA: HSRSRAConfig = PluginField(default_factory=HSRSRAConfig, title="SRA")
    M7A: HSRM7AConfig = PluginField(default_factory=HSRM7AConfig, title="三月七助手")
    Game: HSRGameConfig = PluginField(default_factory=HSRGameConfig, title="游戏配置")
    Run: HSRRunConfig = PluginField(default_factory=HSRRunConfig, title="运行配置")
    TaskMapping: HSRTaskMappingConfig = PluginField(
        default_factory=HSRTaskMappingConfig,
        title="任务引擎映射",
    )


def build_hsr_tags(config: Any) -> str:
    """根据 HSR 用户配置生成列表标签。"""

    tags: list[dict[str, str]] = []
    if not bool(config.get("Data", "IfPassCheck")):
        tags.append({"text": "人工排查未通过", "color": "red"})

    tags.append({"text": "服务器：官服", "color": "blue"})
    try:
        proxied_today = (
            datetime.strptime(config.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
            == datetime.now(tz=UTC4).date()
        )
    except (TypeError, ValueError):
        proxied_today = False
    tags.append(
        {
            "text": (
                f"日常：已代理{config.get('Data', 'ProxyTimes')}次"
                if proxied_today
                else "日常：未代理"
            ),
            "color": "green" if proxied_today else "orange",
        }
    )

    remained_day = int(config.get("Info", "RemainedDay") or 0)
    if remained_day == -1:
        remained_color = "gold"
    elif remained_day == 0:
        remained_color = "red"
    elif remained_day <= 3:
        remained_color = "orange"
    elif remained_day <= 7:
        remained_color = "yellow"
    elif remained_day <= 30:
        remained_color = "blue"
    else:
        remained_color = "green"
    tags.append(
        {
            "text": (
                f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无期限"
            ),
            "color": remained_color,
        }
    )

    now = datetime.now(tz=UTC8)
    iso_year, iso_week, _ = now.isocalendar()
    current_week = f"{iso_year:04d}-W{iso_week:02d}"
    eow_done = bool(config.get("Data", "EchoOfWarCompletedThisWeek")) and (
        config.get("Data", "EchoOfWarLastResetWeek") == current_week
    )
    weekly_done = bool(config.get("Data", "WeeklyCompletedThisWeek")) and (
        config.get("Data", "WeeklyLastResetWeek") == current_week
    )
    if weekly_done:
        if bool(config.get("TaskSwitch", "DivergentUniverse")):
            weekly_text = "差分宇宙 已完成"
        elif bool(config.get("TaskSwitch", "CurrencyWars")):
            weekly_text = "货币战争 已完成"
        else:
            weekly_text = "周常 已完成"
        weekly_color = "green"
    else:
        weekly_text = "周常：未完成"
        weekly_color = "orange"
    tags.extend(
        [
            {
                "text": "历战余响：已完成" if eow_done else "历战余响：未完成",
                "color": "green" if eow_done else "orange",
            },
            {
                "text": weekly_text,
                "color": weekly_color,
            },
        ]
    )
    notes = str(config.get("Info", "Notes") or "")
    tags.append(
        {
            "text": f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}...",
            "color": "pink",
        }
    )
    return json.dumps(tags, ensure_ascii=False)


class HSRUserInfoConfig(HSRModel):
    Name: str = PluginField(default="新用户", title="用户名称", validator="username")
    Status: bool = PluginField(default=True, title="启用用户")
    Server: Literal["CN-Official"] = PluginField(default="CN-Official", title="服务器")
    RemainedDay: int = PluginField(default=-1, title="剩余天数", min=-1, max=9999)
    Notes: str = PluginField(default="无", title="备注", format="textarea", rows=3)
    Tag: str = PluginField(
        default="[]",
        title="用户标签",
        readonly=True,
        hidden=True,
        virtual_handler=build_hsr_tags,
    )


class HSRUserSRAConfig(HSRModel):
    Id: str = PluginField(
        default="",
        title="账号",
        format="password",
        sensitive=True,
    )
    Password: str = PluginField(
        default="",
        title="密码",
        format="password",
        sensitive=True,
    )


class HSRUserDataConfig(HSRModel):
    LastProxyDate: str = PluginField(default="2000-01-01", title="上次代理日期")
    ProxyTimes: int = PluginField(default=0, title="今日代理次数", min=0, max=9999)
    IfPassCheck: bool = PluginField(default=True, title="人工排查是否通过")
    EchoOfWarCompletedThisWeek: bool = PluginField(default=False, title="历战余响本周完成")
    EchoOfWarLastResetWeek: str = PluginField(default="2000-W01", title="历战余响重置周")
    EchoOfWarLastCompletionDate: str = PluginField(default="2000-01-01", title="历战余响完成日期")
    WeeklyLastCompletionDate: str = PluginField(default="2000-01-01", title="周常完成日期")
    WeeklyCompletedThisWeek: bool = PluginField(default=False, title="周常本周完成")
    WeeklyLastResetWeek: str = PluginField(default="2000-W01", title="周常重置周")


class HSRUserTaskSwitchConfig(HSRModel):
    Daily: bool = PluginField(default=True, title="日常")
    ReceiveRewards: bool = PluginField(default=True, title="领取奖励")
    DivergentUniverse: bool = PluginField(default=False, title="差分宇宙")
    CurrencyWars: bool = PluginField(default=False, title="货币战争")


class HSRUserStageConfig(HSRModel):
    Channel: Literal["CalyxGolden", "CalyxCrimson", "Relic", "Ornament"] = PluginField(
        default="CalyxGolden",
        title="关卡通道",
    )
    ScriptStage: dict[str, Any] = PluginField(
        default_factory=dict,
        title="主刷关卡",
        ui_type="json",
        json_type="object",
    )
    ScriptEchoOfWar: dict[str, Any] = PluginField(
        default_factory=dict,
        title="历战余响关卡",
        ui_type="json",
        json_type="object",
    )


class HSRUserTaskOptConfig(HSRModel):
    EchoOfWarWeekday: Literal[
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ] = PluginField(default="Monday", title="历战余响开始星期")


class HSRUserNotifyConfig(HSRModel):
    Enabled: bool = PluginField(default=False, title="启用通知")
    IfSendStatistic: bool = PluginField(default=False, title="发送统计")
    IfSendMail: bool = PluginField(default=False, title="发送邮件")
    ToAddress: str = PluginField(default="", title="收件地址")
    IfServerChan: bool = PluginField(default=False, title="启用 ServerChan")
    ServerChanKey: str = PluginField(default="", title="ServerChan Key", sensitive=True)
    CustomWebhooks: dict[str, Any] = PluginField(
        default_factory=dict,
        title="自定义 Webhook",
        ui_type="json",
        json_type="object",
    )


class HSRUserConfig(HSRModel):
    Info: HSRUserInfoConfig = PluginField(default_factory=HSRUserInfoConfig, title="基础信息")
    SRA: HSRUserSRAConfig = PluginField(default_factory=HSRUserSRAConfig, title="SRA 账号")
    Data: HSRUserDataConfig = PluginField(default_factory=HSRUserDataConfig, title="运行状态")
    TaskSwitch: HSRUserTaskSwitchConfig = PluginField(
        default_factory=HSRUserTaskSwitchConfig,
        title="任务开关",
    )
    Stage: HSRUserStageConfig = PluginField(default_factory=HSRUserStageConfig, title="关卡配置")
    TaskOpt: HSRUserTaskOptConfig = PluginField(default_factory=HSRUserTaskOptConfig, title="任务选项")
    Notify: HSRUserNotifyConfig = PluginField(default_factory=HSRUserNotifyConfig, title="通知")
