"""Official banner discovery adapters keyed by game and server."""

from .base import BannerObservation, BannerSource, BannerSourceError
from .bilibili import BlueArchiveBilibiliSource
from .hypergryph import ArknightsSource, EndfieldSource
from .kuro import WutheringWavesSource
from .sina import PrincessConnectSource
from .sunborn import GirlsFrontline2Source
from .taptap import AzurLaneSource, ResonanceSource

SOURCES: dict[tuple[str, str], BannerSource] = {
    ("endfield", "cn"): EndfieldSource(),
    ("wutheringwaves", "cn"): WutheringWavesSource(),
    ("arknights", "cn"): ArknightsSource(),
    ("bluearchive", "cn"): BlueArchiveBilibiliSource(),
    ("princessconnect", "cn"): PrincessConnectSource(),
    ("azurlane", "cn"): AzurLaneSource(),
    ("girlsfrontline2", "cn"): GirlsFrontline2Source(),
    ("resonance", "cn"): ResonanceSource(),
}

__all__ = ["SOURCES", "BannerObservation", "BannerSource", "BannerSourceError"]
