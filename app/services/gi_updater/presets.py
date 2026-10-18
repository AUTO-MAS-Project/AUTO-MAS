#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""每款游戏每个区服的预设（Profile）：端点与 launcher 三元组。

``PROFILES`` 以 ``(游戏短名, 区服)`` 为键，是新增游戏时的第一处落点。

内置的是公开的 HYP Connect（HoYoPlay）端点与公开已知的 launcher_id / game_id /
biz 三元组：

    分支     /hyp/hyp-connect/api/getGameBranches
    构建     /downloader/sophon_chunk/api/getBuild        （全量清单，只收 GET）
    差分     /downloader/sophon_chunk/api/getPatchBuild   （差分清单，只收 POST）

后两端的方法不可互换，发错一端就是 405（真机实测）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = [
    "SophonChunkUrls",
    "PresetConfig",
    "GameKey",
    "Region",
    "PROFILES",
    "get_profile",
]


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #


class GameKey:
    """游戏短名：``PROFILES`` 与 ``games.spec.SPECS`` 共用的键。"""

    Genshin = "gi"

    #: 已登记的游戏短名；报错与提示用它列可选项
    KNOWN = (Genshin,)

    #: 用户侧常见写法 -> 注册短名
    ALIASES = {"genshin": Genshin, "yuanshen": Genshin, "原神": Genshin}

    @classmethod
    def normalize(cls, value: str) -> str:
        """把用户给的游戏写法归一化成注册短名。
        Returns:
            归一化后的游戏短名。

        Raises:
            ValueError: 无法识别这个游戏写法时——列出 :attr:`KNOWN` 便于自查。
        """
        text = str(value).strip().lower()
        if text in cls.KNOWN:
            return text
        key = cls.ALIASES.get(text)
        if key is not None:
            return key
        raise ValueError(f"未知游戏: {value!r}（可选: {', '.join(cls.KNOWN)}）")


class Region:
    """区服短名，与官方接口的 ``ZoneName`` 取值对齐。"""

    CN = "cn"  # Mainland China / Bilibili
    GLOBAL = "global"  # Global

    @classmethod
    def normalize(cls, value: str) -> str:
        """把用户区服输入归一化成 ``Region.CN`` / ``Region.GLOBAL`` 短名。
        Returns:
            归一化后的区服短名（``"cn"`` 或 ``"global"``）。

        Raises:
            ValueError: 无法识别该区服字符串时。
        """
        text = str(value).strip().lower()
        if text in (
            "cn",
            "zh-cn",
            "china",
            "mainland china",
            "bilibili",
            "国服",
            "官服",
        ):
            return cls.CN
        if text in ("global", "glb", "en", "overseas", "国际服"):
            return cls.GLOBAL
        raise ValueError(f"未知区服: {value!r}（可选: cn / global）")


# --------------------------------------------------------------------------- #
# Sophon URL 组
# --------------------------------------------------------------------------- #


@dataclass
class SophonChunkUrls:
    """本区服的两个 Sophon 清单端点。

    两者的查询串同形（见 :mod:`~app.services.gi_updater.api` 的拼接），差别只在路径与
    HTTP 方法：``main_url`` 取全量清单只收 GET，``patch_url`` 取差分清单位置只收 POST。
    """

    main_url: str
    patch_url: str


# --------------------------------------------------------------------------- #
# Preset
# --------------------------------------------------------------------------- #


@dataclass
class PresetConfig:
    """一款游戏某个区服的全部配置 。"""

    # 身份
    profile_name: str

    # HYP Connect 三元组
    launcher_id: str
    game_id: str
    launcher_biz_name: str

    # 渠道
    channel_id: int = 1
    sub_channel_id: int = 1
    cps: str = ""

    # 本地安装形态
    executable_name: str = ""

    # API 端点
    api_base: str = ""
    downloader_base: str = ""
    launcher_resource_chunks_url: Optional[SophonChunkUrls] = None

    # ------------------------------------------------------------------ 派生

    @property
    def game_branches_url(self) -> str:
        """``getGameBranches`` 完整 URL。

        基于 ``api_base`` 拼接 ``/hyp/hyp-connect/api/getGameBranches``，带 ``launcher_id``
        与本游戏的 ``game_ids[]``。

        Note:
            ``game_ids[]`` 不能省：一个 launcher 分组下挂着多款游戏，不带它时实测官服返回
            4 条、国际服返回 8 条（绝区零、星穹铁道、原神、崩坏三混在一起，且同 biz 可能
            占好几条），第一条并不是原神。服务端过滤之外，取条目时仍按游戏身份本地校验
            （见 :func:`~app.services.gi_updater.api._find_branch_entry`）。
        """
        return (
            f"{self.api_base}/hyp/hyp-connect/api/getGameBranches"
            f"?launcher_id={self.launcher_id}&game_ids[]={self.game_id}"
        )


# --------------------------------------------------------------------------- #
# 内置预设
# --------------------------------------------------------------------------- #

_CN_API = "https://hyp-api.mihoyo.com"
_GLB_API = "https://sg-hyp-api.hoyoverse.com"
_CN_DL = "https://downloader-api.mihoyo.com"
_GLB_DL = "https://sg-downloader-api.hoyoverse.com"

_CN_LAUNCHER_ID = "jGHBHlcOq1"
_GLB_LAUNCHER_ID = "VYTpXlbWo8"


def _sophon_urls(base: str) -> SophonChunkUrls:
    """把本区服的两个清单端点摆好。

    两端方法不通用（见本模块开头的端点表）。
    Returns:
        含全量与差分两个端点的 ``SophonChunkUrls``。
    """
    get_build = f"{base}/downloader/sophon_chunk/api/getBuild"
    return SophonChunkUrls(
        main_url=get_build,
        patch_url=f"{base}/downloader/sophon_chunk/api/getPatchBuild",
    )


def _build_profiles() -> Dict[Tuple[str, str], PresetConfig]:
    """构造模块级 ``PROFILES`` 字典（副作用：填充内置预设）。

    按 ``(游戏短名, 区服)`` 建一份 ``PresetConfig``；目前只登记了原神的官服与
    国际服两条。

    Returns:
        以 ``(game, region)`` 为键的预设字典；随后被赋给模块级 ``PROFILES``。
    """
    profiles: Dict[Tuple[str, str], PresetConfig] = {}

    # ---------------------------------------------------------------- 原神
    cn = PresetConfig(
        profile_name="GICN",
        launcher_id=_CN_LAUNCHER_ID,
        game_id="1Z8W5NHUQb",
        launcher_biz_name="hk4e_cn",
        channel_id=1,
        sub_channel_id=1,
        cps="mihoyo",
        executable_name="YuanShen.exe",
        api_base=_CN_API,
        downloader_base=_CN_DL,
    )
    cn.launcher_resource_chunks_url = _sophon_urls(cn.downloader_base)
    profiles[(GameKey.Genshin, Region.CN)] = cn

    glb = PresetConfig(
        profile_name="GIGlb",
        launcher_id=_GLB_LAUNCHER_ID,
        game_id="gopR6Cufr3",
        launcher_biz_name="hk4e_global",
        channel_id=1,
        sub_channel_id=0,
        cps="mihoyo",
        executable_name="GenshinImpact.exe",
        api_base=_GLB_API,
        downloader_base=_GLB_DL,
    )
    glb.launcher_resource_chunks_url = _sophon_urls(glb.downloader_base)
    profiles[(GameKey.Genshin, Region.GLOBAL)] = glb

    return profiles


PROFILES: Dict[Tuple[str, str], PresetConfig] = _build_profiles()


def get_profile(game: str, region: str) -> PresetConfig:
    """取指定游戏、指定区服的预设。
    Returns:
        匹配到的 ``PresetConfig``。

    Raises:
        ValueError: 游戏或区服无法识别，或该组合没有内置预设时。
    """
    key = (GameKey.normalize(game), Region.normalize(region))
    if key not in PROFILES:
        available = ", ".join(sorted(registered for registered, _ in PROFILES))
        raise ValueError(
            f"未内置游戏 {key[0]!r} 在区服 {key[1]!r} 的预设（已登记游戏: {available}）"
        )
    return PROFILES[key]
