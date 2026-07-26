"""内置游戏中心预设。

预设只描述安全的定位与启动信息。下载、覆盖安装和补丁能力不在 Alpha
宿主 provider 中开放，避免把未经验证的更新器带入生产链。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.models.game_center import GamePlatform


@dataclass(frozen=True)
class GamePreset:
    """一款游戏的稳定创建模板。"""

    key: str
    name: str
    platform: GamePlatform
    provider: str
    executable: str = ""
    package_name: str = ""
    relative_directories: tuple[str, ...] = ()


_PRESETS = {
    "starrail_cn": GamePreset(
        key="starrail_cn",
        name="崩坏：星穹铁道（国服）",
        platform="pc",
        provider="mihoyo_pc",
        executable="StarRail.exe",
    ),
    "genshin_cn": GamePreset(
        key="genshin_cn",
        name="原神（国服）",
        platform="pc",
        provider="mihoyo_pc",
        executable="YuanShen.exe",
    ),
    "zzz_cn": GamePreset(
        key="zzz_cn",
        name="绝区零（国服）",
        platform="pc",
        provider="mihoyo_pc",
        executable="ZenlessZoneZero.exe",
    ),
    "arknights_pc_cn": GamePreset(
        key="arknights_pc_cn",
        name="明日方舟（PC 国服）",
        platform="pc",
        provider="hypergryph_pc",
        executable="Arknights.exe",
        relative_directories=("Arknights Game",),
    ),
    "endfield_cn": GamePreset(
        key="endfield_cn",
        name="明日方舟：终末地（国服）",
        platform="pc",
        provider="hypergryph_pc",
        executable="Endfield.exe",
        relative_directories=("Arknights Endfield",),
    ),
    "arknights_android_cn": GamePreset(
        key="arknights_android_cn",
        name="明日方舟（模拟器国服）",
        platform="emulator",
        provider="adb_apk",
        package_name="com.hypergryph.arknights",
    ),
    "reverse1999_android_cn": GamePreset(
        key="reverse1999_android_cn",
        name="重返未来：1999（模拟器国服）",
        platform="emulator",
        provider="adb_apk",
        package_name="com.shenlan.m.reverse1999",
    ),
}

BUILTIN_GAME_PRESETS: Mapping[str, GamePreset] = MappingProxyType(_PRESETS)


__all__ = ["BUILTIN_GAME_PRESETS", "GamePreset"]
