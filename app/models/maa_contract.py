from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel


class MaaUserConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="用户名")
    Id: str | None = Field(default=None, description="用户ID")
    Mode: Literal["简洁", "详细"] | None = Field(
        default=None, description="用户配置模式"
    )
    StageMode: str | None = Field(default=None, description="关卡配置模式")
    Server: Literal[
        "Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"
    ] | None = Field(default=None, description="服务器")
    Status: bool | None = Field(default=None, description="用户状态")
    RemainedDay: int | None = Field(default=None, description="剩余天数")
    Annihilation: Literal[
        "Close",
        "Annihilation",
        "Chernobog@Annihilation",
        "LungmenOutskirts@Annihilation",
        "LungmenDowntown@Annihilation",
    ] | None = Field(default=None, description="剿灭模式")
    InfrastMode: Literal["Normal", "Rotation", "Custom"] | None = Field(
        default=None, description="基建模式"
    )
    InfrastName: str | None = Field(default=None, description="基建方案名称")
    InfrastIndex: str | None = Field(default=None, description="基建方案索引")
    Password: str | None = Field(default=None, description="密码")
    Notes: str | None = Field(default=None, description="备注")
    MedicineNumb: int | None = Field(default=None, description="吃理智药数量")
    SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] | None = Field(
        default=None, description="连战次数"
    )
    Stage: str | None = Field(default=None, description="关卡选择")
    Stage_1: str | None = Field(default=None, description="备选关卡 - 1")
    Stage_2: str | None = Field(default=None, description="备选关卡 - 2")
    Stage_3: str | None = Field(default=None, description="备选关卡 - 3")
    Stage_Remain: str | None = Field(default=None, description="剩余理智关卡")
    IfSkland: bool | None = Field(default=None, description="是否启用森空岛签到")
    SklandToken: str | None = Field(default=None, description="SklandToken")
    Tag: str | None = Field(default=None, description="状态标签列表")


class MaaUserConfigData(ApiModel):
    IfPassCheck: bool | None = Field(default=None, description="是否通过人工排查")


class MaaUserConfigTask(ApiModel):
    IfStartUp: bool | None = Field(default=None, description="开始唤醒")
    IfRecruit: bool | None = Field(default=None, description="自动公招")
    IfInfrast: bool | None = Field(default=None, description="基建换班")
    IfFight: bool | None = Field(default=None, description="理智作战")
    IfMall: bool | None = Field(default=None, description="信用收支")
    IfAward: bool | None = Field(default=None, description="领取奖励")
    IfRoguelike: bool | None = Field(default=None, description="自动肉鸽")
    IfReclamation: bool | None = Field(default=None, description="生息演算")


class MaaUserConfigNotify(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用通知")
    IfSendStatistic: bool | None = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendSixStar: bool | None = Field(default=None, description="是否发送高资喜报")
    IfSendMail: bool | None = Field(default=None, description="是否发送邮件通知")
    ToAddress: str | None = Field(default=None, description="邮件接收地址")
    IfServerChan: bool | None = Field(
        default=None, description="是否使用Server酱推送"
    )
    ServerChanKey: str | None = Field(default=None, description="ServerChanKey")


class MaaUserConfig(ApiModel):
    type: Literal["MaaUserConfig"] = Field(default="MaaUserConfig", description="配置类型")
    Info: MaaUserConfigInfo | None = Field(default=None, description="基础信息")
    Data: MaaUserConfigData | None = Field(default=None, description="用户数据")
    Task: MaaUserConfigTask | None = Field(default=None, description="任务列表")
    Notify: MaaUserConfigNotify | None = Field(default=None, description="单独通知")


class MaaConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="脚本名称")
    Path: str | None = Field(default=None, description="脚本路径")


class MaaConfigEmulator(ApiModel):
    Id: str | None = Field(default=None, description="模拟器ID")
    Index: str | None = Field(default=None, description="模拟器多开实例索引")


class MaaConfigRun(ApiModel):
    TaskTransitionMethod: Literal["NoAction", "ExitGame", "ExitEmulator"] | None = (
        Field(default=None, description="简洁任务间切换方式")
    )
    ProxyTimesLimit: int | None = Field(default=None, description="每日代理次数限制")
    RunTimesLimit: int | None = Field(default=None, description="重试次数限制")
    AnnihilationTimeLimit: int | None = Field(default=None, description="剿灭超时限制")
    RoutineTimeLimit: int | None = Field(default=None, description="日常超时限制")
    AnnihilationAvoidWaste: bool | None = Field(
        default=None, description="剿灭避免无代理卡浪费理智"
    )


class MaaConfig(ApiModel):
    type: Literal["MaaConfig"] = Field(default="MaaConfig", description="配置类型")
    Info: MaaConfigInfo | None = Field(default=None, description="脚本基础信息")
    Emulator: MaaConfigEmulator | None = Field(default=None, description="模拟器配置")
    Run: MaaConfigRun | None = Field(default=None, description="脚本运行配置")


__all__ = [
    "MaaUserConfigInfo",
    "MaaUserConfigData",
    "MaaUserConfigTask",
    "MaaUserConfigNotify",
    "MaaUserConfig",
    "MaaConfigInfo",
    "MaaConfigEmulator",
    "MaaConfigRun",
    "MaaConfig",
]
