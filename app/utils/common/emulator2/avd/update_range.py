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

#   Contact: DLmaster_361@163.com

"""魔改 AVD 更新：GitHub 的整包按区间只取变了的文件。

做法同 MaaFW 项目更新的区间增量（``app/task/MaaFW/tools/core/project_update/range_delta.py``），但那是
MaaFW 引擎自己的核心包、和它的载荷模型绑在一起（``app.utils`` 也不该依赖 ``app.task``），这里只用公共的
:func:`~app.services.common.update.transport.read_range`，按同样的思路、同样的阈值写一份最小的：

1. 用 HTTP Range 读包尾，找到中央目录，再读整个中央目录（几十 KB）；
2. 包里每个条目和根目录里同一路径的文件比 CRC32 + 大小：一样的从本地复制，不一样的才取回。包里的
   路径照整包的规则剥掉顶层目录、做安全检查（:func:`.update_stage.package_entries`）：新写法的主包是平铺的，
   旧 tag 的主包有同名外层文件夹；
3. 要取回的条目压缩后合计超过包的 :data:`MAX_FETCH_RATIO`，或条目数超过 :data:`MAX_FETCH_ENTRIES`，
   就不按区间取（:class:`RangeUnavailable`），由调用方改下整包；
4. 取回的条目交给标准库 ``zipfile`` 解压，它在读完时核对 CRC；拼好的 ``pkg`` 和整包解出来的一样，之后
   照样按新版清单逐文件核对，对不上同样退回整包。

任何一步失败（服务器不认 Range、回的区间不对、CRC 错……）都抛 :class:`RangeUnavailable`。这条路用不上
发布记录里整包的 SHA-256（整包没有下全，算不出来）：新写法版本必须带清单，逐文件比大小和 SHA-256，
和整包下载一样严。
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import struct
import zipfile
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.services.common.update import transport as _service_update_transport
from app.utils import get_logger
from app.utils import update_files as _utils_update_files

from . import update_stage as stage
from .update_source import RemoteAsset

logger = get_logger("魔改 AVD 更新")

#: 要取回的条目压缩后合计超过包的这个比例，或条目数超过上限，就改下整包（同 MaaFW 的取值）。
MAX_FETCH_RATIO = 0.4
MAX_FETCH_ENTRIES = 3000
#: 相邻两个要取的条目隔得不到这么多就合成一次 Range；一次最多要这么多（单个条目更大时它自己一组）。
MERGE_GAP_BYTES = 1024 * 1024
MAX_GROUP_BYTES = 8 * 1024 * 1024
#: 包尾先读这么多找中央目录结束记录（结束记录 22 字节 + 注释最长 64 KB）。
_TAIL_BYTES = 64 * 1024 + 22
#: 本地文件头比中央目录多出来的扩展字段估个余量。
_LOCAL_HEADER_SLACK = 1024
_LOCAL_HEADER_SIZE = 30
_EOCD = b"PK\x05\x06"
_CHUNK = 1024 * 1024


class RangeUnavailable(RuntimeError):
    """这次不能按区间取（变化太多、服务器不配合、取回的数据不对……），改下整包。"""


class _SparseFile(io.RawIOBase):
    """只读、可 seek 的「远端 zip」：只有取回过的几段有数据，读到别处就说明估错了，按不可用处理。"""

    def __init__(self, size: int) -> None:
        self.size = size
        self.segments: dict[int, bytes] = {}
        self.position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[
            whence
        ]
        self.position = base + offset
        return self.position

    def readinto(self, buffer) -> int:  # noqa: ANN001 - io 协议
        """尽量读满：一次读可能跨过两段相邻的数据（中央目录常常一半在包尾那段里）。"""
        wanted = min(len(buffer), max(self.size - self.position, 0))
        done = 0
        while done < wanted:
            for start, data in self.segments.items():
                if start <= self.position < start + len(data):
                    piece = data[
                        self.position - start : self.position - start + wanted - done
                    ]
                    buffer[done : done + len(piece)] = piece
                    done += len(piece)
                    self.position += len(piece)
                    break
            else:
                raise RangeUnavailable(
                    f"要读的位置 {self.position} 没有取回（本地文件头估短了）"
                )
        return done


@dataclass
class RangePlan:
    """按区间取的计划：``fetch`` 是要取回的条目，``copy`` 是从根目录复制的条目（都是 ``(包内路径, 条目)``）。"""

    asset: RemoteAsset
    archive: zipfile.ZipFile
    remote: _SparseFile
    fetch: list[tuple[str, zipfile.ZipInfo]]
    copy: list[tuple[str, zipfile.ZipInfo]]

    @property
    def fetch_bytes(self) -> int:
        return sum(_entry_span(info)[1] for _, info in self.fetch)

    @property
    def copy_bytes(self) -> int:
        return sum(info.file_size for _, info in self.copy)


def _entry_span(info: zipfile.ZipInfo) -> tuple[int, int]:
    """条目在包里大概占的区间 ``(起点, 长度)``：本地文件头 + 名字 + 扩展字段余量 + 压缩数据。"""
    name_length = len(
        info.orig_filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437")
    )
    length = (
        _LOCAL_HEADER_SIZE
        + name_length
        + len(info.extra)
        + _LOCAL_HEADER_SLACK
        + info.compress_size
    )
    return info.header_offset, length


def _same_as_local(root: Path, rel: str, info: zipfile.ZipInfo) -> bool:
    path = root / rel
    try:
        if os.path.getsize(_utils_update_files.native_path(path)) != info.file_size:
            return False
        crc = 0
        with open(_utils_update_files.native_path(path), "rb") as handle:
            while block := handle.read(_CHUNK):
                crc = zlib.crc32(block, crc)
    except OSError:
        return False
    return crc == info.CRC


async def plan_range(
    client: httpx.AsyncClient, asset: RemoteAsset, root: Path
) -> RangePlan:
    """读中央目录、和根目录逐文件比，定出要取回哪些条目。不划算或读不了抛 :class:`RangeUnavailable`。"""
    size = asset.size
    remote = _SparseFile(size)
    tail_start = max(0, size - _TAIL_BYTES)
    try:
        tail = await _service_update_transport.read_range(
            client,
            asset.url,
            offset=tail_start,
            length=size - tail_start,
            expected_total=size,
        )
        found = tail.rfind(_EOCD)
        if found < 0 or len(tail) - found < 22:
            raise RangeUnavailable("包尾找不到中央目录结束记录")
        entries, cd_size, cd_offset = struct.unpack(
            "<HII", tail[found + 10 : found + 20]
        )
        if entries == 0xFFFF or 0xFFFFFFFF in (cd_size, cd_offset):
            raise RangeUnavailable("包是 Zip64 格式，不按区间取")
        remote.segments[tail_start] = tail
        if cd_offset < tail_start:
            remote.segments[cd_offset] = await _service_update_transport.read_range(
                client,
                asset.url,
                offset=cd_offset,
                length=tail_start - cd_offset,
                expected_total=size,
            )
    except (httpx.HTTPError, ValueError) as e:
        detail = (
            f"HTTP {e.response.status_code}"
            if isinstance(e, httpx.HTTPStatusError)
            else f"{type(e).__name__}: {e}"
        )
        raise RangeUnavailable(f"按区间读包的目录没成（{detail}）") from None
    try:
        archive = zipfile.ZipFile(remote)
        listed = stage.package_entries(archive, asset.top_dir)
    except (zipfile.BadZipFile, OSError, RangeUnavailable) as e:
        raise RangeUnavailable(f"包的目录读不了: {e}") from e

    def compare() -> tuple[list, list]:
        fetch, copy = [], []
        for rel, info in listed:
            (copy if _same_as_local(root, rel, info) else fetch).append((rel, info))
        return fetch, copy

    fetch, copy = await asyncio.to_thread(compare)
    plan = RangePlan(asset, archive, remote, fetch, copy)
    if len(fetch) > MAX_FETCH_ENTRIES or plan.fetch_bytes > MAX_FETCH_RATIO * size:
        raise RangeUnavailable(
            f"变了 {len(fetch)} 个文件、约 {plan.fetch_bytes / 1024**2:.1f} MB，"
            f"超过整包的 {MAX_FETCH_RATIO:.0%}，直接下整包"
        )
    return plan


def _groups(fetch: list[tuple[str, zipfile.ZipInfo]]) -> list[tuple[int, int, list]]:
    """要取回的条目按位置排好，挨得近的合成一次 Range：``[(起点, 长度, 条目们)]``。"""
    groups: list[tuple[int, int, list]] = []
    for rel, info in sorted(fetch, key=lambda item: item[1].header_offset):
        start, length = _entry_span(info)
        if groups:
            group_start, group_length, members = groups[-1]
            end = max(group_start + group_length, start + length)
            if (
                start - (group_start + group_length) <= MERGE_GAP_BYTES
                and end - group_start <= MAX_GROUP_BYTES
            ):
                groups[-1] = (group_start, end - group_start, [*members, (rel, info)])
                continue
        groups.append((start, length, [(rel, info)]))
    return groups


def _extract(plan: RangePlan, members: list, dest: Path) -> None:
    for rel, info in members:
        target = _utils_update_files.resolve_within(dest, rel, resolve_links=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                plan.archive.open(info) as source,
                open(_utils_update_files.native_path(target), "wb") as sink,
            ):
                shutil.copyfileobj(source, sink, _CHUNK)
        except (zipfile.BadZipFile, zlib.error, EOFError) as e:
            raise RangeUnavailable(f"取回的 {rel} 校验不对: {e}") from e


async def fetch_changed(
    client: httpx.AsyncClient,
    plan: RangePlan,
    dest: Path,
    *,
    on_bytes: Callable[[int, int], Awaitable[None]],
) -> int:
    """把变了的条目取回、解到 ``dest``（先清空）。返回取回的字节数。"""
    stage.remove_tree(dest)
    dest.mkdir(parents=True)
    total = plan.fetch_bytes
    fetched = 0
    for start, length, members in _groups(plan.fetch):
        length = min(length, plan.asset.size - start)
        try:
            data = await _service_update_transport.read_range(
                client,
                plan.asset.url,
                offset=start,
                length=length,
                expected_total=plan.asset.size,
            )
        except (httpx.HTTPError, ValueError) as e:
            detail = (
                f"HTTP {e.response.status_code}"
                if isinstance(e, httpx.HTTPStatusError)
                else f"{type(e).__name__}: {e}"
            )
            raise RangeUnavailable(
                f"取回 {start}-{start + length - 1} 没成（{detail}）"
            ) from None
        plan.remote.segments[start] = data
        try:
            await asyncio.to_thread(_extract, plan, members, dest)
        finally:
            del plan.remote.segments[start]
        fetched += len(data)
        await on_bytes(fetched, total)
    return fetched


def copy_unchanged(
    root: Path,
    plan: RangePlan,
    dest: Path,
    progress: stage.Progress | None = None,
) -> None:
    """没变的条目从根目录复制进 ``dest``（在线程里跑）。"""
    total = plan.copy_bytes
    done = 0
    for rel, info in plan.copy:
        target = _utils_update_files.resolve_within(dest, rel, resolve_links=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            _utils_update_files.native_path(
                _utils_update_files.resolve_within(root, rel, resolve_links=False)
            ),
            _utils_update_files.native_path(target),
        )
        done += info.file_size
        if progress is not None:
            progress(done, total)


__all__ = [
    "MAX_FETCH_ENTRIES",
    "MAX_FETCH_RATIO",
    "RangePlan",
    "RangeUnavailable",
    "copy_unchanged",
    "fetch_changed",
    "plan_range",
]
