#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""通过 HTTP Range 预读远端分卷 ZIP 的文件索引和校验清单。

下载更新包前，先获取文件大小，用于估算下载与更新所需的磁盘空间。
预读失败时由调用方继续下载，下载后再检查空间。
服务器不支持 Range 时停止预读，避免意外下载整个分卷。
"""

from __future__ import annotations

import io
import json
import struct
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from typing import Any, NamedTuple

import httpx
import pyzipper

from app.services.common.update import transport as _service_update_transport
from app.utils import get_logger

logger = get_logger("终末地包内索引")

_LOCAL_SIGNATURE = b"PK\x03\x04"
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_EXTRA_ID = 0x0001
"""zip 容器里各段记录的固定标记。中央目录条目要原样搬进合成档案，只改体积与偏移那几个字段：
口令加密成员自带的扩展信息一动，解出来只会是一句误导人的 Bad password。"""

_SENTINEL32 = 0xFFFFFFFF
"""32 位字段装不下真值时 zip 写的哨兵，真值在同条记录的 ZIP64 扩展信息里。"""

_TAIL_BYTES = 128 * 1024
"""尾部读取窗口；中央目录未完整包含在窗口内时另发请求。"""

_HEADER_SLACK = 128
"""取正文时顺带取回本地头的余量。本地头自己报的文件名与扩展字段长度决定正文从哪儿开始，
而中央目录给的那两个长度并不一定和它相等。"""

_MAX_CENTRAL_DIR_BYTES = 4 * 1024**2
"""中央目录读取上限，避免预读占用过多内存。"""

_CENTRAL_FIXED = 46
_CENTRAL_FIELDS = "<HHHHHHIIIHHHHHII"
"""中央目录条目去掉签名后的固定段。"""

_LOCAL_FIXED = 30
_PLAIN_CHUNK = 64 * 1024


class RemoteVolume(NamedTuple):
    """差量包一个分卷的下载地址与体积。"""

    url: str
    size: int


class _Entry(NamedTuple):
    """中央目录里的一条成员记录。"""

    name: str
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int
    raw: bytes
    """这条记录在中央目录里的原始字节，拼合成档案时原样复用。"""


class _Unreadable(RuntimeError):
    """结构不认识；调用方按「读不到」处理，不影响主流程。"""


def volume_spans(
    sizes: Sequence[int], offset: int, length: int
) -> list[tuple[int, int, int]]:
    """把拼接流上的一个区间拆成「第几卷、卷内偏移、这段多长」。

    整包是单条 zip 的纯字节切片，逻辑坐标因此会跨卷；跨卷就得按卷各取一次。

    体积为 0 的卷不需要单独拦：`bisect_right` 在同值起点里取最后一个，落点必定是有长度
    的那一卷，而 `at < cursor` 保证末尾的空卷选不中，每次 `take` 至少为 1。清单里出现 0
    体积卷也只会在上面那道越界检查里判掉，不会走到这里少算一整卷。
    """
    if offset < 0 or length < 0:
        raise ValueError(f"区间不可用: offset={offset} length={length}")
    starts: list[int] = []
    cursor = 0
    for size in sizes:
        starts.append(cursor)
        cursor += size
    if offset + length > cursor:
        raise ValueError(f"区间越过拼接流末尾: {offset}+{length} > {cursor}")
    spans: list[tuple[int, int, int]] = []
    remaining = length
    at = offset
    while remaining:
        index = bisect_right(starts, at) - 1
        local = at - starts[index]
        take = min(remaining, sizes[index] - local)
        spans.append((index, local, take))
        at += take
        remaining -= take
    return spans


async def _read_span(
    client: httpx.AsyncClient,
    volumes: Sequence[RemoteVolume],
    offset: int,
    length: int,
) -> bytes:
    """按逻辑坐标取出连续字节，跨卷时逐卷各发一次 `Range`。"""
    sizes = [volume.size for volume in volumes]
    pieces: list[bytes] = []
    for index, local, take in volume_spans(sizes, offset, length):
        volume = volumes[index]
        pieces.append(
            await _service_update_transport.read_range(
                client,
                volume.url,
                offset=local,
                length=take,
                expected_total=volume.size,
            )
        )
    return b"".join(pieces)


def _central_dir_bounds(tail: bytes, tail_start: int) -> tuple[int, int, int]:
    """解析 ZIP 尾部记录，返回中央目录的偏移、字节长度和条目数。

    支持普通 ZIP 和 ZIP64。记录缺失或信息无效时停止预读，
    由调用方下载完整更新包后再解析。
    """
    locator_at = tail.rfind(_ZIP64_LOCATOR_SIGNATURE)
    if locator_at >= 0:
        _, zip64_at, disks = struct.unpack_from("<IQI", tail, locator_at + 4)
        if disks != 1:
            raise _Unreadable(f"差量包自称跨了 {disks} 块磁盘")
        at = zip64_at - tail_start
        if at < 0 or tail[at : at + 4] != _ZIP64_EOCD_SIGNATURE:
            raise _Unreadable("ZIP64 结尾定位器指不到自己的结尾记录")
        # 记录里依次是长度、两个版本号、本磁盘号、中央目录起始磁盘号、两个条目数、中央目录长度与起点
        fields = struct.unpack_from("<QHHIIQQQQ", tail, at + 4)
        if fields[3] or fields[4]:
            raise _Unreadable("中央目录不落在第一块磁盘上")
        return fields[8], fields[7], fields[6]

    eocd_at = tail.rfind(_EOCD_SIGNATURE)
    if eocd_at < 0:
        raise _Unreadable("尾部窗口里没有结尾记录")
    # 固定段里用到的：[0]本磁盘号 [1]中央目录起始磁盘号 [2..3]两个条目数 [4]中央目录长度 [5]中央目录起点
    fields = struct.unpack_from("<HHHHIIH", tail, eocd_at + 4)
    if 0xFFFF in (fields[2], fields[3]) or _SENTINEL32 in (fields[4], fields[5]):
        raise _Unreadable("结尾记录的字段已写成哨兵，却没有 ZIP64 结尾记录")
    if fields[0] or fields[1]:
        raise _Unreadable("中央目录不落在第一块磁盘上")
    return fields[5], fields[4], fields[3]


def _zip64_values(extra: bytes) -> list[int]:
    """按序取出 ZIP64 扩展信息里的 8 字节字段；没有这个扩展就给空表。"""
    cursor = 0
    while cursor + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, cursor)
        body = extra[cursor + 4 : cursor + 4 + size]
        if len(body) != size:
            raise _Unreadable(f"扩展字段 {header_id:#06x} 报的长度越界")
        if header_id == _ZIP64_EXTRA_ID:
            return [
                int.from_bytes(body[step : step + 8], "little")
                for step in range(0, len(body) - len(body) % 8, 8)
            ]
        cursor += 4 + size
    return []


def _entry(
    name: str, raw: bytes, usize: int, csize: int, offset: int, extra: bytes
) -> _Entry:
    """补出一条中央目录记录：32 位字段写成哨兵时，真值在 ZIP64 扩展信息里按序给。

    那个顺序就是解压体积、压缩体积、本地头偏移，认错了会把正文读到几 GiB 之外去。
    """
    if _SENTINEL32 in (usize, csize, offset):
        values = _zip64_values(extra)
        if len(values) < sum(value == _SENTINEL32 for value in (usize, csize, offset)):
            raise _Unreadable(f"{name} 的 ZIP64 扩展信息缺字段")
        step = 0
        if usize == _SENTINEL32:
            usize = values[step]
            step += 1
        if csize == _SENTINEL32:
            csize = values[step]
            step += 1
        if offset == _SENTINEL32:
            offset = values[step]
    return _Entry(
        name=name,
        compressed_size=csize,
        uncompressed_size=usize,
        local_header_offset=offset,
        raw=raw,
    )


def _iter_central(cd: bytes, declared: int, wanted: set[str]) -> Iterator[_Entry]:
    """按中央目录逐条走一遍，补出 `wanted` 里那些成员的记录。

    走到底才发现条数与结尾记录声明的对不上，同样停止解析——只认前几条会让体积读取假数。
    """

    at = 0
    count = 0
    while at < len(cd):
        if cd[at : at + 4] != _CENTRAL_SIGNATURE:
            raise _Unreadable(f"中央目录第 {count + 1} 条不是成员记录")
        # 46 字节固定段里用到的：[7]压缩体积 [8]解压体积 [9..11]名/扩展/注释长度
        # [2]通用位标记 [15]本地头偏移
        fields = struct.unpack_from(_CENTRAL_FIELDS, cd, at + 4)
        name_len, extra_len, comment_len = fields[9], fields[10], fields[11]
        size = _CENTRAL_FIXED + name_len + extra_len + comment_len
        if at + size > len(cd):
            raise _Unreadable("中央目录末尾被截断")
        raw = cd[at : at + size]
        count += 1
        name = raw[_CENTRAL_FIXED : _CENTRAL_FIXED + name_len].decode(
            "utf-8" if fields[2] & 0x800 else "cp437", "replace"
        )
        if name in wanted:
            yield _entry(
                name=name,
                raw=raw,
                usize=fields[8],
                csize=fields[7],
                offset=fields[15],
                extra=raw[
                    _CENTRAL_FIXED + name_len : _CENTRAL_FIXED + name_len + extra_len
                ],
            )
        at += size
    if count != declared:
        raise _Unreadable(f"中央目录实有 {count} 条，与结尾声明的 {declared} 条不符")


async def _central_directory(
    client: httpx.AsyncClient, volumes: Sequence[RemoteVolume]
) -> tuple[bytes, int]:
    """取回整张中央目录：尾部一次 Range，没盖满时按坐标补取一次。"""

    total = sum(volume.size for volume in volumes)
    tail_start = max(total - _TAIL_BYTES, 0)
    tail = await _read_span(client, volumes, tail_start, total - tail_start)
    cd_offset, cd_size, declared = _central_dir_bounds(tail, tail_start)
    if cd_size > _MAX_CENTRAL_DIR_BYTES:
        raise _Unreadable(f"中央目录有 {cd_size} 字节，超出上限")
    if cd_offset + cd_size > total:
        raise _Unreadable(f"中央目录区间越过流末尾: {cd_offset}+{cd_size} > {total}")
    covered_from = cd_offset - tail_start
    if covered_from >= 0 and covered_from + cd_size <= len(tail):
        return tail[covered_from : covered_from + cd_size], declared
    # 尾部窗口没盖满中央目录（成员太多、中央目录比窗口还长）时按坐标补取一次
    return await _read_span(client, volumes, cd_offset, cd_size), declared


def _single_member_archive(header: bytes, cipher: bytes, entry: _Entry) -> bytes:
    """把「本地头 + 正文 + 中央目录条目」拼成一个只含该成员的单文件 zip。"""
    if max(entry.compressed_size, entry.uncompressed_size) >= _SENTINEL32:
        raise _Unreadable(f"{entry.name} 声明的体积超出 32 位字段")
    central = bytearray(entry.raw)
    # 合成档案只有这一个成员，字段全写满真值：zipfile 只在 32 位字段是哨兵时才去扩展信息里
    # 取体积与偏移，留着原值它就把正文当成在几 GiB 之外
    struct.pack_into("<I", central, 20, entry.compressed_size)
    struct.pack_into("<I", central, 24, entry.uncompressed_size)
    struct.pack_into("<I", central, 42, 0)
    struct.pack_into("<H", central, 34, 0)
    central_start = len(header) + len(cipher)
    eocd = _EOCD_SIGNATURE + struct.pack(
        "<HHHHIIH", 0, 0, 1, 1, len(central), central_start, 0
    )
    # 中央目录必须紧贴结尾记录：zipfile 会把「结尾记录位置 - 中央目录长度 - 中央目录起点」当作偏移
    # 修正量加到每条记录上，这个量在这里只能是 0
    return header + cipher + bytes(central) + eocd


async def _decrypt_member(
    blob: bytes, entry: _Entry, cd_key: str, max_plain_bytes: int
) -> bytes:
    """用差量包口令解出合成档案里那一个成员，并核对长度。"""
    archive = pyzipper.AESZipFile(io.BytesIO(blob))
    try:
        archive.setpassword(cd_key.encode())
        info = archive.infolist()[0]
        if info.filename != entry.name:
            raise _Unreadable(f"合成档案里的成员名是 {info.filename}")
        plain = bytearray()
        with archive.open(info) as source:
            while chunk := source.read(_PLAIN_CHUNK):
                plain += chunk
                if len(plain) > max_plain_bytes:
                    raise _Unreadable(f"解出的正文超过上限 {max_plain_bytes} 字节")
    finally:
        archive.close()
    if len(plain) != entry.uncompressed_size:
        raise _Unreadable(
            f"解出 {len(plain)} 字节，与中央目录声明的 {entry.uncompressed_size} 不符"
        )
    return bytes(plain)


async def _read_member_json(
    client: httpx.AsyncClient,
    volumes: Sequence[RemoteVolume],
    cd_key: str,
    entry: _Entry,
    max_plain_bytes: int,
) -> dict[str, Any]:
    member = entry.name

    # 读取正文前检查压缩和解压大小，控制预读内存占用。
    if entry.uncompressed_size > max_plain_bytes:
        raise _Unreadable(
            f"{member} 声明的解压体积 {entry.uncompressed_size} 超出上限 {max_plain_bytes}"
        )
    if entry.compressed_size > max_plain_bytes + _HEADER_SLACK:
        raise _Unreadable(
            f"{member} 声明的压缩体积 {entry.compressed_size} 超出上限 {max_plain_bytes}"
        )
    window = await _read_span(
        client,
        volumes,
        entry.local_header_offset,
        entry.compressed_size + _HEADER_SLACK,
    )
    if window[:4] != _LOCAL_SIGNATURE:
        raise _Unreadable("本地头签名不对")
    # 正文的位置只认本地头自己报的这两个长度：中央目录条目给的那一份和它并不一定相等
    name_len, extra_len = struct.unpack_from("<HH", window, 26)
    header_at = _LOCAL_FIXED + name_len + extra_len
    if header_at > _HEADER_SLACK:
        raise _Unreadable(f"本地头有 {header_at} 字节，超出预取的余量")
    cipher_at = header_at + entry.compressed_size
    plain = await _decrypt_member(
        _single_member_archive(window[:header_at], window[header_at:cipher_at], entry),
        entry,
        cd_key,
        max_plain_bytes,
    )
    doc = json.loads(plain.decode("utf-8"))
    if not isinstance(doc, dict):
        raise _Unreadable(f"{member} 顶层不是 JSON 对象")
    return doc


async def fetch_package_metadata(
    *,
    client: httpx.AsyncClient,
    volumes: Sequence[RemoteVolume],
    cd_key: str,
    member: str,
    members: Sequence[str],
    max_plain_bytes: int,
) -> tuple[dict[str, Any] | None, dict[str, int] | None]:
    """读取一次中央目录，返回 JSON 清单和指定成员的展开大小。

    任一结果为 None 表示该项预读失败，不等同于空清单或零大小。
    网络与格式错误不阻断更新，取消仍会向上传播。
    """
    wanted = set(members)
    try:
        cd, declared = await _central_directory(client, volumes)
        entries = {
            entry.name: entry
            for entry in _iter_central(cd, declared, wanted | {member})
        }
    except Exception as error:
        logger.warning(f"未能预读中央目录：{type(error).__name__}: {error}")
        return None, None

    sizes = (
        {name: entries[name].uncompressed_size for name in wanted}
        if wanted.issubset(entries)
        else None
    )
    if sizes is None:
        logger.warning("中央目录缺少部分差量成员，无法完整预估展开大小")
    try:
        if member not in entries:
            raise _Unreadable(f"中央目录里没有 {member}")
        doc = await _read_member_json(
            client, volumes, cd_key, entries[member], max_plain_bytes
        )
    except Exception as error:
        logger.warning(f"未能预读 {member}：{type(error).__name__}: {error}")
        doc = None
    return doc, sizes
