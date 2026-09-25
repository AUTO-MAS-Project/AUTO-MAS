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

"""
HoYoPlay（HYP Connect）API 的数据模型。

字段命名与 JSON 键名逐条对齐，便于对照官方响应：

    getGamePackages   -> HypLauncherGameResourcePackageApi / HypResourcesData / HypPackageInfo
    getGameBranches   -> HypLauncherSophonBranchesApi / HypLauncherSophonBranchesKind
    getBuild          -> SophonManifestBuildBranch / SophonManifestBuildIdentity
    getBuild(patch)   -> SophonManifestPatchBranch / SophonManifestPatchIdentity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "HypGameInfoData",
    "HypResourcesData",
    "HypResourcePackageData",
    "HypPackageInfo",
    "HypPackageData",
    "GamePackageResult",
    "HypGameInfoBranchData",
    "HypLauncherSophonBranchesKind",
    "SophonManifestFileInfo",
    "SophonManifestUrlInfo",
    "SophonManifestChunkInfo",
    "SophonManifestBuildIdentity",
    "SophonManifestBuildBranch",
    "SophonManifestPatchIdentity",
    "SophonManifestPatchBranch",
    "parse_game_packages",
    "parse_game_branches",
    "parse_build",
    "parse_patch_build",
]


# --------------------------------------------------------------------------- #
# 工具：宽松取值（服务端同一字段可能给数字，也可能给字符串）
# --------------------------------------------------------------------------- #


def _int(value: Any, default: int = 0) -> int:
    """把任意值宽松转成 ``int``（宽松取值助手）。

    用于解析服务端可能以字符串/缺省形式返回的整数字段。

    Args:
        value: 原始值；``None`` 直接返回 default。
        default: 解析失败或值为 ``None`` 时的回退值。

    Returns:
        转换后的整数；任何异常（类型不符、空串）都会被吞掉返回 ``default``。
    """
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _str(value: Any, default: str = "") -> str:
    """把任意值宽松转成 ``str``（宽松取值助手）。

    Args:
        value: 原始值；``None`` 直接返回 default。
        default: 值为 ``None`` 时的回退值。

    Returns:
        转换后的字符串；``None`` 时返回 ``default``（不会抛异常）。
    """
    if value is None:
        return default
    return str(value)


def _bool(value: Any, default: bool = False) -> bool:
    """把任意值宽松转成 ``bool``（宽松取值助手）。

    除显式布尔外，仅 ``"1"/"true"/"yes"/"on"``（大小写不敏感）视为真。

    Args:
        value: 原始值；``None`` 直接返回 default。
        default: 非真值字符串或 ``None`` 时的回退值。

    Returns:
        判定结果；类型不符或空串等异常均被吞掉返回 ``default``。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# getGamePackages
# --------------------------------------------------------------------------- #


@dataclass
class HypGameInfoData:
    """``game_packages[].game``。"""

    game_id: str = ""
    game_biz: str = ""
    name: str = ""

    @classmethod
    def from_json(cls, data: Optional[Dict[str, Any]]) -> "HypGameInfoData":
        """从 ``game_packages[].game`` 节点构造。

        Args:
            data: 原始 JSON 对象；``None`` 时按空对象处理，字段全部回退默认。

        Returns:
            解析后的 ``HypGameInfoData``；``display`` 缺失时 ``name`` 为空串。
        """
        data = data or {}
        display = data.get("display") or {}
        return cls(
            game_id=_str(data.get("id")),
            game_biz=_str(data.get("biz")),
            name=_str(display.get("name")),
        )


@dataclass
class HypPackageData:
    """单个下载包。"""

    url: str = ""
    path: str = ""
    md5: str = ""
    size: int = 0
    language: str = ""
    version: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "HypPackageData":
        """从单个下载包节点构造。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的 ``HypPackageData``。
        """
        return cls(
            url=_str(data.get("url")),
            path=_str(data.get("path")),
            md5=_str(data.get("md5")),
            size=_int(data.get("size")),
            language=_str(data.get("language")),
            version=_str(data.get("version")),
        )


@dataclass
class HypPackageInfo:
    """一个版本（major 或某个 patch）的全部包。"""

    version: str = ""
    game_packages: List[HypPackageData] = field(default_factory=list)
    audio_packages: List[HypPackageData] = field(default_factory=list)
    resource_list_url: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "HypPackageInfo":
        """从单个版本节点构造（对应一个 major 或 patch）。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的 ``HypPackageInfo``；``game_pkgs``/``audio_pkgs`` 缺失时为空列表。
        """
        return cls(
            version=_str(data.get("version")),
            game_packages=[
                HypPackageData.from_json(x) for x in (data.get("game_pkgs") or [])
            ],
            audio_packages=[
                HypPackageData.from_json(x) for x in (data.get("audio_pkgs") or [])
            ],
            resource_list_url=_str(data.get("res_list_url")),
        )


@dataclass
class HypResourcePackageData:
    """``major`` / ``pre_download`` 容器。"""

    current_version: Optional[HypPackageInfo] = None
    patches: List[HypPackageInfo] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Optional[Dict[str, Any]]) -> "HypResourcePackageData":
        """从 ``major``/``pre_download`` 容器节点构造。

        Args:
            data: 原始 JSON 对象；``None`` 时按空对象处理。

        Returns:
            解析后的 ``HypResourcePackageData``；``major`` 缺失则 ``current_version`` 为 ``None``。
        """
        data = data or {}
        return cls(
            current_version=(
                HypPackageInfo.from_json(data["major"]) if data.get("major") else None
            ),
            patches=[HypPackageInfo.from_json(x) for x in (data.get("patches") or [])],
        )


@dataclass
class HypResourcesData:
    """``game_packages[]`` 的元素。"""

    game_info: HypGameInfoData = field(default_factory=HypGameInfoData)
    main_package: Optional[HypResourcePackageData] = None
    pre_download: Optional[HypResourcePackageData] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "HypResourcesData":
        """从 ``game_packages[]`` 元素构造。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的 ``HypResourcesData``；``main``/``pre_download`` 缺失时为 ``None``。
        """
        return cls(
            game_info=HypGameInfoData.from_json(data.get("game")),
            main_package=(
                HypResourcePackageData.from_json(data["main"])
                if data.get("main")
                else None
            ),
            pre_download=(
                HypResourcePackageData.from_json(data["pre_download"])
                if data.get("pre_download")
                else None
            ),
        )


@dataclass
class GamePackageResult:
    """归一化后的「本次要下的包」。"""

    main_package: List[HypPackageData] = field(default_factory=list)
    audio_package: List[HypPackageData] = field(default_factory=list)
    uncompressed_url: str = ""
    version: str = ""


def parse_game_packages(payload: Dict[str, Any]) -> List[HypResourcesData]:
    """解析 ``getGamePackages`` 响应，返回 ``game_packages[]``。

    Args:
        payload: 接口原始 JSON 响应。

    Returns:
        每个元素的 ``HypResourcesData`` 列表；``data.game_packages`` 缺失时为空列表。
    """
    data = (payload or {}).get("data") or {}
    return [
        HypResourcesData.from_json(item) for item in (data.get("game_packages") or [])
    ]


# --------------------------------------------------------------------------- #
# getGameBranches
# --------------------------------------------------------------------------- #


@dataclass
class HypGameInfoBranchData:
    """一个分支（main / pre_download）。"""

    package_id: str = ""
    branch: str = ""
    password: str = ""
    tag: str = ""
    diff_tags: List[str] = field(default_factory=list)

    @classmethod
    def from_json(
        cls, data: Optional[Dict[str, Any]]
    ) -> Optional["HypGameInfoBranchData"]:
        """从单个分支节点构造（对应 main/pre_download）。

        Args:
            data: 原始 JSON 对象；``None``/空时返回 ``None``。

        Returns:
            解析后的分支信息；输入为空时返回 ``None``。
        """
        if not data:
            return None
        return cls(
            package_id=_str(data.get("package_id")),
            branch=_str(data.get("branch")),
            password=_str(data.get("password")),
            tag=_str(data.get("tag")),
            diff_tags=[_str(x) for x in (data.get("diff_tags") or [])],
        )


@dataclass
class HypLauncherSophonBranchesKind:
    """``game_branches[]`` 的元素。"""

    game_info: HypGameInfoData = field(default_factory=HypGameInfoData)
    main: Optional[HypGameInfoBranchData] = None
    pre_download: Optional[HypGameInfoBranchData] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "HypLauncherSophonBranchesKind":
        """从 ``game_branches[]`` 元素构造。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的分支容器；``main``/``pre_download`` 缺失时为 ``None``。
        """
        return cls(
            game_info=HypGameInfoData.from_json(data.get("game")),
            main=HypGameInfoBranchData.from_json(data.get("main")),
            pre_download=HypGameInfoBranchData.from_json(data.get("pre_download")),
        )


def parse_game_branches(payload: Dict[str, Any]) -> List[HypLauncherSophonBranchesKind]:
    """解析 ``getGameBranches`` 响应，返回 ``game_branches[]``。

    Args:
        payload: 接口原始 JSON 响应。

    Returns:
        每个元素的 ``HypLauncherSophonBranchesKind`` 列表；``game_branches`` 缺失时为空列表。
    """
    data = (payload or {}).get("data") or {}
    return [
        HypLauncherSophonBranchesKind.from_json(item)
        for item in (data.get("game_branches") or [])
    ]


# --------------------------------------------------------------------------- #
# getBuild
# --------------------------------------------------------------------------- #


@dataclass
class SophonManifestFileInfo:
    """``manifest``。"""

    id: str = ""
    checksum: str = ""
    compressed_size: int = 0
    uncompressed_size: int = 0

    @classmethod
    def from_json(cls, data: Optional[Dict[str, Any]]) -> "SophonManifestFileInfo":
        """从 ``manifest`` 节点构造。

        Args:
            data: 原始 JSON 对象；``None`` 时按空对象处理。

        Returns:
            解析后的清单文件信息。
        """
        data = data or {}
        return cls(
            id=_str(data.get("id")),
            checksum=_str(data.get("checksum")),
            compressed_size=_int(data.get("compressed_size")),
            uncompressed_size=_int(data.get("uncompressed_size")),
        )


@dataclass
class SophonManifestUrlInfo:
    """``manifest_download`` / ``chunk_download``。"""

    url_prefix: str = ""
    url_suffix: str = ""
    password: str = ""
    is_encrypted: bool = False
    is_compressed: bool = False

    @classmethod
    def from_json(cls, data: Optional[Dict[str, Any]]) -> "SophonManifestUrlInfo":
        """从下载端点节点构造（manifest/chunk 下载 URL 组）。

        Args:
            data: 原始 JSON 对象；``None`` 时按空对象处理。

        Returns:
            解析后的 URL 信息。

        Note:
            字段名是有意重映射：JSON 的 ``encryption`` -> ``is_encrypted``、
            ``compression`` -> ``is_compressed``，易写反，对照时务必留意。
        """
        data = data or {}
        return cls(
            url_prefix=_str(data.get("url_prefix")),
            url_suffix=_str(data.get("url_suffix")),
            password=_str(data.get("password")),
            is_encrypted=_bool(data.get("encryption")),
            is_compressed=_bool(data.get("compression")),
        )


@dataclass
class SophonManifestChunkInfo:
    """``stats`` / ``deduplicated_stats``。"""

    compressed_size: int = 0
    uncompressed_size: int = 0
    file_count: int = 0
    chunk_count: int = 0

    @classmethod
    def from_json(cls, data: Optional[Dict[str, Any]]) -> "SophonManifestChunkInfo":
        """从 ``stats``/``deduplicated_stats`` 节点构造。

        Args:
            data: 原始 JSON 对象；``None`` 时按空对象处理。

        Returns:
            解析后的分块统计信息。
        """
        data = data or {}
        return cls(
            compressed_size=_int(data.get("compressed_size")),
            uncompressed_size=_int(data.get("uncompressed_size")),
            file_count=_int(data.get("file_count")),
            chunk_count=_int(data.get("chunk_count")),
        )


@dataclass
class SophonManifestBuildIdentity:
    """—— ``data.manifests[]`` 的元素。

    额外保留 ``matching_field`` / ``category_id`` / ``category_name``
    （这三个字段定义在 ``SophonIdentifiableProperty`` 里）。
    """

    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""
    manifest: SophonManifestFileInfo = field(default_factory=SophonManifestFileInfo)
    manifest_download: SophonManifestUrlInfo = field(
        default_factory=SophonManifestUrlInfo
    )
    chunk_download: SophonManifestUrlInfo = field(default_factory=SophonManifestUrlInfo)
    stats: SophonManifestChunkInfo = field(default_factory=SophonManifestChunkInfo)
    deduplicated_stats: SophonManifestChunkInfo = field(
        default_factory=SophonManifestChunkInfo
    )

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "SophonManifestBuildIdentity":
        """从 ``data.manifests[]`` 元素构造。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的清单条目；``matching_field`` 等来自 ``SophonIdentifiableProperty``。
        """
        return cls(
            matching_field=_str(data.get("matching_field")),
            category_id=_int(data.get("category_id")),
            category_name=_str(data.get("category_name")),
            manifest=SophonManifestFileInfo.from_json(data.get("manifest")),
            manifest_download=SophonManifestUrlInfo.from_json(
                data.get("manifest_download")
            ),
            chunk_download=SophonManifestUrlInfo.from_json(data.get("chunk_download")),
            stats=SophonManifestChunkInfo.from_json(data.get("stats")),
            deduplicated_stats=SophonManifestChunkInfo.from_json(
                data.get("deduplicated_stats")
            ),
        )


@dataclass
class SophonManifestBuildBranch:
    """``getBuild`` 响应整体。"""

    retcode: int = 0
    message: str = ""
    build_id: str = ""
    tag: str = ""
    manifests: List[SophonManifestBuildIdentity] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """成功标志：``retcode == 0`` 且 ``manifests`` 非空（服务端正常返回清单）。"""
        return self.retcode == 0 and bool(self.manifests)

    def find(self, matching_field: str) -> Optional[SophonManifestBuildIdentity]:
        """按 ``matching_field`` 定位首个命中的清单条目。

        Args:
            matching_field: 要匹配的标识串（如 ``"game"``）。

        Returns:
            首个命中条目；未命中返回 ``None``。
        """
        for identity in self.manifests:
            if identity.matching_field == matching_field:
                return identity
        return None


def parse_build(payload: Dict[str, Any]) -> SophonManifestBuildBranch:
    """解析 ``getBuild`` 响应。

    Args:
        payload: 接口原始 JSON 响应。

    Returns:
        整体构建分支信息（含 ``retcode``/``tag``/``manifests``）。
    """
    payload = payload or {}
    data = payload.get("data") or {}
    return SophonManifestBuildBranch(
        retcode=_int(payload.get("retcode")),
        message=_str(payload.get("message")),
        build_id=_str(data.get("build_id")),
        tag=_str(data.get("tag")),
        manifests=[
            SophonManifestBuildIdentity.from_json(item)
            for item in (data.get("manifests") or [])
        ],
    )


# --------------------------------------------------------------------------- #
# getBuild (patch / 差分)
# --------------------------------------------------------------------------- #


@dataclass
class SophonManifestPatchIdentity:
    """差分清单条目。"""

    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""
    manifest: SophonManifestFileInfo = field(default_factory=SophonManifestFileInfo)
    manifest_download: SophonManifestUrlInfo = field(
        default_factory=SophonManifestUrlInfo
    )
    diff_download: SophonManifestUrlInfo = field(default_factory=SophonManifestUrlInfo)
    #: version tag -> stats
    diff_tagged_info: Dict[str, SophonManifestChunkInfo] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "SophonManifestPatchIdentity":
        """从差分清单条目构造。

        Args:
            data: 原始 JSON 对象。

        Returns:
            解析后的差分条目；``stats`` 被重建成 ``version tag -> 分块统计`` 的映射。
        """
        tagged = data.get("stats") or {}
        return cls(
            matching_field=_str(data.get("matching_field")),
            category_id=_int(data.get("category_id")),
            category_name=_str(data.get("category_name")),
            manifest=SophonManifestFileInfo.from_json(data.get("manifest")),
            manifest_download=SophonManifestUrlInfo.from_json(
                data.get("manifest_download")
            ),
            diff_download=SophonManifestUrlInfo.from_json(data.get("diff_download")),
            diff_tagged_info={
                _str(key): SophonManifestChunkInfo.from_json(value)
                for key, value in tagged.items()
            }
            if isinstance(tagged, dict)
            else {},
        )


@dataclass
class SophonManifestPatchBranch:
    """差分 ``getBuild`` 响应。"""

    retcode: int = 0
    message: str = ""
    build_id: str = ""
    tag: str = ""
    patch_id: str = ""
    manifests: List[SophonManifestPatchIdentity] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """成功标志：``retcode == 0`` 且 ``manifests`` 非空。"""
        return self.retcode == 0 and bool(self.manifests)

    def find(self, matching_field: str) -> Optional[SophonManifestPatchIdentity]:
        """按 ``matching_field`` 定位差分清单条目。

        Args:
            matching_field: 要匹配的标识串。

        Returns:
            首个命中条目；未命中返回 ``None``。
        """
        for identity in self.manifests:
            if identity.matching_field == matching_field:
                return identity
        return None


def parse_patch_build(payload: Dict[str, Any]) -> SophonManifestPatchBranch:
    """解析差分 ``getBuild`` 响应。

    Args:
        payload: 接口原始 JSON 响应。

    Returns:
        差分构建分支信息（含 ``patch_id``/``manifests``）。
    """
    payload = payload or {}
    data = payload.get("data") or {}
    return SophonManifestPatchBranch(
        retcode=_int(payload.get("retcode")),
        message=_str(payload.get("message")),
        build_id=_str(data.get("build_id")),
        tag=_str(data.get("tag")),
        patch_id=_str(data.get("patch_id")),
        manifests=[
            SophonManifestPatchIdentity.from_json(item)
            for item in (data.get("manifests") or [])
        ],
    )
