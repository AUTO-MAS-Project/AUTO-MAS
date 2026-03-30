from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config.base import MultipleConfig
from app.core.config.fields import RefField, VirtualField
from app.core.config.pydantic import PydanticConfigBase
from app.core.config.types import EncryptedString
from app.utils.constants import STARRAIL_STAGE_BOOK, UTC4
from .common import Webhook


RELIC_OPTIONS: tuple[str, ...] = (
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
)

MATERIAL_OPTIONS: tuple[str, ...] = (
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
)

ORNAMENT_OPTIONS: tuple[str, ...] = (
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
)

ECHO_OF_WAR_OPTIONS: tuple[str, ...] = (
    "-",
    "Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass",
    "Echo_of_War_Glance_of_Twilight",
    "Echo_of_War_Inner_Beast_Battlefield",
    "Echo_of_War_Salutations_of_Ashen_Dreams",
    "Echo_of_War_Borehole_Planet_Past_Nightmares",
    "Echo_of_War_Divine_Seed",
    "Echo_of_War_End_of_the_Eternal_Freeze",
    "Echo_of_War_Destruction_Beginning",
)

SIM_WORLD_OPTIONS: tuple[str, ...] = (
    "-",
    "Simulated_Universe_World_3",
    "Simulated_Universe_World_4",
    "Simulated_Universe_World_5",
    "Simulated_Universe_World_6",
    "Simulated_Universe_World_8",
)


class SrcUserConfig(PydanticConfigBase):
    """SRC用户配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新用户"
        Status: bool = True
        Id: str = ""
        Password: EncryptedString = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        Server: Literal[
            "CN-Official",
            "CN-Bilibili",
            "VN-Official",
            "OVERSEA-America",
            "OVERSEA-Asia",
            "OVERSEA-Europe",
            "OVERSEA-TWHKMO",
        ] = "CN-Official"
        RemainedDay: int = Field(default=-1, ge=-1, le=9999)
        Notes: str = "无"
        Tag: Annotated[
            str,
            VirtualField(
                "getTags",
                depends_on=(
                    ("Data", "IfPassCheck"),
                    ("Data", "LastProxyDate"),
                    ("Data", "ProxyTimes"),
                    ("Info", "RemainedDay"),
                    ("Stage", "Channel"),
                    ("Stage", "Relic"),
                    ("Stage", "Materials"),
                    ("Stage", "Ornament"),
                    ("Stage", "EchoOfWar"),
                    ("Stage", "SimulatedUniverseWorld"),
                    ("Info", "Notes"),
                ),
            ),
        ] = "[ ]"

    class StageModel(BaseModel):
        Channel: Literal["Relic", "Materials", "Ornament"] = "Relic"
        Relic: str = "-"
        Materials: str = "-"
        Ornament: str = "-"
        ExtractReservedTrailblazePower: bool = False
        UseFuel: bool = False
        FuelReserve: int = Field(default=5, ge=0, le=9999)
        EchoOfWar: str = "-"
        SimulatedUniverseWorld: str = "-"

        @field_validator("Relic", mode="before")
        @classmethod
        def _validate_relic(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            return text if text in RELIC_OPTIONS else "-"

        @field_validator("Materials", mode="before")
        @classmethod
        def _validate_materials(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            return text if text in MATERIAL_OPTIONS else "-"

        @field_validator("Ornament", mode="before")
        @classmethod
        def _validate_ornament(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            return text if text in ORNAMENT_OPTIONS else "-"

        @field_validator("EchoOfWar", mode="before")
        @classmethod
        def _validate_echo_of_war(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            return text if text in ECHO_OF_WAR_OPTIONS else "-"

        @field_validator("SimulatedUniverseWorld", mode="before")
        @classmethod
        def _validate_sim_world(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            return text if text in SIM_WORLD_OPTIONS else "-"

    class DataModel(BaseModel):
        LastProxyDate: str = "2000-01-01"
        ProxyTimes: int = Field(default=0, ge=0, le=9999)
        IfPassCheck: bool = True

        @field_validator("LastProxyDate", mode="before")
        @classmethod
        def _normalize_ymd(cls, value: Any) -> str:
            text = value if isinstance(value, str) else str(value)
            try:
                datetime.strptime(text, "%Y-%m-%d")
                return text
            except ValueError:
                return "2000-01-01"

    class NotifyModel(BaseModel):
        Enabled: bool = False
        IfSendStatistic: bool = False
        IfSendMail: bool = False
        ToAddress: str = ""
        IfServerChan: bool = False
        ServerChanKey: str = ""

    Info: InfoModel = Field(default_factory=InfoModel)
    Stage: StageModel = Field(default_factory=StageModel)
    Data: DataModel = Field(default_factory=DataModel)
    Notify: NotifyModel = Field(default_factory=NotifyModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

    def getTags(self) -> str:  # noqa: N802
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags: list[dict[str, str]] = []

        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

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
                "text": f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无期限",
                "color": tag_color,
            }
        )

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

        notes = self.get("Info", "Notes")
        tags.append(
            {
                "text": f"备注：{notes}"
                if len(notes) <= 20
                else f"备注：{notes[:20]}...",
                "color": "pink",
            }
        )

        return json.dumps(tags, ensure_ascii=False)


class SrcConfig(PydanticConfigBase):
    """SRC配置"""

    related_config: ClassVar[dict[str, MultipleConfig[Any]]] = {}

    class InfoModel(BaseModel):
        Name: str = "新 SRC 脚本"
        Path: str = str(Path.cwd())

    class EmulatorModel(BaseModel):
        Id: Annotated[
            str,
            RefField(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                on_delete="set_default",
            ),
        ] = "-"
        Index: str = "-"

    class RunModel(BaseModel):
        TaskTransitionMethod: Literal["ExitGame", "ExitEmulator"] = "ExitGame"
        ProxyTimesLimit: int = Field(default=0, ge=0, le=9999)
        RunTimesLimit: int = Field(default=3, ge=1, le=9999)
        RunTimeLimit: int = Field(default=10, ge=1, le=9999)

    Info: InfoModel = Field(default_factory=InfoModel)
    Emulator: EmulatorModel = Field(default_factory=EmulatorModel)
    Run: RunModel = Field(default_factory=RunModel)

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.UserData = MultipleConfig([SrcUserConfig])


__all__ = ["SrcUserConfig", "SrcConfig"]
