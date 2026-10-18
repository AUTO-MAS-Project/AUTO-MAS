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

"""Sophon 下载链路：清单 protobuf 解码、zstd 解压、清单解析与分块下载。

整条链路（上游的等价流程）::

    getGameBranches                      拿 package_id / branch / password / tag
        └─ getBuild(plat_app=biz, ...)   拿 manifests[]（每个 matching_field 一条）
            └─ GET {manifest_download.url_prefix}/{manifest.id}
                → zstd 解压 → protobuf 解析 → assets[]
                    └─ GET {chunk_download.url_prefix}/{chunk_name}
                        → zstd 解压 → 按 chunk_on_file_offset 写入目标文件
                        → 校验 chunk 解压后 MD5 → 校验整文件 MD5

关键不变式：

    * ``matching_field`` 决定清单类别，主资源用 ``game``
    * chunk 是按**偏移直写**，不是先落临时文件再合并

清单与差分档案的正文都是 protobuf，这里用 protobuf 官方运行时按 schema 构造消息类：
手写的长度前缀解析分不出 ``bytes`` / ``string`` / 嵌套消息，只能预先声明「哪些字段号是消
息」来补，内层解析失败还得吞掉异常退回原始 bytes。也不入库 ``protoc`` 生成物——生成物是
不可读的序列化字节，而显式写出字段号能逐条对照上游 ``.proto``。解出的消息一律转成小
dataclass 再交给上层，上游的 ``PascalCase`` 字段名不外泄。

上游原始定义（MIT，Hi3Helper.Sophon 项目，署名见 :mod:`app.services.gi_updater`）::

    message SophonManifestProto { repeated SophonManifestAssetProperty Assets = 1; }
    message SophonManifestAssetProperty {
      string AssetName = 1; repeated SophonManifestAssetChunk AssetChunks = 2;
      int32 AssetType = 3; int64 AssetSize = 4; string AssetHashMd5 = 5;
    }
    message SophonManifestAssetChunk {
      string ChunkName = 1; string ChunkDecompressedHashMd5 = 2;
      int64 ChunkOnFileOffset = 3; int64 ChunkSize = 4; int64 ChunkSizeDecompressed = 5;
    }

    message SophonPatchProto {
      repeated SophonPatchAssetProperty PatchAssets = 1;
      repeated SophonUnusedAssetProperty UnusedAssets = 2;
    }
    message SophonPatchAssetProperty {
      string AssetName = 1; int64 AssetSize = 2; string AssetHashMd5 = 3;
      repeated SophonPatchAssetInfo AssetInfos = 4;
    }
    message SophonPatchAssetInfo { string VersionTag = 1; SophonPatchAssetChunk Chunk = 2; }
    message SophonPatchAssetChunk {
      string PatchName = 1; string VersionTag = 2; string BuildId = 3; int64 PatchSize = 4;
      string PatchMd5 = 5; int64 PatchOffset = 6; int64 PatchLength = 7;
      string OriginalFileName = 8; int64 OriginalFileLength = 9; string OriginalFileMd5 = 10;
    }
    message SophonUnusedAssetProperty { string VersionTag = 1; repeated SophonUnusedAssetInfo AssetInfos = 2; }
    message SophonUnusedAssetInfo { repeated SophonUnusedAssetFile Assets = 1; }
    message SophonUnusedAssetFile { string FileName = 1; int64 FileSize = 2; string FileMd5 = 3; }

zstd 用 ``zstandard`` 包（仓库硬依赖）。

本模块是协议层，不含任何游戏知识。差分清单与补丁落盘见 :mod:`patch`。
"""

from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass, field
from typing import Any, List, Sequence, Tuple

import zstandard
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from app.services.gi_updater.common import UpdaterError

__all__ = [
    "MAIN_MATCHING_FIELD",
    "SophonAssetChunk",
    "SophonAssetProperty",
    "SophonManifestProto",
    "SophonPatchAssetInfo",
    "SophonPatchAssetProperty",
    "SophonPatchChunk",
    "SophonPatchProto",
    "SophonUnusedAssetFile",
    "SophonUnusedAssetInfo",
    "SophonUnusedAssetProperty",
    "decompress",
    "inflate_file",
    "parse_sophon_manifest",
    "parse_sophon_patch",
]


_PROTO_PACKAGE = "Hi3Helper.Sophon.Protos"
_proto_pool = descriptor_pool.DescriptorPool()

_STRING = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
_INT32 = descriptor_pb2.FieldDescriptorProto.TYPE_INT32
_INT64 = descriptor_pb2.FieldDescriptorProto.TYPE_INT64
_MESSAGE = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
_SCALAR = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_REPEATED = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED

#: 一条字段定义：``(字段名, 字段号, 类型, label, 嵌套类型名)``；标量类型的嵌套名传空串
_FieldSpec = tuple[str, int, int, int, str]


def _add_message(
    file_proto: descriptor_pb2.FileDescriptorProto,
    name: str,
    fields: Sequence[_FieldSpec],
) -> None:
    """往文件描述符里加一个 message 定义。"""
    message = file_proto.message_type.add()
    message.name = name
    for field_name, number, field_type, label, type_name in fields:
        entry = message.field.add()
        entry.name = field_name
        entry.number = number
        entry.type = field_type
        entry.label = label
        if type_name:
            entry.type_name = f".{_PROTO_PACKAGE}.{type_name}"


def _build_proto_file(
    file_name: str,
    messages: Sequence[tuple[str, Sequence[_FieldSpec]]],
) -> None:
    """注册一个 proto 文件描述符。

    Args:
        file_name: 文件名（仅用于描述符内标识）。
    """
    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = file_name
    file_proto.package = _PROTO_PACKAGE
    file_proto.syntax = "proto3"
    for name, fields in messages:
        _add_message(file_proto, name, fields)
    _proto_pool.Add(file_proto)


def _message_class(name: str) -> type:
    """取已注册 message 的 Python 类。
    Returns:
        可用于 ``ParseFromString`` 的消息类。
    """
    descriptor = _proto_pool.FindMessageTypeByName(f"{_PROTO_PACKAGE}.{name}")
    return message_factory.GetMessageClass(descriptor)


_build_proto_file(
    "SophonManifestProto.proto",
    [
        (
            "SophonManifestProto",
            [("Assets", 1, _MESSAGE, _REPEATED, "SophonManifestAssetProperty")],
        ),
        (
            "SophonManifestAssetProperty",
            [
                ("AssetName", 1, _STRING, _SCALAR, ""),
                ("AssetChunks", 2, _MESSAGE, _REPEATED, "SophonManifestAssetChunk"),
                ("AssetType", 3, _INT32, _SCALAR, ""),
                ("AssetSize", 4, _INT64, _SCALAR, ""),
                ("AssetHashMd5", 5, _STRING, _SCALAR, ""),
            ],
        ),
        (
            "SophonManifestAssetChunk",
            [
                ("ChunkName", 1, _STRING, _SCALAR, ""),
                ("ChunkDecompressedHashMd5", 2, _STRING, _SCALAR, ""),
                ("ChunkOnFileOffset", 3, _INT64, _SCALAR, ""),
                ("ChunkSize", 4, _INT64, _SCALAR, ""),
                ("ChunkSizeDecompressed", 5, _INT64, _SCALAR, ""),
            ],
        ),
    ],
)

_build_proto_file(
    "SophonPatchProto.proto",
    [
        (
            "SophonPatchProto",
            [
                ("PatchAssets", 1, _MESSAGE, _REPEATED, "SophonPatchAssetProperty"),
                ("UnusedAssets", 2, _MESSAGE, _REPEATED, "SophonUnusedAssetProperty"),
            ],
        ),
        (
            "SophonPatchAssetProperty",
            [
                ("AssetName", 1, _STRING, _SCALAR, ""),
                ("AssetSize", 2, _INT64, _SCALAR, ""),
                ("AssetHashMd5", 3, _STRING, _SCALAR, ""),
                ("AssetInfos", 4, _MESSAGE, _REPEATED, "SophonPatchAssetInfo"),
            ],
        ),
        (
            "SophonPatchAssetInfo",
            [
                ("VersionTag", 1, _STRING, _SCALAR, ""),
                ("Chunk", 2, _MESSAGE, _SCALAR, "SophonPatchAssetChunk"),
            ],
        ),
        (
            "SophonPatchAssetChunk",
            [
                ("PatchName", 1, _STRING, _SCALAR, ""),
                ("VersionTag", 2, _STRING, _SCALAR, ""),
                ("BuildId", 3, _STRING, _SCALAR, ""),
                ("PatchSize", 4, _INT64, _SCALAR, ""),
                ("PatchMd5", 5, _STRING, _SCALAR, ""),
                ("PatchOffset", 6, _INT64, _SCALAR, ""),
                ("PatchLength", 7, _INT64, _SCALAR, ""),
                ("OriginalFileName", 8, _STRING, _SCALAR, ""),
                ("OriginalFileLength", 9, _INT64, _SCALAR, ""),
                ("OriginalFileMd5", 10, _STRING, _SCALAR, ""),
            ],
        ),
        (
            "SophonUnusedAssetProperty",
            [
                ("VersionTag", 1, _STRING, _SCALAR, ""),
                ("AssetInfos", 2, _MESSAGE, _REPEATED, "SophonUnusedAssetInfo"),
            ],
        ),
        (
            "SophonUnusedAssetInfo",
            [("Assets", 1, _MESSAGE, _REPEATED, "SophonUnusedAssetFile")],
        ),
        (
            "SophonUnusedAssetFile",
            [
                ("FileName", 1, _STRING, _SCALAR, ""),
                ("FileSize", 2, _INT64, _SCALAR, ""),
                ("FileMd5", 3, _STRING, _SCALAR, ""),
            ],
        ),
    ],
)

_ManifestMessage = _message_class("SophonManifestProto")
_PatchMessage = _message_class("SophonPatchProto")


# --------------------------------------------------------------------------- #
# Sophon 清单（SophonManifestProto）
# --------------------------------------------------------------------------- #


@dataclass
class SophonAssetChunk:
    """清单里一个 asset 所引用的数据块。"""

    chunk_name: str = ""
    chunk_decompressed_hash_md5: str = ""
    chunk_on_file_offset: int = 0
    chunk_size: int = 0
    chunk_size_decompressed: int = 0


@dataclass
class SophonAssetProperty:
    """清单里的一个资源条目。"""

    asset_name: str = ""
    asset_type: int = 0
    asset_size: int = 0
    asset_hash_md5: str = ""
    asset_chunks: List[SophonAssetChunk] = field(default_factory=list)

    @property
    def is_directory(self) -> bool:
        """目录项的判定：``asset_type != 0``。"""
        return self.asset_type != 0


@dataclass
class SophonManifestProto:
    """解析后的 Sophon 主清单。"""

    assets: List[SophonAssetProperty] = field(default_factory=list)


def parse_sophon_manifest(data: bytes) -> SophonManifestProto:
    """解析 Sophon 清单 protobuf。
    Returns:
        :class:`SophonManifestProto`，含 ``assets`` 列表。

    Raises:
        google.protobuf.message.DecodeError: 字节不符合清单 schema 时。
    """
    message = _ManifestMessage()
    message.ParseFromString(data)

    return SophonManifestProto(
        assets=[
            SophonAssetProperty(
                asset_name=asset.AssetName,
                asset_type=asset.AssetType,
                asset_size=asset.AssetSize,
                asset_hash_md5=asset.AssetHashMd5,
                asset_chunks=[
                    SophonAssetChunk(
                        chunk_name=chunk.ChunkName,
                        chunk_decompressed_hash_md5=chunk.ChunkDecompressedHashMd5,
                        chunk_on_file_offset=chunk.ChunkOnFileOffset,
                        chunk_size=chunk.ChunkSize,
                        chunk_size_decompressed=chunk.ChunkSizeDecompressed,
                    )
                    for chunk in asset.AssetChunks
                ],
            )
            for asset in message.Assets
        ]
    )


# --------------------------------------------------------------------------- #
# Sophon 差分（SophonPatchProto）
# --------------------------------------------------------------------------- #


@dataclass
class SophonPatchChunk:
    """差分档案里一条分片的坐标与基线信息。"""

    patch_name: str = ""
    version_tag: str = ""
    build_id: str = ""
    patch_size: int = 0
    patch_md5: str = ""
    patch_offset: int = 0
    patch_length: int = 0
    original_file_name: str = ""
    original_file_length: int = 0
    original_file_md5: str = ""


@dataclass
class SophonPatchAssetInfo:
    """某个可升级基线对应的差分信息。

    Note:
        上游把 ``Chunk`` 声明为单值，这里也按单值取：没有该字段时 ``chunks``
        为空列表，与上层 ``info.chunks[0] if info.chunks else None`` 的口径一致。
    """

    version_tag: str = ""
    chunks: List[SophonPatchChunk] = field(default_factory=list)


@dataclass
class SophonPatchAssetProperty:
    """差分清单里的一个 asset 条目。"""

    asset_name: str = ""
    asset_size: int = 0
    asset_hash_md5: str = ""
    asset_infos: List[SophonPatchAssetInfo] = field(default_factory=list)


@dataclass
class SophonUnusedAssetFile:
    """升级后不再被引用的一个旧文件。"""

    file_name: str = ""
    file_size: int = 0
    file_md5: str = ""


@dataclass
class SophonUnusedAssetInfo:
    """一批不再被引用的旧文件。"""

    assets: List[SophonUnusedAssetFile] = field(default_factory=list)


@dataclass
class SophonUnusedAssetProperty:
    """某个基线升上来之后变成无用的文件清单。"""

    version_tag: str = ""
    asset_infos: List[SophonUnusedAssetInfo] = field(default_factory=list)


@dataclass
class SophonPatchProto:
    """解析后的 Sophon 差分清单。"""

    patch_assets: List[SophonPatchAssetProperty] = field(default_factory=list)
    unused_assets: List[SophonUnusedAssetProperty] = field(default_factory=list)


def _to_patch_chunk(chunk: Any) -> SophonPatchChunk:
    """把上游的差分分片转成内部 dataclass。
    Returns:
        对应的 :class:`SophonPatchChunk`。
    """
    return SophonPatchChunk(
        patch_name=chunk.PatchName,
        version_tag=chunk.VersionTag,
        build_id=chunk.BuildId,
        patch_size=chunk.PatchSize,
        patch_md5=chunk.PatchMd5,
        patch_offset=chunk.PatchOffset,
        patch_length=chunk.PatchLength,
        original_file_name=chunk.OriginalFileName,
        original_file_length=chunk.OriginalFileLength,
        original_file_md5=chunk.OriginalFileMd5,
    )


def parse_sophon_patch(data: bytes) -> SophonPatchProto:
    """解析 Sophon 差分清单 protobuf。
    Returns:
        :class:`SophonPatchProto`，含 ``patch_assets`` 与 ``unused_assets``。

    Raises:
        google.protobuf.message.DecodeError: 字节不符合差分 schema 时。
    """
    message = _PatchMessage()
    message.ParseFromString(data)

    return SophonPatchProto(
        patch_assets=[
            SophonPatchAssetProperty(
                asset_name=asset.AssetName,
                asset_size=asset.AssetSize,
                asset_hash_md5=asset.AssetHashMd5,
                asset_infos=[
                    SophonPatchAssetInfo(
                        version_tag=info.VersionTag,
                        chunks=(
                            [_to_patch_chunk(info.Chunk)]
                            if info.HasField("Chunk")
                            else []
                        ),
                    )
                    for info in asset.AssetInfos
                ],
            )
            for asset in message.PatchAssets
        ],
        unused_assets=[
            SophonUnusedAssetProperty(
                version_tag=unused.VersionTag,
                asset_infos=[
                    SophonUnusedAssetInfo(
                        assets=[
                            SophonUnusedAssetFile(
                                file_name=item.FileName,
                                file_size=item.FileSize,
                                file_md5=item.FileMd5,
                            )
                            for item in info.Assets
                        ]
                    )
                    for info in unused.AssetInfos
                ],
            )
            for unused in message.UnusedAssets
        ],
    )


# --------------------------------------------------------------------------- #
# 解压
# --------------------------------------------------------------------------- #

#: 线程各自的解压器：``zstandard.ZstdDecompressor`` 内部持有可复用的解压上下文，
#: **不是线程安全的**。清单与数据块的解压会落到 ``asyncio.to_thread`` 的多个工作线程上，
#: 共享单例会出现 ``Data corruption detected`` / ``Unknown frame descriptor`` 之类的
#: 交叉损坏（实测），所以按 ``threading.local`` 每线程惰性独享一个实例。
_ZSTD_LOCAL = threading.local()


def _decompressor() -> zstandard.ZstdDecompressor:
    """返回当前线程独享的 ``zstandard.ZstdDecompressor``。"""
    impl = getattr(_ZSTD_LOCAL, "impl", None)
    if impl is None:
        impl = _ZSTD_LOCAL.impl = zstandard.ZstdDecompressor()
    return impl


def decompress(data: bytes) -> bytes:
    """解压一段 zstd 数据。

    走流式读取器而不是单次 ``decompress()``：Sophon 的数据块帧头里往往不带内容长度，
    单次解压器算不出输出上限会直接拒绝。

    Raises:
        UpdaterError: zstandard 报错时。解压失败和取回坏字节是同一回事，
            调用方按「问不出」处理。
    """
    try:
        with _decompressor().stream_reader(io.BytesIO(data)) as reader:
            return reader.read()
    except zstandard.ZstdError as exc:
        raise UpdaterError(f"zstd 解压失败: {exc}") from exc


#: 解压流式落盘的缓冲块大小
_INFLATE_BLOCK = 4 * 1024 * 1024


def inflate_file(src: str, dst: str) -> Tuple[int, str]:
    """把一个 zstd 文件解到 ``dst``，返回 ``(写出字节数, 内容的 MD5)``。

    全程流式：内存占用只跟缓冲块一样大，几百 MiB 的数据块也解得动。校验和在同一次
    遍历里算完，不再回读一遍。
    """
    digest = hashlib.md5()
    total = 0
    try:
        with (
            open(src, "rb") as raw,
            open(dst, "wb") as out,
            _decompressor().stream_reader(raw) as reader,
        ):
            while block := reader.read(_INFLATE_BLOCK):
                digest.update(block)
                out.write(block)
                total += len(block)
    except zstandard.ZstdError as exc:
        raise UpdaterError(f"zstd 解压失败: {exc}") from exc
    return total, digest.hexdigest()


#: 主资源的 ``matching_field``，官方固定为该值
MAIN_MATCHING_FIELD = "game"
