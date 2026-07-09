#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""游戏中心内置预设

每个预设描述一款游戏在特定渠道下的更新/启动参数, 供 Provider 使用。
"添加游戏" 对话框据此预填 GameConfig。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass(frozen=True)
class GamePreset:
    """一款游戏(渠道)的预设参数"""

    key: str
    name: str
    platform: Literal["pc", "emulator"]
    provider: Literal["mihoyo_pc", "hypergryph_pc", "adb_apk"]
    # provider 相关参数(各 provider 各取所需)
    params: dict[str, Any] = field(default_factory=dict)
    # 安卓包名(模拟器游戏)
    package_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "platform": self.platform,
            "provider": self.provider,
            "params": dict(self.params),
            "package_name": self.package_name,
        }


# miHoYo HoYoPlay 统一 launcher_id(国服)
_MIHOYO_LAUNCHER_ID_CN = "jGHBHlcOq1"

# 鹰角 launcher batch_proxy 统一 launcher_appcode
_HG_LAUNCHER_APPCODE = "abYeZZ16BPluCFyT"
_HG_API_URL = "https://launcher.hypergryph.com/api/proxy/batch_proxy"


PRESETS: dict[str, GamePreset] = {
    # ---------------- miHoYo PC ----------------
    "starrail_cn": GamePreset(
        key="starrail_cn",
        name="崩坏：星穹铁道 (国服)",
        platform="pc",
        provider="mihoyo_pc",
        params={
            "launcher_id": _MIHOYO_LAUNCHER_ID_CN,
            "game_id": "64kMb5iAWu",
            "biz": "hkrpg_cn",
            "exe": "StarRail.exe",
        },
    ),
    "genshin_cn": GamePreset(
        key="genshin_cn",
        name="原神 (国服)",
        platform="pc",
        provider="mihoyo_pc",
        params={
            "launcher_id": _MIHOYO_LAUNCHER_ID_CN,
            "game_id": "1Z8W5NHUQb",
            "biz": "hk4e_cn",
            "exe": "YuanShen.exe",
        },
    ),
    "zzz_cn": GamePreset(
        key="zzz_cn",
        name="绝区零 (国服)",
        platform="pc",
        provider="mihoyo_pc",
        params={
            "launcher_id": _MIHOYO_LAUNCHER_ID_CN,
            "game_id": "x6znKlJ0xK",
            "biz": "nap_cn",
            "exe": "ZenlessZoneZero.exe",
        },
    ),
    # ---------------- 鹰角 PC ----------------
    "arknights_pc_cn": GamePreset(
        key="arknights_pc_cn",
        name="明日方舟 (PC 端 · 国服)",
        platform="pc",
        provider="hypergryph_pc",
        params={
            "api_url": _HG_API_URL,
            "appcode": "GzD1CpaWgmSq1wew",
            "launcher_appcode": _HG_LAUNCHER_APPCODE,
            "channel": "1",
            "sub_channel": "1",
            "seq": "5",
            "exe": "Arknights.exe",
            "launcher_dir_name": "Arknights Game",
        },
    ),
    "endfield_cn": GamePreset(
        key="endfield_cn",
        name="明日方舟：终末地 (国服)",
        platform="pc",
        provider="hypergryph_pc",
        params={
            "api_url": _HG_API_URL,
            "appcode": "6LL0KJuqHBVz33WK",
            "launcher_appcode": _HG_LAUNCHER_APPCODE,
            "channel": "1",
            "sub_channel": "1",
            "seq": "5",
            "exe": "Endfield.exe",
            "launcher_dir_name": "Arknights Endfield",
        },
    ),
    # ---------------- 模拟器 (ADB APK) ----------------
    "arknights_android_cn": GamePreset(
        key="arknights_android_cn",
        name="明日方舟 (模拟器 · 国服)",
        platform="emulator",
        provider="adb_apk",
        package_name="com.hypergryph.arknights",
        params={
            "version_api": "https://ak-conf.hypergryph.com/config/prod/official/Android/version",
            "apk_url": "https://ak.hypergryph.com/downloads/android_lastest",
            "version_strategy": "arknights",
        },
    ),
    "reverse1999_android_cn": GamePreset(
        key="reverse1999_android_cn",
        name="重返未来：1999 (模拟器 · 国服)",
        platform="emulator",
        provider="adb_apk",
        package_name="com.shenlan.m.reverse1999",
        params={
            # 官网固定入口, 文件名内嵌构建号
            "apk_url": "https://d.bluepoch.com/prepage/Reverse1999_Bluepoch_1006.apk",
            "version_strategy": "reverse1999",
        },
    ),
}


def get_preset(key: str) -> Optional[GamePreset]:
    return PRESETS.get(key)


def list_presets() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PRESETS.values()]
