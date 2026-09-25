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

"""原神各区服的预设（Profile）：端点与 launcher 三元组。

内置的是公开的 HYP Connect（HoYoPlay）端点与公开已知的
launcher_id / game_id / biz 三元组：

    资源包   /hyp/hyp-connect/api/getGamePackages
    分支     /hyp/hyp-connect/api/getGameBranches
    构建     /downloader/sophon_chunk/api/getBuild        （全量清单，只收 GET）
    差分     /downloader/sophon_chunk/api/getPatchBuild   （差分清单，只收 POST）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
    "SophonChunkUrls",
    "PresetConfig",
    "GameNameType",
    "Region",
    "PROFILES",
    "get_profile",
]

# --------------------------------------------------------------------------- #
# 枚举（/ LauncherType）
# --------------------------------------------------------------------------- #


class GameNameType:
    """游戏类型标识，写进 ``config.ini`` 的 ``[Profile]`` 段。"""

    Genshin = "Genshin"


class Region:
    """区服短名，与官方接口的 ``ZoneName`` 取值对齐。"""

    CN = "cn"  # Mainland China / Bilibili
    GLOBAL = "global"  # Global

    @classmethod
    def normalize(cls, value: str) -> str:
        """把用户区服输入归一化成 ``Region.CN`` / ``Region.GLOBAL`` 短名。

        Args:
            value: 用户输入（支持 cn/zh-cn/china/bilibili/国服、global/glb/en/国际服 等）。

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
    """Sophon 的 ``getBuild`` 端点集合。

    先请求 ``branch_url`` 拿到 ``package_id / branch / password``，
    再拼到 ``main_url`` / ``preload_url`` / ``patch_url`` 上。
    """

    branch_url: str
    main_url: str
    preload_url: str
    patch_url: str
    #: 主资源的 ``matching_field``，官方固定为 ``"game"``
    main_branch_matching_field: str = "game"
    exclude_matching_field_main: List[str] = field(default_factory=list)
    exclude_matching_field_preload: List[str] = field(default_factory=list)
    exclude_matching_field_patch: List[str] = field(default_factory=list)
    exclude_matching_field_update: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Preset
# --------------------------------------------------------------------------- #


@dataclass
class PresetConfig:
    """一款游戏某个区服的全部配置 。"""

    # 身份
    profile_name: str
    game_name: str
    game_type: str
    zone_name: str
    vendor_type: str

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
    internal_game_name_in_config: str = ""
    game_directory_name: str = "Games"
    game_data_folder_name: str = ""

    # 语言
    default_voice_language: str = "zh-cn"
    supported_languages: Tuple[str, ...] = ("zh-cn", "en-us", "ja-jp", "ko-kr")

    # API 端点
    api_base: str = ""
    downloader_base: str = ""
    launcher_resource_url: str = ""
    launcher_resource_chunks_url: Optional[SophonChunkUrls] = None

    # 开关
    #: 是否强制走 Sophon（原神自 5.6 起已无 zip 包）
    is_force_redirect_to_sophon: bool = False

    # ------------------------------------------------------------------ 派生

    @property
    def game_packages_url(self) -> str:
        """``getGamePackages`` 完整 URL。

        基于 ``api_base`` 拼接 ``/hyp/hyp-connect/api/getGamePackages``，并带
        ``launcher_id`` 与 ``game_ids[]`` 查询参数。
        """
        return (
            f"{self.api_base}/hyp/hyp-connect/api/getGamePackages"
            f"?launcher_id={self.launcher_id}&game_ids[]={self.game_id}"
        )

    @property
    def game_branches_url(self) -> str:
        """``getGameBranches`` 完整 URL。

        基于 ``api_base`` 拼接 ``/hyp/hyp-connect/api/getGameBranches``，并带 ``launcher_id`` 参数。
        """
        return (
            f"{self.api_base}/hyp/hyp-connect/api/getGameBranches"
            f"?launcher_id={self.launcher_id}"
        )

    def build_get_build_url(
        self,
        package_id: str,
        branch: str = "main",
        password: str = "",
        tag: str = "",
    ) -> str:
        """拼 ``getBuild`` URL（主清单与预下载清单）。

        Args:
            package_id: 分支接口返回的 ``package_id``，拼进 ``package_id`` 参数。
            branch: 分支名；默认 ``"main"``，拼进 ``branch`` 参数。
            password: 分支密码，拼进 ``password`` 参数（可空）。
            tag: 版本 tag，拼进 ``tag`` 参数。

        Returns:
            完整 ``getBuild`` URL（含 ``plat_app={biz}`` 等业务参数）。

        Note:
            ``tag`` 必须传 API 返回的原始 3 段版本串（如 ``7.0.0``）；
            ``tag`` 为空时该参数整体被省略。若补成 4 段版本号，服务端会以 ``-202`` 拒绝。
        """
        return self.build_sophon_query_url(
            f"{self.downloader_base}/downloader/sophon_chunk/api/getBuild",
            package_id=package_id,
            branch=branch,
            password=password,
            tag=tag,
        )

    def build_sophon_query_url(
        self,
        base_url: str,
        package_id: str,
        branch: str = "main",
        password: str = "",
        tag: str = "",
    ) -> str:
        """给任意 Sophon ``getBuild`` 系端点拼上同一套查询参数。

        主清单（``getBuild``）与差分清单（``getPatchBuild``）的查询串形状完全一样，
        差别只在端点路径与 HTTP 方法，所以拼接只留这一份。

        Args:
            base_url: 端点地址，取自预设 :class:`SophonChunkUrls`。
            package_id: 分支接口返回的 ``package_id``。
            branch: 分支名。
            password: 分支密码（可空）。
            tag: 版本 tag（可空，空时整体省略该参数）。

        Returns:
            带 ``plat_app`` 等业务参数的完整请求地址。
        """
        url = (
            f"{base_url}"
            f"?plat_app={self.launcher_biz_name}"
            f"&branch={branch}"
            f"&password={password}"
            f"&package_id={package_id}"
        )
        if tag:
            url += f"&tag={tag}"
        return url


# --------------------------------------------------------------------------- #
# 内置预设
# --------------------------------------------------------------------------- #

_CN_API = "https://hyp-api.mihoyo.com"
_GLB_API = "https://sg-hyp-api.hoyoverse.com"
_CN_DL = "https://downloader-api.mihoyo.com"
_GLB_DL = "https://sg-downloader-api.hoyoverse.com"

_CN_LAUNCHER_ID = "jGHBHlcOq1"
_GLB_LAUNCHER_ID = "VYTpXlbWo8"

_COMMON_LOCALES = ("zh-cn", "en-us", "ja-jp", "ko-kr")


def _sophon_urls(base: str) -> SophonChunkUrls:
    """构造本区服的 Sophon 下载 URL 组。

    branch/main/preload 都走 ``getBuild``（只收 GET），**差分走独立的
    ``getPatchBuild`` 端点（只收 POST）**；两个端点互不通用，拿 GET 去问 getPatchBuild
    或拿 POST 去问 getBuild，服务端都回 405。
    这里只按区服把两个端点摆好，``main_branch_matching_field`` 固定为 ``"game"``。

    Args:
        base: 下载域名（``downloader_base``）。

    Returns:
        含全量与差分两个端点的 ``SophonChunkUrls``。
    """
    get_build = f"{base}/downloader/sophon_chunk/api/getBuild"
    return SophonChunkUrls(
        branch_url=get_build,
        main_url=get_build,
        preload_url=get_build,
        patch_url=f"{base}/downloader/sophon_chunk/api/getPatchBuild",
        main_branch_matching_field="game",
    )


def _build_profiles() -> Dict[Tuple[str, str], PresetConfig]:
    """构造模块级 ``PROFILES`` 字典（副作用：填充内置预设）。

    按 ``(游戏短名, 区服)`` 为原神的官服与国际服各建一份 ``PresetConfig``，
    并补全 ``launcher_resource_url``（回退为 getGamePackages 端点）。

    Returns:
        以 ``(game, region)`` 为键的预设字典；随后被赋给模块级 ``PROFILES``。
    """
    profiles: Dict[Tuple[str, str], PresetConfig] = {}

    # ---------------------------------------------------------------- 原神
    profiles[("gi", Region.CN)] = PresetConfig(
        profile_name="GICN",
        game_name="原神",
        game_type=GameNameType.Genshin,
        zone_name="Mainland China",
        vendor_type="miHoYo",
        launcher_id=_CN_LAUNCHER_ID,
        game_id="1Z8W5NHUQb",
        launcher_biz_name="hk4e_cn",
        channel_id=1,
        sub_channel_id=1,
        cps="mihoyo",
        executable_name="YuanShen.exe",
        internal_game_name_in_config="原神",
        game_directory_name="Genshin Impact Game",
        game_data_folder_name="YuanShen_Data",
        default_voice_language="zh-cn",
        supported_languages=_COMMON_LOCALES,
        api_base=_CN_API,
        downloader_base=_CN_DL,
        # 5.6 起官方移除 zip 包，本预设强制走 Sophon
        is_force_redirect_to_sophon=True,
    )
    profiles[("gi", Region.CN)].launcher_resource_chunks_url = _sophon_urls(_CN_DL)

    profiles[("gi", Region.GLOBAL)] = PresetConfig(
        profile_name="GIGlb",
        game_name="Genshin Impact",
        game_type=GameNameType.Genshin,
        zone_name="Global",
        vendor_type="miHoYo",
        launcher_id=_GLB_LAUNCHER_ID,
        game_id="gopR6Cufr3",
        launcher_biz_name="hk4e_global",
        channel_id=1,
        sub_channel_id=0,
        cps="mihoyo",
        executable_name="GenshinImpact.exe",
        internal_game_name_in_config="Genshin Impact",
        game_directory_name="Genshin Impact Game",
        game_data_folder_name="GenshinImpact_Data",
        default_voice_language="en-us",
        supported_languages=_COMMON_LOCALES,
        api_base=_GLB_API,
        downloader_base=_GLB_DL,
        is_force_redirect_to_sophon=True,
    )
    profiles[("gi", Region.GLOBAL)].launcher_resource_chunks_url = _sophon_urls(_GLB_DL)

    for preset in profiles.values():
        preset.launcher_resource_url = preset.game_packages_url

    return profiles


PROFILES: Dict[Tuple[str, str], PresetConfig] = _build_profiles()


def get_profile(region: str) -> PresetConfig:
    """取原神指定区服的预设。

    Args:
        region: 区服，``cn`` / ``global``（也接受 ``官服`` / ``国际服`` 等写法，
            由 :meth:`Region.normalize` 归一化）。

    Returns:
        匹配到的 ``PresetConfig``。

    Raises:
        ValueError: 区服无法识别，或该区服没有内置预设时。
    """
    key = ("gi", Region.normalize(region))
    if key not in PROFILES:
        available = ", ".join(sorted(registered for _, registered in PROFILES))
        raise ValueError(f"原神不支持区服 {key[1]!r}（可选: {available}）")
    return PROFILES[key]
