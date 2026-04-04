from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel


class SrcUserConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="用户名称")
    Status: bool | None = Field(default=None, description="是否启用")
    Id: str | None = Field(default=None, description="用户ID")
    Password: str | None = Field(default=None, description="密码")
    Mode: Literal["简洁", "详细"] | None = Field(
        default=None, description="脚本模式"
    )
    Server: Literal[
        "CN-Official",
        "CN-Bilibili",
        "VN-Official",
        "OVERSEA-America",
        "OVERSEA-Asia",
        "OVERSEA-Europe",
        "OVERSEA-TWHKMO",
    ] | None = Field(default=None, description="游戏服务器")
    RemainedDay: int | None = Field(default=None, description="剩余天数")
    Notes: str | None = Field(default=None, description="备注")
    Tag: str | None = Field(default=None, description="用户标签信息")


class SrcUserConfigStage(ApiModel):
    Channel: Literal["Relic", "Materials", "Ornament"] | None = Field(
        default=None, description="关卡通道"
    )
    Relic: Literal[
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
    ] | None = Field(default=None, description="遗器关卡")
    Materials: Literal[
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
    ] | None = Field(default=None, description="材料关卡")
    Ornament: Literal[
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
    ] | None = Field(default=None, description="饰品关卡")
    ExtractReservedTrailblazePower: bool | None = Field(
        default=None, description="使用储备开拓力"
    )
    UseFuel: bool | None = Field(default=None, description="使用燃料")
    FuelReserve: int | None = Field(default=None, description="保留的燃料数量")
    EchoOfWar: str | None = Field(default=None, description="历战余响关卡")
    SimulatedUniverseWorld: str | None = Field(
        default=None, description="模拟宇宙关卡"
    )


class SrcUserConfigData(ApiModel):
    LastProxyDate: str | None = Field(default=None, description="上次代理日期")
    ProxyTimes: int | None = Field(default=None, description="代理次数")
    IfPassCheck: bool | None = Field(default=None, description="是否通过检查")


class SrcUserConfigNotify(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用通知")
    IfSendStatistic: bool | None = Field(
        default=None, description="是否发送统计信息"
    )
    IfSendMail: bool | None = Field(default=None, description="是否发送邮件")
    ToAddress: str | None = Field(default=None, description="收件地址")
    IfServerChan: bool | None = Field(default=None, description="是否启用Server酱")
    ServerChanKey: str | None = Field(default=None, description="Server酱密钥")


class SrcUserConfig(ApiModel):
    type: Literal["SrcUserConfig"] = Field(default="SrcUserConfig", description="配置类型")
    Info: SrcUserConfigInfo | None = Field(default=None, description="基础信息")
    Stage: SrcUserConfigStage | None = Field(default=None, description="关卡配置")
    Data: SrcUserConfigData | None = Field(default=None, description="用户数据")
    Notify: SrcUserConfigNotify | None = Field(default=None, description="单独通知")


class SrcConfigInfo(ApiModel):
    Name: str | None = Field(default=None, description="SRC脚本名称")
    Path: str | None = Field(default=None, description="SRC路径")


class SrcConfigEmulator(ApiModel):
    Id: str | None = Field(default=None, description="模拟器ID")
    Index: str | None = Field(default=None, description="模拟器索引")


class SrcConfigRun(ApiModel):
    TaskTransitionMethod: Literal["ExitGame", "ExitEmulator"] | None = Field(
        default=None, description="任务切换方式"
    )
    ProxyTimesLimit: int | None = Field(default=None, description="代理次数限制")
    RunTimesLimit: int | None = Field(default=None, description="运行次数限制")
    RunTimeLimit: int | None = Field(default=None, description="运行时间限制（分钟）")


class SrcConfig(ApiModel):
    type: Literal["SrcConfig"] = Field(default="SrcConfig", description="配置类型")
    Info: SrcConfigInfo | None = Field(default=None, description="脚本基础信息")
    Emulator: SrcConfigEmulator | None = Field(default=None, description="模拟器配置")
    Run: SrcConfigRun | None = Field(default=None, description="脚本运行配置")


__all__ = [
    "SrcUserConfigInfo",
    "SrcUserConfigStage",
    "SrcUserConfigData",
    "SrcUserConfigNotify",
    "SrcUserConfig",
    "SrcConfigInfo",
    "SrcConfigEmulator",
    "SrcConfigRun",
    "SrcConfig",
]
