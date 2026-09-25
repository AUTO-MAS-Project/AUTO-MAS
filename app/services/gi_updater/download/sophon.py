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
Sophon 分块下载内核 —— （``SophonManifest`` /
``SophonAsset`` / ``SophonAsset.Download`` / ``SophonUpdate``）。

整条链路（的等价流程）::

    getGameBranches                      拿 package_id / branch / password / tag
        └─ getBuild(plat_app=biz, ...)   拿 manifests[]（每个 matching_field 一条）
            └─ GET {manifest_download.url_prefix}/{manifest.id}
                → zstd 解压 → protobuf 解析 → assets[]
                    └─ GET {chunk_download.url_prefix}/{chunk_name}
                        → zstd 解压 → 按 chunk_on_file_offset 写入目标文件
                        → 校验 chunk 解压后 MD5 → 校验整文件 MD5

关键不变式：
    * ``matching_field`` 决定清单类别：``game`` 是主资源，
      ``zh-cn / en-us / ja-jp / ko-kr`` 是各语言语音包
    * 语音包就是「换一个 matching_field 再走一遍完全相同的流程」
    * chunk 是按**偏移直写**，不是先落临时文件再合并
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.services.gi_updater.api.client import HttpClient
from app.services.gi_updater.api.models import SophonManifestBuildBranch
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.paths import safe_join
from app.services.gi_updater.common.progress import (
    ProgressBase,
    summarize_size,
)
from app.services.gi_updater.download.protobuf import parse_sophon_manifest
from app.services.gi_updater.download.zstd import iter_decompress
from app.services.gi_updater.errors import UpdateAborted

__all__ = [
    "SophonManifestInfo",
    "SophonChunksInfo",
    "SophonChunkManifestInfoPair",
    "SophonChunk",
    "SophonAsset",
    "SophonManifest",
    "SophonDownloader",
    "SophonError",
    "VOICE_MATCHING_FIELDS",
]

#: 语音包使用的 matching_field
VOICE_MATCHING_FIELDS = ("zh-cn", "en-us", "ja-jp", "ko-kr")
#: 主资源
MAIN_MATCHING_FIELD = "game"


class SophonError(RuntimeError):
    """Sophon 链路异常。"""


# --------------------------------------------------------------------------- #
# 结构定义
# --------------------------------------------------------------------------- #


@dataclass
class SophonManifestInfo:
    """清单的下载地址信息。"""

    manifest_base_url: str = ""
    manifest_id: str = ""
    manifest_checksum_md5: str = ""
    is_use_compression: bool = False
    manifest_size: int = 0
    manifest_compressed_size: int = 0
    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""

    @property
    def manifest_file_url(self) -> str:
        """清单文件的完整下载地址。"""
        return f"{self.manifest_base_url.rstrip('/')}/{self.manifest_id}"


@dataclass
class SophonChunksInfo:
    """数据块的下载地址与数量信息。"""

    chunks_base_url: str = ""
    chunks_count: int = 0
    files_count: int = 0
    total_size: int = 0
    total_compressed_size: int = 0
    is_use_compression: bool = False
    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""

    def chunk_url(self, chunk_name: str) -> str:
        """拼接单个 chunk 的下载地址。

        Args:
            chunk_name: chunk 文件名（清单里的 ``chunk_name``）。

        Returns:
            完整 URL 字符串。
        """
        return f"{self.chunks_base_url.rstrip('/')}/{chunk_name}"


@dataclass
class SophonChunkManifestInfoPair:
    """清单 + chunk 的信息对。"""

    manifest_info: Optional[SophonManifestInfo] = None
    chunks_info: Optional[SophonChunksInfo] = None
    #: 同一个 getBuild 响应里的其它 manifest（用于取语音包）
    other_build_data: Optional[SophonManifestBuildBranch] = None
    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""
    is_found: bool = False
    return_code: int = 0
    return_message: str = ""

    def get_other_manifest_info_pair(
        self, matching_field: str
    ) -> "SophonChunkManifestInfoPair":
        """取同一份 build 下另一个 ``matching_field`` 的清单信息对。

        同一个 build 响应里换 ``matching_field`` 再定位一次——这正是语音包的实现方式。

        Args:
            matching_field: 目标 matching_field（如 ``zh-cn``）。

        Returns:
            定位到的信息对；找不到则 ``is_found=False``，并可能带 404 信息。
        """
        if self.other_build_data is None:
            return SophonChunkManifestInfoPair(
                matching_field=matching_field, is_found=False
            )

        identity = self.other_build_data.find(matching_field)
        if identity is None:
            return SophonChunkManifestInfoPair(
                matching_field=matching_field,
                is_found=False,
                return_code=404,
                return_message=f"Sophon manifest with matching field: {matching_field} is not found!",
            )

        return _identity_to_pair(identity, self.other_build_data)


@dataclass
class SophonChunk:
    """单个数据块及其校验信息。"""

    chunk_name: str = ""
    #: 解压后的 MD5（校验用）
    chunk_hash_decompressed: str = ""
    chunk_offset: int = 0
    chunk_size: int = 0
    chunk_size_decompressed: int = 0


@dataclass
class SophonAsset:
    """清单里的一个文件。"""

    asset_name: str = ""
    asset_size: int = 0
    asset_hash: str = ""
    is_directory: bool = False
    chunks: List[SophonChunk] = field(default_factory=list)
    chunks_info: Optional[SophonChunksInfo] = None
    matching_field: str = ""
    category_id: int = 0
    category_name: str = ""

    @property
    def chunk_count(self) -> int:
        """该 asset 包含的 chunk 数。

        Returns:
            ``chunks`` 列表长度。
        """
        return len(self.chunks)

    def __str__(self) -> str:  # pragma: no cover
        """人类可读表示：``资产名 (可读大小)``。"""
        return f"{self.asset_name} ({summarize_size(self.asset_size)})"


# --------------------------------------------------------------------------- #
# 清单获取
# --------------------------------------------------------------------------- #


def _identity_to_pair(
    identity: Any, build_data: SophonManifestBuildBranch
) -> SophonChunkManifestInfoPair:
    """把 ``SophonManifestBuildIdentity`` 转成信息对。

    Args:
        identity: 从 getBuild 响应解析出的某 matching_field 身份对象。
        build_data: 原始 build 响应数据（用于在语音包场景里二次定位）。

    Returns:
        填充好的 :class:`SophonChunkManifestInfoPair`（``is_found=True``）。
    """
    manifest_info = SophonManifestInfo(
        manifest_base_url=identity.manifest_download.url_prefix,
        manifest_id=identity.manifest.id,
        manifest_checksum_md5=identity.manifest.checksum,
        is_use_compression=identity.manifest_download.is_compressed,
        manifest_size=identity.manifest.uncompressed_size,
        manifest_compressed_size=identity.manifest.compressed_size,
        matching_field=identity.matching_field,
        category_id=identity.category_id,
        category_name=identity.category_name,
    )
    chunks_info = SophonChunksInfo(
        chunks_base_url=identity.chunk_download.url_prefix,
        chunks_count=identity.stats.chunk_count,
        files_count=identity.stats.file_count,
        total_size=identity.stats.uncompressed_size,
        total_compressed_size=identity.stats.compressed_size,
        is_use_compression=identity.chunk_download.is_compressed,
        matching_field=identity.matching_field,
        category_id=identity.category_id,
        category_name=identity.category_name,
    )
    return SophonChunkManifestInfoPair(
        manifest_info=manifest_info,
        chunks_info=chunks_info,
        other_build_data=build_data,
        matching_field=identity.matching_field,
        category_id=identity.category_id,
        category_name=identity.category_name,
        is_found=True,
    )


class SophonManifest:
    """静态方法的等价物。"""

    @staticmethod
    def create_info_pair(
        client: HttpClient,
        url: str,
        matching_field: str = MAIN_MATCHING_FIELD,
        *,
        throw_if_not_found: bool = True,
        method: str = "GET",
        logger: Any = None,
    ) -> SophonChunkManifestInfoPair:
        """拉 ``getBuild`` 并组装成清单信息对。

        ``getBuild`` 主清单用 GET、**差分（patch）用 POST**：
        两者 URL 完全相同，只有 HTTP 方法不同。

        Args:
            client: HTTP 客户端。
            url: getBuild 请求地址。
            matching_field: 清单类别；默认 ``game``（主资源）。
            throw_if_not_found: 未找到对应清单时是否抛异常。
            method: HTTP 方法，``"GET"``（主清单）或 ``"POST"``（差分）。
            logger: 可选日志器。

        Returns:
            定位到的信息对（``is_found`` 指示是否成功）。

        Raises:
            SophonError: ``throw_if_not_found=True`` 且对应 matching_field
                在响应中不存在时。
        """
        logger = logger or get_logger()
        payload = client.request(method, url).json()
        from app.services.gi_updater.api.models import parse_build

        build = parse_build(payload)

        if not build.manifests:
            return SophonChunkManifestInfoPair(
                matching_field=matching_field,
                is_found=False,
                return_code=build.retcode,
                return_message=build.message,
            )

        field_name = matching_field or MAIN_MATCHING_FIELD
        identity = build.find(field_name)
        if identity is None:
            if throw_if_not_found:
                raise SophonError(f"未找到 matching_field={field_name} 的 Sophon 清单")
            return SophonChunkManifestInfoPair(
                matching_field=field_name,
                is_found=False,
                return_code=404,
                return_message=f"Sophon manifest with matching field: {field_name} is not found!",
            )

        return _identity_to_pair(identity, build)

    @staticmethod
    def create_patch_info_pair(
        client: HttpClient,
        url: str,
        version_update_from: str,
        matching_field: str = MAIN_MATCHING_FIELD,
        *,
        logger: Any = None,
    ) -> SophonChunkManifestInfoPair:
        """拉差分 ``getPatchBuild`` 并组装成清单信息对。

        与 :meth:`create_info_pair` 的三点差异：

        1. 端点是 ``getPatchBuild``（不是 ``getBuild``），且只收 **POST**；
        2. 清单条目类型是 ``SophonManifestPatchIdentity``，
           chunk 信息来自 ``diff_download`` + ``stats``（重建为
           ``diff_tagged_info``，键是基线版本）；
        3. 拿不到 ``DiffTaggedInfo`` 就认为「没有可用的差分」→ ``is_found=False``。

        Args:
            client: HTTP 客户端。
            url: patch 分支 ``getPatchBuild`` 请求地址（用 POST）。
            version_update_from: 起始版本号，用于取 ``diff_tagged_info``。
            matching_field: 清单类别；默认 ``game``。
            logger: 可选日志器。

        Returns:
            定位到的信息对（``is_found`` 指示是否成功）。
        """
        logger = logger or get_logger()
        from app.services.gi_updater.api.models import parse_patch_build

        payload = client.request("POST", url).json()
        branch = parse_patch_build(payload)

        if not branch.manifests:
            return SophonChunkManifestInfoPair(
                matching_field=matching_field,
                is_found=False,
                return_code=branch.retcode,
                return_message=branch.message,
            )

        field_name = matching_field or MAIN_MATCHING_FIELD
        identity = branch.find(field_name)
        if identity is None:
            return SophonChunkManifestInfoPair(
                matching_field=field_name,
                is_found=False,
                return_code=404,
                return_message=f"Sophon patch with matching field: {field_name} is not found!",
            )

        stats = identity.diff_tagged_info.get(version_update_from)
        if stats is None:
            return SophonChunkManifestInfoPair(
                matching_field=field_name,
                is_found=False,
                return_code=404,
                return_message=(
                    "Sophon patch diff tagged info with version: "
                    f"{version_update_from} is not found!"
                ),
            )

        manifest_info = SophonManifestInfo(
            manifest_base_url=identity.manifest_download.url_prefix,
            manifest_id=identity.manifest.id,
            manifest_checksum_md5=identity.manifest.checksum,
            is_use_compression=identity.manifest_download.is_compressed,
            manifest_size=identity.manifest.uncompressed_size,
            manifest_compressed_size=identity.manifest.compressed_size,
            matching_field=identity.matching_field,
            category_id=identity.category_id,
            category_name=identity.category_name,
        )
        chunks_info = SophonChunksInfo(
            chunks_base_url=identity.diff_download.url_prefix,
            chunks_count=stats.chunk_count,
            files_count=stats.file_count,
            total_size=stats.uncompressed_size,
            total_compressed_size=stats.compressed_size,
            is_use_compression=identity.diff_download.is_compressed,
            matching_field=identity.matching_field,
            category_id=identity.category_id,
            category_name=identity.category_name,
        )
        return SophonChunkManifestInfoPair(
            manifest_info=manifest_info,
            chunks_info=chunks_info,
            matching_field=identity.matching_field,
            category_id=identity.category_id,
            category_name=identity.category_name,
            is_found=True,
        )

    @staticmethod
    def enumerate_assets(
        client: HttpClient,
        pair: SophonChunkManifestInfoPair,
        *,
        logger: Any = None,
    ) -> List[SophonAsset]:
        """把清单枚举成资源列表。

        下载清单 → 按需 zstd 解压 → protobuf 解析 → ``SophonAsset`` 列表。

        Args:
            client: HTTP 客户端。
            pair: 清单/分片信息对。
            logger: 可选日志器。

        Returns:
            ``SophonAsset`` 列表；``manifest_info`` / ``chunks_info`` 缺失时返回空列表。

        Note:
            清单 MD5 不一致只告警、不中断（仍继续解析）。
        """
        logger = logger or get_logger()
        if pair.manifest_info is None or pair.chunks_info is None:
            return []

        url = pair.manifest_info.manifest_file_url
        logger.debug(
            "下载 Sophon 清单：%s（matching_field=%s）", url, pair.matching_field
        )

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

        if pair.manifest_info.manifest_checksum_md5:
            actual = hashlib.md5(raw).hexdigest()
            if actual.lower() != pair.manifest_info.manifest_checksum_md5.lower():
                logger.warning(
                    "清单 MD5 不一致（期望 %s，实际 %s），仍继续解析",
                    pair.manifest_info.manifest_checksum_md5,
                    actual,
                )

        return _assets_from_proto(raw, pair)


class _BytesStream:
    """把 bytes 包装成有 ``read()`` 的流（供 iter_decompress 使用）。"""

    def __init__(self, data: bytes) -> None:
        """用一段 bytes 构造最小只读流适配器。

        Args:
            data: 待被读取的字节（供 ``iter_decompress`` 使用）。
        """
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        """从缓冲读取至多 ``size`` 字节（``-1``/``None`` 表示读完剩余）。

        Args:
            size: 最多读取的字节数；负数或 ``None`` 时读到末尾。

        Returns:
            读到的字节；已到末尾返回空 ``bytes``。
        """
        if size is None or size < 0:
            chunk = self._data[self._offset :]
            self._offset = len(self._data)
            return chunk
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _assets_from_proto(
    raw: bytes, pair: SophonChunkManifestInfoPair
) -> List[SophonAsset]:
    """protobuf -> ``SophonAsset``。

    Args:
        raw: 已解压的清单 protobuf 字节。
        pair: 清单/分片信息对（为资产附带 ``chunks_info`` 等）。

    Returns:
        ``SophonAsset`` 列表；目录条目以 ``is_directory=True`` 表示。
    """
    proto = parse_sophon_manifest(raw)
    assets: List[SophonAsset] = []

    for item in proto.assets:
        if item.is_directory or not item.asset_hash_md5:
            # 目录条目：只登记名字，不写文件内容
            assets.append(
                SophonAsset(
                    asset_name=item.asset_name,
                    is_directory=True,
                    chunks_info=pair.chunks_info,
                    matching_field=pair.matching_field,
                    category_id=pair.category_id,
                    category_name=pair.category_name,
                )
            )
            continue

        assets.append(
            SophonAsset(
                asset_name=item.asset_name,
                asset_size=item.asset_size,
                asset_hash=item.asset_hash_md5,
                is_directory=False,
                chunks=[
                    SophonChunk(
                        chunk_name=chunk.chunk_name,
                        chunk_hash_decompressed=chunk.chunk_decompressed_hash_md5,
                        chunk_offset=chunk.chunk_on_file_offset,
                        chunk_size=chunk.chunk_size,
                        chunk_size_decompressed=chunk.chunk_size_decompressed,
                    )
                    for chunk in item.asset_chunks
                ],
                chunks_info=pair.chunks_info,
                matching_field=pair.matching_field,
                category_id=pair.category_id,
                category_name=pair.category_name,
            )
        )

    return assets


# --------------------------------------------------------------------------- #
# 下载器
# --------------------------------------------------------------------------- #


@dataclass
class SophonDownloader:
    """把 Sophon 清单里的 asset 落到磁盘。"""

    client: HttpClient
    #: chunk 级并发（默认 ``min(8, CPU)``，按 ``thread_count/2`` clamp 到 2..32）
    chunk_threads: int = 8
    progress: Optional[ProgressBase] = None
    logger: Any = None
    #: dry-run：只统计，不写盘不下载
    dry_run: bool = False
    #: 协作式中止判定：在资产与数据块边界轮询，返回真即抛 ``UpdateAborted``
    should_abort: Optional[Callable[[], bool]] = None

    def __post_init__(self) -> None:
        """补默认日志器（未显式传入时）。"""
        if self.logger is None:
            self.logger = get_logger()

    def _check_abort(self) -> None:
        """在安全边界检查是否该收工。

        Raises:
            UpdateAborted: ``should_abort`` 返回真时。
        """
        if self.should_abort is not None and self.should_abort():
            raise UpdateAborted("更新已中止")

    # ---------------------------------------------------------------- 清单

    def fetch_assets(self, pair: SophonChunkManifestInfoPair) -> List[SophonAsset]:
        """拉取清单并解析出资产列表（``enumerate_assets`` 的便捷封装）。

        Args:
            pair: 清单/分片信息对。

        Returns:
            ``SophonAsset`` 列表。
        """
        return SophonManifest.enumerate_assets(self.client, pair, logger=self.logger)

    # ---------------------------------------------------------------- 单文件

    def download_asset(
        self,
        asset: SophonAsset,
        game_path: str,
        *,
        verify: bool = True,
    ) -> bool:
        """下载并组装单个 asset。

        每个 chunk 按 ``ChunkOnFileOffset`` 写进同一个目标文件流。

        Args:
            asset: 目标资产（含 chunk 列表与 ``asset_name``）。
            game_path: 游戏根目录（资产名相对其解析）。
            verify: 写入后是否整体校验 MD5。

        Returns:
            ``True`` 表示成功（或已完整被复用）；目录/无 chunk 资产或
            校验失败返回 ``False``（不抛异常）。
        """
        if asset.is_directory or asset.chunks_info is None:
            return False

        target = _resolve_target_path(game_path, asset.asset_name)
        if self.dry_run:
            return True

        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)

        if self._is_asset_complete(target, asset):
            self.logger.debug("跳过已完整文件：%s", asset.asset_name)
            if self.progress:
                self.progress.advance(asset.asset_size)
            return True

        # 先把目标文件预分配到最终大小
        with open(target, "a+b") as handle:
            if handle.tell() < asset.asset_size:
                handle.truncate(asset.asset_size)

        if self.progress:
            self.progress.set_current_file(asset.asset_name, asset.asset_size)

        self._run_chunks(asset, target)

        if verify and not self._is_asset_complete(target, asset):
            self.logger.error("文件校验失败：%s", target)
            return False
        return True

    def _run_chunks(self, asset: SophonAsset, target: str) -> None:
        """下载各 chunk 并按 ``chunk_offset`` 并发写入目标文件。

        Args:
            asset: 目标资产（chunk 列表）。
            target: 本地目标文件路径。

        Note:
            用线程池并发；每个 worker 下载一个 chunk 后 ``seek(offset)``
            写入同一文件。
        """
        chunks_info = asset.chunks_info
        assert chunks_info is not None

        def worker(chunk: SophonChunk) -> None:
            self._check_abort()
            data = self._fetch_chunk(chunks_info, chunk)
            with open(target, "r+b") as handle:
                handle.seek(chunk.chunk_offset)
                handle.write(data)
            if self.progress:
                self.progress.advance(len(data))

        with ThreadPoolExecutor(max_workers=max(1, self.chunk_threads)) as pool:
            futures = [pool.submit(worker, chunk) for chunk in asset.chunks]
            for future in as_completed(futures):
                future.result()

    def _fetch_chunk(self, chunks_info: SophonChunksInfo, chunk: SophonChunk) -> bytes:
        """下载并（按需）解压一个 chunk，同时校验解压后 MD5。

        Args:
            chunks_info: chunk 所属清单分组，提供 ``chunk_download.url_prefix``。
            chunk: 目标 chunk 的元数据（名称、压缩后长度、解压后 MD5 等）。

        Returns:
            解压后的 chunk 原始字节。

        Raises:
            SophonError: 压缩后长度不符、解压失败或 MD5 与清单不一致时。
        """
        url = chunks_info.chunk_url(chunk.chunk_name)
        response = self.client.get(url, stream=True)
        try:
            if chunks_info.is_use_compression:
                data = b"".join(
                    iter_decompress(response._stream or _BytesStream(response.content))
                )
            else:
                data = response.content
        finally:
            response.close()

        if chunk.chunk_hash_decompressed:
            actual = hashlib.md5(data).hexdigest()
            if actual.lower() != chunk.chunk_hash_decompressed.lower():
                raise SophonError(
                    f"chunk {chunk.chunk_name} MD5 校验失败"
                    f"（期望 {chunk.chunk_hash_decompressed}，实际 {actual}）"
                )
        expected = chunk.chunk_size_decompressed or chunk.chunk_size
        if expected and len(data) != expected:
            raise SophonError(
                f"chunk {chunk.chunk_name} 长度不符（期望 {expected}，实际 {len(data)}）"
            )
        return data

    # ---------------------------------------------------------------- 校验

    def _is_asset_complete(self, target: str, asset: SophonAsset) -> bool:
        """校验目标文件大小与 MD5 是否与资产一致。

        Args:
            target: 本地目标文件路径。
            asset: 资产元数据（提供期望大小与 MD5）。

        Returns:
            ``True`` 表示大小一致且 MD5 匹配（无 ``asset_hash`` 时仅看大小）；
            文件不存在或不符返回 ``False``。
        """
        if not os.path.isfile(target):
            return False
        if os.path.getsize(target) != asset.asset_size:
            return False
        if not asset.asset_hash:
            return True
        digest = hashlib.md5()
        with open(target, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest().lower() == asset.asset_hash.lower()

    # ---------------------------------------------------------------- 批量

    def download_assets(
        self,
        assets: Iterable[SophonAsset],
        game_path: str,
        *,
        file_threads: int = 4,
        verify: bool = True,
    ) -> Dict[str, bool]:
        """并行下载多个 asset（按文件维度再开一层并发）。

        Args:
            assets: 待下载的资产可迭代对象。
            game_path: 游戏根目录。
            file_threads: 文件级并发数，默认 4。
            verify: 每个文件写入后是否校验 MD5。

        Returns:
            资产名 → 成功布尔的字典（单文件异常被捕获并记为 ``False``，
            不会导致整体中断）。

        Note:
            目录类资产会被跳过（不参与下载）。
        """
        asset_list = [asset for asset in assets if not asset.is_directory]
        results: Dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=max(1, file_threads)) as pool:
            futures = {
                pool.submit(self.download_asset, asset, game_path, verify=verify): asset
                for asset in asset_list
            }
            for future in as_completed(futures):
                self._check_abort()
                asset = futures[future]
                try:
                    results[asset.asset_name] = future.result()
                except Exception as error:  # noqa: BLE001
                    self.logger.error("下载 %s 失败：%s", asset.asset_name, error)
                    results[asset.asset_name] = False
        return results


def _resolve_target_path(game_path: str, asset_name: str) -> str:
    """把清单里的资产路径解析为本地绝对路径，越界即拒绝。

    清单路径以 ``\\``（或 ``/``）分隔且相对游戏根目录。清单是服务端下发的
    不可信输入，这里走 :func:`common.paths.safe_join` 做防穿越校验——
    ``..``、盘符、UNC 与解析后越出根目录的路径一律拒绝，与 Collapse 上游
    的路径安全行为对齐。

    Args:
        game_path: 游戏根目录。
        asset_name: 清单里的资产名（含相对路径）。

    Returns:
        拼接后的本地绝对路径。

    Raises:
        UnsafePathError: 路径形态非法或越出游戏根目录时。
    """
    return safe_join(game_path, asset_name)
