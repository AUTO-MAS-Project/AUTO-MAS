import json
from pathlib import Path
from datetime import datetime

from app.utils.constants import UTC4, STARRAIL_STAGE_BOOK
from ..ConfigBase import (
    ConfigBase,
    MultipleConfig,
    ConfigItem,
    MultipleUIDValidator,
    BoolValidator,
    OptionsValidator,
    RangeValidator,
    VirtualConfigValidator,
    FolderValidator,
    EncryptValidator,
    DateTimeValidator,
    UserNameValidator,
)
from .common import Webhook


class SrcUserConfig(ConfigBase):
    """SRC用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 脚本模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "简洁", OptionsValidator(["简洁", "详细"])
        )
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "CN-Official",
            OptionsValidator(
                [
                    "CN-Official",
                    "CN-Bilibili",
                    "VN-Official",
                    "OVERSEA-America",
                    "OVERSEA-Asia",
                    "OVERSEA-Europe",
                    "OVERSEA-TWHKMO",
                ]
            ),
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## 关卡配置----------------------------------------------------------
        ## 关卡通道
        self.Stage_Channel = ConfigItem(
            "Stage",
            "Channel",
            "Relic",
            OptionsValidator(["Relic", "Materials", "Ornament"]),
        )
        ## 遗器关卡
        self.Stage_Relic = ConfigItem(
            "Stage",
            "Relic",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Cavern_of_Corrosion_Path_of_Possession",
                    "Cavern_of_Corrosion_Path_of_Hidden_Salvation",
                    "Cavern_of_Corrosion_Path_of_Thundersurge",
                    "Cavern_of_Corrosion_Path_of_Aria",
                    "Cavern_of_Corrosion_Path_of_Uncertainty",
                    "Cavern_of_Corrosion_Path_of_Cavalier",
                    "Cavern_of_Corrosion_Path_of_Dreamdive"
                    "Cavern_of_Corrosion_Path_of_Darkness",
                    "Cavern_of_Corrosion_Path_of_Elixir_Seekers",
                    "Cavern_of_Corrosion_Path_of_Conflagration",
                    "Cavern_of_Corrosion_Path_of_Holy_Hymn",
                    "Cavern_of_Corrosion_Path_of_Providence",
                    "Cavern_of_Corrosion_Path_of_Drifting",
                    "Cavern_of_Corrosion_Path_of_Jabbing_Punch",
                    "Cavern_of_Corrosion_Path_of_Gelid_Wind",
                ]
            ),
        )
        ## 材料关卡
        self.Stage_Materials = ConfigItem(
            "Stage",
            "Materials",
            "-",
            OptionsValidator(
                [
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
            ),
        )
        ## 饰品关卡
        self.Stage_Ornament = ConfigItem(
            "Stage",
            "Ornament",
            "-",
            OptionsValidator(
                [
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
            ),
        )
        ## 使用储备开拓力
        self.Stage_ExtractReservedTrailblazePower = ConfigItem(
            "Stage", "ExtractReservedTrailblazePower", False, BoolValidator()
        )
        ## 使用燃料
        self.Stage_UseFuel = ConfigItem("Stage", "UseFuel", False, BoolValidator())
        ## 保留的燃料数量
        self.Stage_FuelReserve = ConfigItem(
            "Stage", "FuelReserve", 5, RangeValidator(0, 9999)
        )
        ## 历战余响关卡
        self.Stage_EchoOfWar = ConfigItem(
            "Stage",
            "EchoOfWar",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass",
                    "Echo_of_War_Glance_of_Twilight",
                    "Echo_of_War_Inner_Beast_Battlefield",
                    "Echo_of_War_Salutations_of_Ashen_Dreams",
                    "Echo_of_War_Borehole_Planet_Past_Nightmares",
                    "Echo_of_War_Divine_Seed",
                    "Echo_of_War_End_of_the_Eternal_Freeze",
                    "Echo_of_War_Destruction_Beginning",
                ]
            ),
        )
        ## 模拟宇宙关卡
        self.Stage_SimulatedUniverseWorld = ConfigItem(
            "Stage",
            "SimulatedUniverseWorld",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Simulated_Universe_World_3",
                    "Simulated_Universe_World_4",
                    "Simulated_Universe_World_5",
                    "Simulated_Universe_World_6",
                    "Simulated_Universe_World_8",
                ]
            ),
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 是否通过检查
        self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 人工排查状态标签
        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

        # 日常代理标签（使用东4区时间）
        if (
            datetime.strptime(self.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
            == datetime.now(tz=UTC4).date()
        ):
            tags.append(
                {
                    "text": f"日常：已代理{self.get('Data', 'ProxyTimes')}次",
                    "color": "green",
                }
            )
        else:
            tags.append({"text": "日常：未代理", "color": "orange"})

        # 剩余天数标签
        remained_day = self.get("Info", "RemainedDay")
        if remained_day == -1:
            tag_color = "gold"
        elif remained_day == 0:
            tag_color = "red"
        elif remained_day <= 3:
            tag_color = "orange"
        elif remained_day <= 7:
            tag_color = "yellow"
        elif remained_day <= 30:
            tag_color = "blue"
        else:
            tag_color = "green"
        tags.append(
            {
                "text": (
                    f"剩余天数：{remained_day}天"
                    if remained_day >= 0
                    else "剩余天数：无期限"
                ),
                "color": tag_color,
            }
        )

        # 关卡信息标签
        tags.append(
            {
                "text": f"关卡：{STARRAIL_STAGE_BOOK.get(self.get('Stage', self.get('Stage', 'Channel')), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"周本：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'EchoOfWar'), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"模拟宇宙：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'SimulatedUniverseWorld'), '未知关卡')}",
                "color": "blue",
            }
        )

        # 备注标签
        notes = self.get("Info", "Notes")
        tags.append(
            {
                "text": (
                    f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."
                ),
                "color": "pink",
            }
        )

        return json.dumps(tags, ensure_ascii=False)


class SrcConfig(ConfigBase):
    """SRC配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## Info ------------------------------------------------------------
        ## SRC 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 SRC 脚本")
        ## SRC 路径
        self.Info_Path = ConfigItem("Info", "Path", str(Path.cwd()), FolderValidator())

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Run -------------------------------------------------------------
        ## 任务切换方式
        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitGame",
            OptionsValidator(["ExitGame", "ExitEmulator"]),
        )
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([SrcUserConfig])

        super().__init__()


__all__ = ["SrcUserConfig", "SrcConfig"]
