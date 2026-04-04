from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel


class MaaEndUserConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="用户名")
    Status: bool | None = Field(default=None, description="用户状态")
    Id: str | None = Field(default=None, description="用户ID")
    Password: str | None = Field(default=None, description="密码")
    Mode: Literal["简洁", "详细"] | None = Field(
        default=None, description="配置模式"
    )
    Resource: Literal["官服"] | None = Field(default=None, description="资源名称")
    RemainedDay: int | None = Field(default=None, description="剩余天数")
    Notes: str | None = Field(default=None, description="备注")
    IfSkland: bool | None = Field(default=None, description="是否启用森空岛签到")
    SklandToken: str | None = Field(default=None, description="SklandToken")
    Tag: str | None = Field(default=None, description="用户标签信息")


class MaaEndUserConfigTask(ApiModel):
    ProtocolSpaceTab: Literal[
        "OperatorProgression", "WeaponProgression", "CrisisDrills"
    ] | None = Field(default=None, description="协议空间选项卡")
    OperatorProgression: Literal[
        "OperatorEXP", "Promotions", "T-Creds", "SkillUp"
    ] | None = Field(default=None, description="干员养成任务")
    WeaponProgression: Literal["WeaponEXP", "WeaponTune"] | None = Field(
        default=None, description="武器养成任务"
    )
    CrisisDrills: Literal[
        "AdvancedProgression1",
        "AdvancedProgression2",
        "AdvancedProgression3",
        "AdvancedProgression4",
        "AdvancedProgression5",
    ] | None = Field(default=None, description="危境预演任务")
    RewardsSetOption: Literal["RewardsSetA", "RewardsSetB"] | None = Field(
        default=None, description="奖励套组选项"
    )


class MaaEndUserConfigNotify(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用通知")
    IfSendStatistic: bool | None = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: bool | None = Field(default=None, description="是否发送邮件")
    ToAddress: str | None = Field(default=None, description="收件地址")
    IfServerChan: bool | None = Field(default=None, description="是否启用Server酱")
    ServerChanKey: str | None = Field(default=None, description="Server酱密钥")


class MaaEndUserConfig(ApiModel):
    type: Literal["MaaEndUserConfig"] = Field(
        default="MaaEndUserConfig", description="配置类型"
    )
    Info: MaaEndUserConfigInfo | None = Field(default=None, description="用户信息")
    Task: MaaEndUserConfigTask | None = Field(default=None, description="任务配置")
    Notify: MaaEndUserConfigNotify | None = Field(
        default=None, description="通知配置"
    )


class MaaEndConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="脚本名称")
    Path: str | None = Field(default=None, description="脚本路径")


class MaaEndConfigRun(ApiModel):
    RunTimeLimit: int | None = Field(default=None, description="运行时间限制（分钟）")
    ProxyTimesLimit: int | None = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: int | None = Field(default=None, description="重试次数限制")


class MaaEndConfigGame(ApiModel):
    ControllerType: Literal[
        "Win32-Window", "Win32-Window-Background", "Win32-Front", "ADB"
    ] | None = Field(default=None, description="控制器类型")
    Path: str | None = Field(default=None, description="终末地客户端路径")
    Arguments: str | None = Field(default=None, description="游戏启动参数")
    WaitTime: int | None = Field(default=None, description="游戏等待时间")
    EmulatorId: str | None = Field(default=None, description="模拟器ID")
    EmulatorIndex: str | None = Field(default=None, description="模拟器索引")
    CloseOnFinish: bool | None = Field(default=None, description="结束后关闭游戏")


class MaaEndConfig(ApiModel):
    type: Literal["MaaEndConfig"] = Field(default="MaaEndConfig", description="配置类型")
    Info: MaaEndConfigInfo | None = Field(default=None, description="脚本信息")
    Run: MaaEndConfigRun | None = Field(default=None, description="运行配置")
    Game: MaaEndConfigGame | None = Field(default=None, description="游戏配置")


__all__ = [
    "MaaEndUserConfigInfo",
    "MaaEndUserConfigTask",
    "MaaEndUserConfigNotify",
    "MaaEndUserConfig",
    "MaaEndConfigInfo",
    "MaaEndConfigRun",
    "MaaEndConfigGame",
    "MaaEndConfig",
]
