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
Sophon 差分更新 —— 与
``SophonPatchAsset.Update.cs``。

差分链路（/ ``StartAlterSophonPatch``）::

    getBuild（patch 分支，带 versionUpdateFrom）
        ├─ patch 清单 protobuf：patch_assets[] / unused_assets[]
        └─ 目标版本主清单（main/preload）
                ↓ 对每个「目标清单里的 asset」判定补丁方式
        ┌───────────────┬──────────────────────────────────────────┐
        │ 不在 patch 里 │ DownloadOver —— 按主清单正常下载整文件    │
        │ original 为空 │ CopyOver     —— patch chunk 就是新内容    │
        │ original 非空 │ Patch        —— HDiff 打到旧文件上        │
        └───────────────┴──────────────────────────────────────────┘
        另有 unused_assets[] -> Remove（删除旧文件）

关于 HDiff：
没有内建的等价实现，本模块采用**可插拔补丁器**：
    * 优先调用外部 ``hpatchz`` 可执行文件
    * 若不可用，抛 ``HDiffUnavailableError`` 并把待处理项交给上层告警
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.services.gi_updater.api.client import HttpClient
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.progress import ProgressBase, SpeedLimiter
from app.services.gi_updater.download.protobuf import parse_sophon_patch
from app.services.gi_updater.download.sophon import (
    SophonAsset,
    SophonChunkManifestInfoPair,
    SophonChunksInfo,
    SophonDownloader,
    SophonManifest,
    _BytesStream,
    _resolve_target_path,
)
from app.services.gi_updater.download.zstd import decompress, iter_decompress
from app.services.gi_updater.errors import UpdateAborted

__all__ = [
    "SophonPatchMethod",
    "SophonPatchAsset",
    "SophonPatcher",
    "HDiffUnavailableError",
    "HDiffPatcher",
    "ExternalHDiffPatcher",
    "build_patch_assets",
]

#: HDiff 补丁文件的魔数
HDIFF_MAGIC = b"HDIFF"
#: 空文件的 MD5
BLANK_FILE_MD5 = "d41d8cd98f00b204e9800998ecf8427e"


class HDiffUnavailableError(RuntimeError):
    """没有可用的 HDiff 实现。"""


class SophonPatchMethod(str, Enum):
    """差分清单给出的四种落盘方式。"""

    CopyOver = "CopyOver"
    DownloadOver = "DownloadOver"
    Patch = "Patch"
    Remove = "Remove"


@dataclass
class SophonPatchAsset:
    """一个目标文件与其差分处理信息。"""

    #: 目标版本主清单里的 asset（含完整 chunk 列表）
    main_asset: Optional[SophonAsset] = None
    #: 差分档案的 chunk 信息（基址与是否压缩）——取 patch 分片只能用它，
    #: 主包 chunk 目录里没有这些分片；``DownloadOver`` 不需要，留 ``None``
    patch_chunks_info: Optional[SophonChunksInfo] = None
    patch_method: SophonPatchMethod = SophonPatchMethod.DownloadOver

    target_file_path: str = ""
    target_file_size: int = 0
    target_file_hash: str = ""

    #: patch chunk 的坐标（在 diff 文件里的偏移/长度）
    patch_name_source: str = ""
    patch_hash: str = ""
    patch_offset: int = 0
    patch_size: int = 0
    patch_chunk_length: int = 0

    original_file_path: str = ""
    original_file_size: int = 0
    original_file_hash: str = ""

    matching_field: str = ""

    @property
    def needs_download(self) -> bool:
        """该补丁资产是否需要从网络下载数据。

        Returns:
            ``True`` 表示 CopyOver / Patch / DownloadOver——三者的字节都来自差分档案
            或目标资源；只有 Remove 不需要。
        """
        return self.patch_method in (
            SophonPatchMethod.DownloadOver,
            SophonPatchMethod.CopyOver,
            SophonPatchMethod.Patch,
        )


# --------------------------------------------------------------------------- #
# 补丁清单构建
# --------------------------------------------------------------------------- #


def build_patch_assets(
    client: HttpClient,
    patch_pair: SophonChunkManifestInfoPair,
    target_pair: SophonChunkManifestInfoPair,
    version_update_from: str,
    *,
    logger: Any = None,
) -> Tuple[List[SophonPatchAsset], List[str]]:
    """把目标清单与差分清单合并成补丁资产列表。

    以差分清单点名的文件为准：每个文件按本机基线挑出对应分片，分片带
    ``original_file_name`` 的走 hdiff 打补丁（Patch），不带的说明分片本身就是新内容
    （CopyOver）；差分清单没点名的目标文件不动。同时收集需要删除的旧文件。

    Args:
        client: HTTP 客户端。
        patch_pair: 差分分支清单/分片信息对。
        target_pair: 目标版本主清单信息对。
        version_update_from: 本机已装的基线版本串（3 段，如 ``7.0.0``）——
            差分清单为**每个**基线都存了一份 ``asset_info``，必须按它挑，
            拿错基线的分片会把别的版本的分片当成本次要下的量。
        logger: 可选日志器。

    Returns:
        ``(补丁资产列表, 需要删除的旧文件路径列表)`` 二元组。
    """
    logger = logger or get_logger()

    target_assets = SophonManifest.enumerate_assets(client, target_pair, logger=logger)
    patch_proto = _fetch_patch_proto(client, patch_pair, logger=logger)

    # asset_name -> 本机基线对应的那份 asset_info
    patch_dict: Dict[str, Any] = {}
    for asset_property in patch_proto.patch_assets:
        info = _pick_asset_info(asset_property, version_update_from)
        if info is None:
            continue
        patch_dict[asset_property.asset_name] = info

    results: List[SophonPatchAsset] = []
    target_index = {
        asset.asset_name: asset for asset in target_assets if not asset.is_directory
    }
    # 只处理差分清单点名、且带本机基线分片的文件。目标清单里其余文件本机已有且内容
    # 一致，不在这次更新范围内——把它们当成「整文件重下」会把一次约 10 GB 的增量
    # 变成上百 GB 的全量下载。
    for name, info in patch_dict.items():
        asset = target_index.get(name)
        if asset is None:
            logger.debug("差分清单里的 %s 不在目标清单中，跳过", name)
            continue

        chunk = info.chunks[0] if info.chunks else None
        if chunk is None or not chunk.original_file_name:
            # patch chunk 本身就是新内容：整份新文件从差分档案里取
            results.append(
                SophonPatchAsset(
                    main_asset=asset,
                    patch_chunks_info=patch_pair.chunks_info,
                    patch_method=SophonPatchMethod.CopyOver,
                    target_file_path=asset.asset_name,
                    target_file_size=asset.asset_size,
                    target_file_hash=asset.asset_hash,
                    patch_name_source=chunk.patch_name if chunk else "",
                    patch_hash=chunk.patch_md5 if chunk else "",
                    patch_offset=chunk.patch_offset if chunk else 0,
                    patch_size=chunk.patch_size if chunk else 0,
                    patch_chunk_length=chunk.patch_length if chunk else 0,
                    matching_field=asset.matching_field,
                )
            )
            continue

        results.append(
            SophonPatchAsset(
                main_asset=asset,
                patch_chunks_info=patch_pair.chunks_info,
                patch_method=SophonPatchMethod.Patch,
                target_file_path=asset.asset_name,
                target_file_size=asset.asset_size,
                target_file_hash=asset.asset_hash,
                patch_name_source=chunk.patch_name,
                patch_hash=chunk.patch_md5,
                patch_offset=chunk.patch_offset,
                patch_size=chunk.patch_size,
                patch_chunk_length=chunk.patch_length,
                original_file_path=chunk.original_file_name,
                original_file_size=chunk.original_file_length,
                original_file_hash=chunk.original_file_md5,
                matching_field=asset.matching_field,
            )
        )

    # unused_assets -> 待删除的旧文件（目标清单里还在用的必须留下）
    removed = _collect_unused_assets(patch_proto, set(target_index))

    return results, removed


def _fetch_patch_proto(
    client: HttpClient, pair: SophonChunkManifestInfoPair, logger: Any
):
    """下载并解析差分清单 protobuf。

    Args:
        client: HTTP 客户端（:class:`~api.client.HttpClient`）。
        pair: 差分分支信息对，提供清单 URL 与是否压缩。
        logger: 日志器，用于输出调试信息。

    Returns:
        解析后的 :class:`SophonPatchProto`。

    Raises:
        RuntimeError: 信息对中缺失 ``manifest_info`` 时。
    """
    if pair.manifest_info is None:
        raise RuntimeError("差分清单信息缺失")
    url = pair.manifest_info.manifest_file_url
    logger.debug("下载 Sophon 差分清单：%s", url)
    response = client.get(url, stream=True)
    try:
        if pair.manifest_info.is_use_compression:
            raw = b"".join(
                iter_decompress(response._stream or _BytesStream(response.content))
            )
        else:
            raw = response.content
    finally:
        response.close()
    return parse_sophon_patch(raw)


def _pick_asset_info(asset_property, version_update_from: str) -> Any:
    """从 asset 的多个 asset_info 里挑出本机基线对应的那一份。

    差分清单会把**每个可升级基线**的分片都塞进同一个 asset 条目（``asset_infos``
    里各一份，带 ``version_tag``）。服务端也是按 ``versionUpdateFrom`` 精确匹配，
    所以这里只认版本 tag 相同的条目：tag 对不上就返回 ``None``，
    让该文件走上层的全量下载分支，而不是拿别的基线的分片来打补丁。

    Args:
        asset_property: 差分清单里的一个 asset 属性对象，含 ``asset_infos`` 列表。
        version_update_from: 本机基线版本串（3 段，如 ``7.0.0``），比较忽略大小写。

    Returns:
        该基线对应的 asset_info（:class:`SophonPatchAssetInfo`）；没有则 ``None``。
    """
    wanted = version_update_from.lower()
    for info in asset_property.asset_infos:
        if info.version_tag.lower() == wanted:
            return info
    return None


def _collect_unused_assets(patch_proto, keep_names: Set[str]) -> List[str]:
    """收集新版本不再引用的旧文件（``SophonUnusedAssetProperty``）。

    Args:
        patch_proto: 已解析的差分清单协议对象，含 ``unused_assets``。
        keep_names: 目标清单里仍然存在的文件名；命中的一律不删。

    Returns:
        待删除的相对文件路径列表（已去重、保持首次出现顺序）。
    """
    names: List[str] = []
    seen: Set[str] = set()
    for unused_property in patch_proto.unused_assets:
        for info in unused_property.asset_infos:
            for file_entry in info.assets:
                name = file_entry.file_name
                if not name or name in keep_names or name in seen:
                    continue
                seen.add(name)
                names.append(name)
    return names


# --------------------------------------------------------------------------- #
# HDiff 补丁器（可插拔）
# --------------------------------------------------------------------------- #


class HDiffPatcher:
    """HDiff 补丁器接口。"""

    @property
    def available(self) -> bool:  # pragma: no cover
        """基类默认不可用（需子类实现真正的 HDiff 后端）。

        Returns:
            ``False``；具体可用实现见 :class:`ExternalHDiffPatcher`。
        """
        return False

    def patch(
        self, diff_path: str, old_path: str, new_path: str
    ) -> None:  # pragma: no cover
        """基类默认实现：无可用 HDiff 后端，直接报错。

        Args:
            diff_path: 差分文件路径。
            old_path: 旧文件路径。
            new_path: 输出新文件路径。

        Raises:
            HDiffUnavailableError: 始终，提示应使用子类实现。
        """
        raise HDiffUnavailableError("未实现 HDiff 补丁器")


class ExternalHDiffPatcher(HDiffPatcher):
    """调用外部 ``hpatchz``（HDiffPatch 官方 CLI）。

    用法：``hpatchz [-f] <oldFile> <diffFile> <outNewFile>``
    """

    def __init__(self, executable: str = "hpatchz") -> None:
        """记录外部 ``hpatchz`` 可执行文件名或路径。

        Args:
            executable: ``hpatchz`` 命令名或绝对路径，默认 ``"hpatchz"``。
        """
        self.executable = executable

    @property
    def available(self) -> bool:
        """外部 ``hpatchz`` 是否可在 PATH 中找到。

        Returns:
            ``True`` 表示可执行文件存在、HDiff 补丁可用。
        """
        return shutil.which(self.executable) is not None

    def patch(self, diff_path: str, old_path: str, new_path: str) -> None:
        """调用外部 ``hpatchz`` 子进程把旧文件打补丁成新文件。

        Args:
            diff_path: 差分文件路径。
            old_path: 旧（原始）文件路径。
            new_path: 输出新文件路径（父目录会被创建）。

        Raises:
            HDiffUnavailableError: 未找到 ``hpatchz`` 时。
            RuntimeError: 子进程返回非零退出码时。
        """
        if not self.available:
            raise HDiffUnavailableError(
                f"未找到 {self.executable}；需要 HDiffPatch 才能打增量包"
            )
        os.makedirs(os.path.dirname(os.path.abspath(new_path)) or ".", exist_ok=True)
        result = subprocess.run(
            [self.executable, "-f", old_path, diff_path, new_path],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{self.executable} 执行失败（{result.returncode}）："
                f"{result.stderr.decode('utf-8', 'replace')}"
            )


# --------------------------------------------------------------------------- #
# 差分应用器
# --------------------------------------------------------------------------- #


@dataclass
class SophonPatcher:
    """把 ``SophonPatchAsset`` 列表应用到本地游戏目录。"""

    client: HttpClient
    game_path: str
    #: diff 数据的输出目录（同级）
    patch_output_dir: Optional[str] = None
    downloader: Optional[SophonDownloader] = None
    hdiff: HDiffPatcher = field(default_factory=ExternalHDiffPatcher)
    progress: Optional[ProgressBase] = None
    speed_limiter: Optional[SpeedLimiter] = None
    logger: Any = None
    dry_run: bool = False
    #: 协作式中止判定，在每条补丁资产边界轮询
    should_abort: Optional[Callable[[], bool]] = None
    #: 协作式中止判定，在每条补丁资产边界轮询
    should_abort: Optional[Callable[[], bool]] = None
    #: 协作式中止判定，在每条补丁资产边界轮询
    should_abort: Optional[Callable[[], bool]] = None

    #: 统计
    applied: Dict[str, int] = field(default_factory=dict)
    #: 因缺少 HDiff 实现而未能处理的项
    pending_hdiff: List[SophonPatchAsset] = field(default_factory=list)

    def __post_init__(self) -> None:
        """补默认日志器、补 ``patch_output_dir`` 与默认下载器。"""
        if self.logger is None:
            self.logger = get_logger()
        if self.patch_output_dir is None:
            self.patch_output_dir = os.path.join(self.game_path, "chunk_auto_mas")
        if self.downloader is None:
            self.downloader = SophonDownloader(
                client=self.client,
                progress=self.progress,
                speed_limiter=self.speed_limiter,
                logger=self.logger,
                dry_run=self.dry_run,
                should_abort=self.should_abort,
            )

    # ---------------------------------------------------------------- 主入口

    def apply(
        self,
        assets: List[SophonPatchAsset],
        removed: Optional[List[str]] = None,
        *,
        remove_old_assets: bool = True,
    ) -> Dict[str, int]:
        """按补丁方式分派处理。

        Args:
            assets: 待应用的 :class:`SophonPatchAsset` 列表。
            removed: 需要删除的旧文件路径列表；默认 ``None``。
            remove_old_assets: 是否执行删除（``removed`` 中的项）。

        Returns:
            按补丁方式统计的计数字典（键为 ``DownloadOver`` / ``CopyOver`` /
            ``Patch`` / ``Remove``，值为成功处理数）。环境不支持 HDiff 时，
            相关项记入 ``self.pending_hdiff`` 而非计入统计。
        """
        counts: Dict[str, int] = {method.value: 0 for method in SophonPatchMethod}
        # 一进来先复核本地：尺寸对得上的文件要读全文件算 MD5 才敢跳过，续传时
        # 这一段可能比下载还久。不标阶段的话界面上就是「0 B / 待下量」一动不动。
        if self.progress:
            self.progress.set_stage("verify", "校验本地文件")

        for asset in assets:
            if self.should_abort is not None and self.should_abort():
                raise UpdateAborted("更新已中止")
            target = _resolve_target_path(self.game_path, asset.target_file_path)
            if self._is_target_complete(target, asset):
                counts[asset.patch_method.value] += 1
                # 跳过 = 本次不用从网络取任何字节，只记条数。字节口径见下面两处
                # advance(len(chunk_data))：总量按计划里的 Σ patch_chunk_length，
                # 这里再按新文件大小入账会把进度灌满、把速度显示抬高。
                if self.progress:
                    self.progress.advance(0, count=1)
                continue

            if self.progress and self.progress.snapshot().stage != "download":
                self.progress.set_stage("download", "下载中")

            # DownloadOver 已不再由 build_patch_assets 产出（差分没点名的文件本轮
            # 不动），留着是为了全量兜底路径能复用同一套分派
            if asset.patch_method == SophonPatchMethod.DownloadOver:
                ok = self._download_over(asset)
            elif asset.patch_method == SophonPatchMethod.CopyOver:
                ok = self._copy_over(asset)
            else:
                ok = self._patch_hdiff(asset)

            counts[asset.patch_method.value] += 1 if ok else 0
            if ok and self.progress:
                self.progress.advance(0, count=1)
            if not ok:
                self.logger.warning(
                    "补丁失败：%s（%s）",
                    asset.target_file_path,
                    asset.patch_method.value,
                )

        self.applied = counts

        if remove_old_assets:
            for name in removed or []:
                self._remove_asset(name)
                counts[SophonPatchMethod.Remove.value] += 1

        if self.pending_hdiff:
            self.logger.warning(
                "有 %d 个文件需要 HDiff 补丁但当前环境不支持，已记录到 .pending_hdiff",
                len(self.pending_hdiff),
            )
            self._write_pending_hdiff()

        return counts

    # ---------------------------------------------------------------- 各方式

    def _download_over(self, asset: SophonPatchAsset) -> bool:
        """整文件下载（与主清单流程一致）。

        Args:
            asset: 目标补丁资产（其 ``main_asset`` 提供完整 chunk 列表）。

        Returns:
            ``True`` 表示下载并校验成功；失败返回 ``False``。
        """
        assert self.downloader is not None and asset.main_asset is not None
        return self.downloader.download_asset(asset.main_asset, self.game_path)

    def _copy_over(self, asset: SophonPatchAsset) -> bool:
        """—— 下载 patch chunk 并按偏移写入目标文件。

        注意：要先判断该 chunk 本身是不是 HDiff，
        若是则退化成「对空文件打补丁」。Python 侧同样处理。

        Args:
            asset: 待 CopyOver 的补丁资产（patch chunk 即新内容）。

        Returns:
            ``True`` 表示写入后文件已完整（校验通过）；否则 ``False``。
        """
        if self.dry_run:
            return True

        chunk_data = self._fetch_patch_chunk(asset)
        target = _resolve_target_path(self.game_path, asset.target_file_path)

        if chunk_data.startswith(HDIFF_MAGIC):
            # 对空引用文件打 HDiff
            return self._apply_hdiff_bytes(chunk_data, None, target, asset)

        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        # 这条分片本身就是**完整的新文件**（实测 82 条 CopyOver 全部满足
        # patch_chunk_length == target_file_size）。两个坑一起避开：
        #   1. ``patch_offset`` 是它在差分档案里的偏移，不是目标文件里的偏移
        #      （实测 67/82 条非零），拿它当目标偏移会写错位置；
        #   2. 追加模式（a+b）下写入永远落在文件末尾、seek 失效，预分配再写
        #      会把文件撑成两倍大。
        # 所以整份写到 .temp 再原子替换，旧文件在成功前保持原样。
        temp_path = target + ".temp"
        try:
            with open(temp_path, "wb") as handle:
                handle.write(chunk_data)
            if os.path.isfile(target):
                os.remove(target)
            os.replace(temp_path, target)
        finally:
            if os.path.isfile(temp_path):
                _remove_quiet(temp_path)

        if self.progress:
            self.progress.advance(len(chunk_data))
        return self._is_target_complete(target, asset)

    def _patch_hdiff(self, asset: SophonPatchAsset) -> bool:
        """——对旧文件打 HDiff 补丁生成新文件。

        Args:
            asset: 待 Patch 的补丁资产（含 old/new 路径与 diff 坐标）。

        Returns:
            ``True`` 表示补丁后文件完整（校验通过）；否则 ``False``。
        """
        if self.dry_run:
            return True

        chunk_data = self._fetch_patch_chunk(asset)
        old_path = _resolve_target_path(self.game_path, asset.original_file_path)
        target = _resolve_target_path(self.game_path, asset.target_file_path)
        return self._apply_hdiff_bytes(chunk_data, old_path, target, asset)

    def _apply_hdiff_bytes(
        self,
        chunk_data: bytes,
        old_path: Optional[str],
        target: str,
        asset: SophonPatchAsset,
    ) -> bool:
        """把一段 diff 数据落盘并交给 hdiff 补丁器应用。

        Args:
            chunk_data: 已下载的 diff 字节（写入临时 diff 文件）。
            old_path: 旧文件路径；``None`` 时用空 ``.diff_ref`` 表示无原文件。
            target: 输出新文件路径。
            asset: 关联的补丁资产（用于命名与完成校验）。

        Returns:
            ``True`` 表示补丁后文件完整；若 hdiff 不可用则记入
            ``pending_hdiff`` 并返回 ``False``。

        Note:
            先写 ``<target>.temp``，成功后删旧文件再原子替换；失败只留一个 temp
            并被清掉。差分切片与「从零重建」的空引用文件用完立刻删除——它们原本
            会留在缓存目录直到整轮结束，一次更新能白占好几 GiB。
        """
        if not self.hdiff.available:
            self.pending_hdiff.append(asset)
            return False

        assert self.patch_output_dir is not None
        os.makedirs(self.patch_output_dir, exist_ok=True)
        diff_path = os.path.join(
            self.patch_output_dir, _safe_name(asset.patch_name_source)
        )
        with open(diff_path, "wb") as handle:
            handle.write(chunk_data)

        temp_path = target + ".temp"
        stub_path = ""
        old_file = old_path
        if old_file is None or not os.path.isfile(old_file):
            # 没有原文件时，写一个空的 .diff_ref 代表「从零重建」
            old_file = stub_path = os.path.join(
                self.patch_output_dir, _safe_name(asset.target_file_path) + ".diff_ref"
            )
            with open(old_file, "wb"):
                pass

        try:
            self.hdiff.patch(diff_path, old_file, temp_path)
            if os.path.isfile(target):
                os.remove(target)
            os.replace(temp_path, target)
        finally:
            if os.path.isfile(temp_path):
                _remove_quiet(temp_path)
            _remove_quiet(diff_path)
            if stub_path:
                _remove_quiet(stub_path)

        if self.progress:
            self.progress.advance(len(chunk_data))
        return self._is_target_complete(target, asset)

    # ---------------------------------------------------------------- 工具

    def _fetch_patch_chunk(self, asset: SophonPatchAsset) -> bytes:
        """从 diff 源里取出该 asset 对应的那段字节（按需解压并校验 MD5）。

        Args:
            asset: 待取数据的补丁资产（提供 diff 坐标与 ``patch_hash``）。

        Returns:
            该 asset 的 patch 数据原始字节。

        Raises:
            RuntimeError: 缺差分档案 chunk 信息、取回长度与清单不符，
                或整档下载时 MD5 与清单不符。
        """
        # 基址只能取差分档案那份：主包 chunk 目录里没有 patch 分片，
        # 拿主包基址去拼会 404
        chunks_info = asset.patch_chunks_info
        if chunks_info is None:
            raise RuntimeError(f"缺少差分档案 chunk 信息：{asset.target_file_path}")

        url = chunks_info.chunk_url(asset.patch_name_source)
        start = asset.patch_offset
        length = asset.patch_chunk_length

        if length:
            response = self.client.range_get(url, start, start + length - 1)
        else:
            response = self.client.get(url, stream=True)
        try:
            data = response.content
        finally:
            response.close()

        # ``patch_hash`` / ``patch_size`` 描述的是**整份差分档案**：多个 asset 共用
        # 同一档案、各取自己的 offset+length 段，所以按段取数时不能拿整档 MD5 来比
        # （必然不符），只能比段长度；只有整档下载时才校验 MD5。
        # 目标文件本身的完整性由打补丁后的 ``target_file_hash`` 兜底。
        if length:
            if len(data) != length:
                raise RuntimeError(
                    f"patch 分段长度不符：{asset.patch_name_source} "
                    f"期望 {length} 实际 {len(data)}"
                )
        elif asset.patch_hash and len(data) != asset.patch_size:
            raise RuntimeError(
                f"差分档案大小不符：{asset.patch_name_source} "
                f"期望 {asset.patch_size} 实际 {len(data)}"
            )
        elif asset.patch_hash:
            actual = hashlib.md5(data).hexdigest()
            if actual.lower() != asset.patch_hash.lower():
                raise RuntimeError(
                    f"差分档案 {asset.patch_name_source} MD5 不符"
                    f"（期望 {asset.patch_hash}，实际 {actual}）"
                )

        if chunks_info.is_use_compression:
            data = decompress(data)

        if self.speed_limiter:
            self.speed_limiter.consume(len(data))

        return data

    def _is_target_complete(self, target: str, asset: SophonPatchAsset) -> bool:
        """校验目标文件大小与 MD5 是否与补丁资产一致。

        Args:
            target: 本地目标文件路径。
            asset: 补丁资产元数据（提供期望大小与 ``target_file_hash``）。

        Returns:
            ``True`` 表示大小一致且 MD5 匹配；无 ``target_file_hash`` 时
            仅看大小；文件不存在或不符返回 ``False``。
        """
        if not os.path.isfile(target):
            return False
        if os.path.getsize(target) != asset.target_file_size:
            return False
        if not asset.target_file_hash:
            return True
        digest = hashlib.md5()
        with open(target, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest().lower() == asset.target_file_hash.lower()

    def _remove_asset(self, name: str) -> None:
        """删除一个旧文件（HDiff 不可用等场景的清理）。

        Args:
            name: 待删除的相对文件路径。

        Note:
            先 ``chmod(0o666)`` 去掉只读位再删，规避 Windows 只读文件
            无法直接删除的问题；失败只告警、不抛异常。
        """
        path = _resolve_target_path(self.game_path, name)
        if not os.path.isfile(path):
            return
        try:
            os.chmod(path, 0o666)
            os.remove(path)
            self.logger.debug("删除旧文件：%s", path)
        except OSError as error:
            self.logger.warning("删除失败 %s：%s", path, error)

    def _write_pending_hdiff(self) -> None:
        """把 ``pending_hdiff`` 清单写入游戏根目录的 ``.pending_hdiff``。

        Note:
            每行以 ``\\t`` 分隔 ``目标文件\\t原文件\\tpatch名\\t偏移\\t长度``；
            写入失败只告警、不抛异常。
        """
        path = os.path.join(self.game_path, ".pending_hdiff")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                for asset in self.pending_hdiff:
                    handle.write(
                        f"{asset.target_file_path}\t{asset.original_file_path}\t"
                        f"{asset.patch_name_source}\t{asset.patch_offset}\t"
                        f"{asset.patch_chunk_length}\n"
                    )
        except OSError as error:  # pragma: no cover
            self.logger.warning("无法写入 %s：%s", path, error)


def _safe_name(name: str) -> str:
    """把清单里的路径名转成本地安全文件名（防止路径穿越）。

    Args:
        name: 清单里的文件名（可能含 ``\\`` / ``/`` / ``:``）。

    Returns:
        把分隔符与冒号替换为下划线后的平面文件名，无法用于跳出目录。
    """
    return name.replace("\\", "_").replace("/", "_").replace(":", "_")


def _remove_quiet(path: str) -> None:
    """删一个中间产物文件，不存在或删不掉都不抛。

    Args:
        path: 要删除的临时文件路径。

    Note:
        临时文件删不掉不该让整次更新失败——它只是白占点磁盘，下次清理或手工删除
        都能解决；把异常冒上去会把已经写好的游戏文件也一起判失败。
    """
    try:
        os.remove(path)
    except OSError:
        pass
