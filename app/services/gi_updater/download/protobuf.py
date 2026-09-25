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
极简 protobuf wire 解码器（无第三方依赖）。

只为解析 Sophon 的清单 protobuf，因此只实现需要的部分：
    * varint（wire type 0）
    * 64-bit（wire type 1）
    * length-delimited（wire type 2）
    * 32-bit（wire type 5）

字段号与 完全一致，便于逐条对照。

这是自研极简解码（非 protobuf-net）：``length-delimited`` 字段把
bytes / string / 嵌套消息编码得完全同构、无法自描述，因此必须按已知
schema（见模块内的 ``MANIFEST_SPEC`` / ``PATCH_SPEC``）显式声明哪些
字段是嵌套消息，否则退化为启发式判断（可能误判）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

__all__ = [
    "ProtoReader",
    "ProtoMessage",
    "decode_varint",
    "read_message",
    "SophonManifestProto",
    "SophonAssetProperty",
    "SophonAssetChunk",
    "SophonPatchProto",
    "SophonPatchAssetProperty",
    "SophonPatchChunk",
    "parse_sophon_manifest",
    "parse_sophon_patch",
]

# wire types
_WIRE_VARINT = 0
_WIRE_64BIT = 1
_WIRE_LEN = 2
_WIRE_32BIT = 5

# ---------------------------------------------------------------------------
# 已知 schema 的嵌套消息字段号（避免依赖启发式判断）
#
# 用嵌套字典描述「哪些字段是 message、以及它内部又有哪些字段是 message」：
#     SophonManifestProto: assets(1) -> asset_chunks(2)
#     SophonPatchProto:    patch_assets(1) -> asset_infos(4) -> chunks(2)
#                          unused_assets(2) -> asset_infos(2) -> assets(1)
#
# 空字典表示「这一层没有嵌套消息」。
# ---------------------------------------------------------------------------
MANIFEST_SPEC: Dict[int, Any] = {1: {2: {}}}
PATCH_SPEC: Dict[int, Any] = {1: {4: {2: {}}}, 2: {2: {1: {}}}}


def decode_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """读一个 varint，返回 ``(值, 新的 offset)``。

    Args:
        data: 待解析的整段字节。
        offset: 起始读取位置。

    Returns:
        解码出的 ``(整数值, 解析后新的 offset)``。

    Raises:
        ValueError: ``offset`` 越界（读到末尾仍未结束）或 varint 超过
            64 bit 上限（protobuf 最大值）时。
    """
    result = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("protobuf varint 越界")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7
        if shift > 63:
            raise ValueError("protobuf varint 超长")


@dataclass
class ProtoMessage:
    """解析后的消息：字段号 -> 值列表（保留重复字段）。"""

    fields: Dict[int, List[Any]] = field(default_factory=dict)

    def get(self, field_number: int, default: Any = None) -> Any:
        """取某字段号的第一个值（重复字段只取首个）。

        Args:
            field_number: protobuf 字段号。
            default: 字段缺失时返回的默认值。

        Returns:
            该字段的第一个值；不存在则返回 ``default``。
        """
        values = self.fields.get(field_number)
        if not values:
            return default
        return values[0]

    def get_all(self, field_number: int) -> List[Any]:
        """取某字段号的全部值（保留重复字段出现顺序）。

        Args:
            field_number: protobuf 字段号。

        Returns:
            该字段所有值的列表；无此字段则为空列表。
        """
        return self.fields.get(field_number, [])

    def get_string(self, field_number: int, default: str = "") -> str:
        """取某字段号的第一个值并尽量转成 UTF-8 字符串。

        Args:
            field_number: protobuf 字段号。
            default: 字段缺失或无法解码时返回的默认字符串。

        Returns:
            解码后的字符串；缺失或转换失败时返回 ``default``。
        """
        value = self.get(field_number)
        if value is None:
            return default
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def get_int(self, field_number: int, default: int = 0) -> int:
        """取某字段号的第一个值并尝试转成 int。

        Args:
            field_number: protobuf 字段号。
            default: 字段缺失或不可转 int 时返回的默认值。

        Returns:
            整数；缺失或转换失败时返回 ``default``。
        """
        value = self.get(field_number)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_messages(self, field_number: int) -> List["ProtoMessage"]:
        """取某字段号下所有被解析为嵌套消息的值。

        Args:
            field_number: protobuf 字段号。

        Returns:
            仅包含 :class:`ProtoMessage` 实例的列表（过滤掉裸 bytes 等值）。
        """
        return [
            item
            for item in self.get_all(field_number)
            if isinstance(item, ProtoMessage)
        ]


class ProtoReader:
    """按 wire format 遍历字段。"""

    @staticmethod
    def iter_fields(data: bytes) -> Iterator[Tuple[int, int, Any]]:
        """按 wire format 顺序产出每个字段。

        Args:
            data: 整段 protobuf 消息字节。

        Yields:
            ``(field_number, wire_type, value)`` 三元组。

        Raises:
            ValueError: 遇到不支持的 wire type 时（本解码器仅支持
                0/1/2/5；packed 等其它编码会触发）。
        """
        offset = 0
        length = len(data)
        while offset < length:
            tag, offset = decode_varint(data, offset)
            field_number = tag >> 3
            wire_type = tag & 0x07

            if wire_type == _WIRE_VARINT:
                value, offset = decode_varint(data, offset)
                yield field_number, wire_type, value
            elif wire_type == _WIRE_64BIT:
                value = int.from_bytes(
                    data[offset : offset + 8], "little", signed=False
                )
                offset += 8
                yield field_number, wire_type, value
            elif wire_type == _WIRE_LEN:
                size, offset = decode_varint(data, offset)
                value = data[offset : offset + size]
                offset += size
                yield field_number, wire_type, value
            elif wire_type == _WIRE_32BIT:
                value = int.from_bytes(
                    data[offset : offset + 4], "little", signed=False
                )
                offset += 4
                yield field_number, wire_type, value
            else:
                raise ValueError(f"不支持的 protobuf wire type: {wire_type}")


def read_message(
    data: bytes, nested_spec: "Optional[Dict[int, Any]]" = None
) -> ProtoMessage:
    """把一段字节解释成一个 protobuf 消息。

    长度限定字段（bytes / string / 嵌套消息）在 wire format 里完全同构，
    无法自描述，所以这里用两条规则决定怎么解释：

    * ``nested_spec`` 显式给出嵌套结构（``{字段号: 子结构}``）时，
      只把其中列出的字段当消息递归解析 —— schema 已知时推荐，精确无歧义；
    * 否则退化为启发式：首字节能解出合法 tag 且长度自洽就当消息，
      失败则保留原始 bytes。

    Args:
        data: 待解析的整段消息字节。
        nested_spec: 已知 schema 的嵌套字段结构；``None`` 时走启发式。

    Returns:
        解析后的 :class:`ProtoMessage`（字段号 → 值列表）。

    Note:
        在启发式路径下，内层消息解析抛出的异常会被**吞掉**并回退为
        原始 bytes，不会向上传播（见 ``# noqa: BLE001``）。
    """
    message = ProtoMessage()
    for field_number, wire_type, value in ProtoReader.iter_fields(data):
        if wire_type in (_WIRE_VARINT, _WIRE_64BIT, _WIRE_32BIT):
            message.fields.setdefault(field_number, []).append(value)
            continue

        # length-delimited
        parsed: Any = value
        if nested_spec is not None:
            child_spec = nested_spec.get(field_number)
            should_parse = child_spec is not None
        else:
            child_spec = None
            should_parse = _looks_like_message(value)
        if should_parse:
            try:
                parsed = read_message(value, child_spec or {})
            except Exception:  # noqa: BLE001 - 不是消息就当 bytes
                parsed = value
        message.fields.setdefault(field_number, []).append(parsed)
    return message


def _looks_like_message(raw: bytes) -> bool:
    """启发式判断一段 bytes 是否像嵌套消息。

    仅检查首字段能否解出合法 tag、以及长度是否自洽，**不保证**内容真是
    消息——恰好形如消息的 bytes 可能被误判为 True。这是 ``read_message``
    在无 ``nested_spec`` 时的兜底判断，存在误判风险。

    Args:
        raw: 待判断的字节。

    Returns:
        像消息返回 ``True``；空字节或非法则返回 ``False``。
    """
    if not raw:
        return False
    for byte in raw:
        if byte < 0x80:
            break
    try:
        tag, offset = decode_varint(raw, 0)
    except ValueError:
        return False
    wire_type = tag & 0x07
    if wire_type not in (_WIRE_VARINT, _WIRE_64BIT, _WIRE_LEN, _WIRE_32BIT):
        return False
    if wire_type == _WIRE_LEN:
        try:
            size, offset = decode_varint(raw, offset)
        except ValueError:
            return False
        return offset + size == len(raw)
    return offset <= len(raw)


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
    """清单里的一个资源条目。

    字段号：asset_name=1, asset_chunks=2, asset_type=3, asset_size=4, asset_hash_md5=5
    """

    asset_name: str = ""
    asset_type: int = 0
    asset_size: int = 0
    asset_hash_md5: str = ""
    asset_chunks: List[SophonAssetChunk] = field(default_factory=list)

    @property
    def is_directory(self) -> bool:
        """的判定：asset_type != 0。"""
        return self.asset_type != 0


@dataclass
class SophonManifestProto:
    """``assets = 1``。"""

    assets: List[SophonAssetProperty] = field(default_factory=list)


def parse_sophon_manifest(data: bytes) -> SophonManifestProto:
    """解析 Sophon 清单 protobuf。

    Args:
        data: 原始清单字节（通常已 zstd 解压）。

    Returns:
        :class:`SophonManifestProto`，含 ``assets`` 列表。
    """
    message = read_message(data, MANIFEST_SPEC)
    assets: List[SophonAssetProperty] = []

    for asset_message in message.get_messages(1):
        asset = SophonAssetProperty(
            asset_name=asset_message.get_string(1),
            asset_type=asset_message.get_int(3),
            asset_size=asset_message.get_int(4),
            asset_hash_md5=asset_message.get_string(5),
        )
        for chunk_message in asset_message.get_messages(2):
            asset.asset_chunks.append(
                SophonAssetChunk(
                    chunk_name=chunk_message.get_string(1),
                    chunk_decompressed_hash_md5=chunk_message.get_string(2),
                    chunk_on_file_offset=chunk_message.get_int(3),
                    chunk_size=chunk_message.get_int(4),
                    chunk_size_decompressed=chunk_message.get_int(5),
                )
            )
        assets.append(asset)

    return SophonManifestProto(assets=assets)


# --------------------------------------------------------------------------- #
# Sophon 差分（SophonPatchProto）
# --------------------------------------------------------------------------- #


@dataclass
class SophonPatchChunk:
    """（``SophonPatchProto`` 里嵌套的 chunk）。

    字段号：patch_name=1, version_tag=2, build_id=3, patch_size=4, patch_md5=5,
    patch_offset=6, patch_length=7, original_file_name=8, original_file_length=9,
    original_file_md5=10
    """

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
    """``version_tag=1, chunk=2``。"""

    version_tag: str = ""
    chunks: List[SophonPatchChunk] = field(default_factory=list)


@dataclass
class SophonPatchAssetProperty:
    """—— ``asset_name=1, asset_size=2,
    asset_hash_md5=3, asset_infos=4``。"""

    asset_name: str = ""
    asset_size: int = 0
    asset_hash_md5: str = ""
    asset_infos: List[SophonPatchAssetInfo] = field(default_factory=list)


@dataclass
class SophonUnusedAssetFile:
    """``file_name=1, file_size=2, file_md5=3``。"""

    file_name: str = ""
    file_size: int = 0
    file_md5: str = ""


@dataclass
class SophonUnusedAssetInfo:
    """``assets=1``。"""

    assets: List[SophonUnusedAssetFile] = field(default_factory=list)


@dataclass
class SophonUnusedAssetProperty:
    """``version_tag=1, asset_infos=2``。

    Note:
        这里列的是「从某个基线升上来后就不再被引用」的旧文件，跨基线混在一起，
        因此不能直接照单全删——目标清单里仍然存在的同名文件必须留下。
    """

    version_tag: str = ""
    asset_infos: List[SophonUnusedAssetInfo] = field(default_factory=list)


@dataclass
class SophonPatchProto:
    """``patch_assets=1, unused_assets=2``。"""

    patch_assets: List[SophonPatchAssetProperty] = field(default_factory=list)
    unused_assets: List[SophonUnusedAssetProperty] = field(default_factory=list)


def parse_sophon_patch(data: bytes) -> SophonPatchProto:
    """解析 Sophon 差分清单 protobuf。

    Args:
        data: 原始差分清单字节（通常已 zstd 解压）。

    Returns:
        :class:`SophonPatchProto`，含 ``patch_assets`` 与 ``unused_assets``。
    """
    message = read_message(data, PATCH_SPEC)
    proto = SophonPatchProto()

    for asset_message in message.get_messages(1):
        asset = SophonPatchAssetProperty(
            asset_name=asset_message.get_string(1),
            asset_size=asset_message.get_int(2),
            asset_hash_md5=asset_message.get_string(3),
        )
        for info_message in asset_message.get_messages(4):
            info = SophonPatchAssetInfo(version_tag=info_message.get_string(1))
            for chunk_message in info_message.get_messages(2):
                info.chunks.append(
                    SophonPatchChunk(
                        patch_name=chunk_message.get_string(1),
                        version_tag=chunk_message.get_string(2),
                        build_id=chunk_message.get_string(3),
                        patch_size=chunk_message.get_int(4),
                        patch_md5=chunk_message.get_string(5),
                        patch_offset=chunk_message.get_int(6),
                        patch_length=chunk_message.get_int(7),
                        original_file_name=chunk_message.get_string(8),
                        original_file_length=chunk_message.get_int(9),
                        original_file_md5=chunk_message.get_string(10),
                    )
                )
            asset.asset_infos.append(info)
        proto.patch_assets.append(asset)

    for unused_message in message.get_messages(2):
        unused = SophonUnusedAssetProperty(version_tag=unused_message.get_string(1))
        for info_message in unused_message.get_messages(2):
            info = SophonUnusedAssetInfo()
            for file_message in info_message.get_messages(1):
                info.assets.append(
                    SophonUnusedAssetFile(
                        file_name=file_message.get_string(1),
                        file_size=file_message.get_int(2),
                        file_md5=file_message.get_string(3),
                    )
                )
            unused.asset_infos.append(info)
        proto.unused_assets.append(unused)

    return proto
