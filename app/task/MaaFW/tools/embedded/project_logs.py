#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""项目自己写进视图的日志：每次运行把本次新写的部分打码后另存进 history。

MAS 每次运行另存的还有 ``.worker.log``（runner 事件、worker 与 agent 的 stdout / stderr）和
``.maafw.log``（``debug/maafw.log`` 本次运行的部分）。项目 agent 自己写文件的日志原本只在
视图里：M9A 的 ``debug/custom/*.log``（DEBUG 级，控制台只出 INFO）与
``debug/agent-bootstrap.log``，MaaEnd go-service 的 ``debug/go-service.log``（控制台只出
Error）与 ``debug/go-service.stderr.log``（stderr 被重定向到这里，panic 只在这份里），MaaFgo
的 ``bbcdll/bbc_server.log`` 等。视图里的 ``.log`` 一定是运行期写出来的（投影在任何深度都剔
``.log``，载荷里没有），切换版本时按私有文件原样带过去。

做法与 ``.maafw.log`` 相同：运行开始时 :func:`snapshot_project_logs` 记下每个 ``.log`` 的
大小、开头与该位置之前的几百个字节，收尾时 :func:`copy_project_log_delta` 只取本次新写的部分，
拼成 ``history/…/<时分秒>.project.log``，每段前面一行分隔头。已有文件从记下的位置取到结尾；
新出现的、被轮转或截短（变小了）、被整个重写（开头或记下位置之前那一段变了）的从头取。
``debug/`` 顶层的 ``maafw.log`` / ``maafw.bak.*.log`` 不收（``.maafw.log`` 就是它）。

单个文件只留本次新增部分的末尾 :data:`PROJECT_LOG_TAIL_BYTES`，一次运行总量
:data:`PROJECT_LOG_TOTAL_BYTES`（``debug/`` 下的优先、同组里新写的优先），截掉多少写一行说明；
切口从下一行开始，不留半行（半行里可能是半个密码）。打码与 ``.maafw.log`` 同一口径：按字节把
密码的各种写法（``secret_log_variants``）在 UTF-8 / GBK / UTF-16LE 下的字节换成「<已隐藏>」
（``option_secrets.secret_byte_pairs``）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.utils import get_logger

from .option_secrets import redact_secret_bytes, secret_byte_pairs

logger = get_logger("MFW 项目日志")

PROJECT_LOG_TAIL_BYTES = 2 * 1024 * 1024
PROJECT_LOG_TOTAL_BYTES = 8 * 1024 * 1024
# 记开头这么多字节：收尾时开头变了就是整个重写过（``open(..., "w")`` 每次运行重开的日志），
# 从头取；只是往后追加的开头不变。
_HEAD_BYTES = 256
_LOG_SUFFIX = ".log"
# debug/ 顶层的原生日志：history 里的 .maafw.log 是它的按次副本（已打码），不重复收。
_NATIVE_LOG_RE = re.compile(r"^maafw(?:\.bak\..+)?\.log$", re.IGNORECASE)
# 不是项目日志的目录：字节码缓存、MAS 更新器保留目录、切换半成品。
_SKIP_DIR_NAMES = frozenset(
    {"__pycache__", ".pycache", ".mas-update", ".mas-update-cache", ".staging"}
)


@dataclass(frozen=True)
class LogMark:
    """运行开始时一个日志文件的状态。"""

    size: int
    head: bytes
    # 记下位置之前的最后几个字节：收尾时这一段没变才算「往后追加」，否则是整个重写过。
    tail: bytes = b""


@dataclass
class ProjectLogDelta:
    # 写进去的段（项目相对路径, 本次新增字节, 实际写入字节）。
    segments: list[tuple[str, int, int]] = field(default_factory=list)
    # 超出总量、一个字节都没写的（项目相对路径, 本次新增字节）。
    skipped: list[tuple[str, int]] = field(default_factory=list)
    written_bytes: int = 0


def list_project_logs(view: Path) -> list[tuple[str, Path]]:
    """视图里项目自己写的 ``.log``（项目相对 posix 路径, 绝对路径），按收集优先级排好。"""

    view = Path(view)
    found: list[tuple[bool, float, str, Path]] = []

    def _error(exc: OSError) -> None:
        logger.debug(f"读取视图目录失败，跳过: {exc.filename}: {exc}")

    for current, dir_names, file_names in os.walk(view, onerror=_error):
        dir_names[:] = sorted(
            name for name in dir_names if name.casefold() not in _SKIP_DIR_NAMES
        )
        base = Path(current)
        rel_dir = os.path.relpath(current, view).replace(os.sep, "/")
        prefix = "" if rel_dir == "." else f"{rel_dir}/"
        for name in file_names:
            if not name.casefold().endswith(_LOG_SUFFIX):
                continue
            if rel_dir.casefold() == "debug" and _NATIVE_LOG_RE.match(name):
                continue
            rel = f"{prefix}{name}"
            path = base / name
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            found.append((not rel.casefold().startswith("debug/"), -mtime, rel, path))
    found.sort()
    return [(rel, path) for _, _, rel, path in found]


def _read_head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(_HEAD_BYTES)


def _read_before(path: Path, end: int) -> bytes:
    """``end`` 之前的最后 ``_HEAD_BYTES`` 个字节。"""

    begin = max(0, end - _HEAD_BYTES)
    with path.open("rb") as handle:
        handle.seek(begin)
        return handle.read(end - begin)


def snapshot_project_logs(view: Path) -> dict[str, LogMark]:
    """运行开始时：视图里每个项目日志的大小与开头，按项目相对路径（小写）记。"""

    marks: dict[str, LogMark] = {}
    for rel, path in list_project_logs(view):
        try:
            size = path.stat().st_size
            marks[rel.casefold()] = LogMark(
                size, _read_head(path), _read_before(path, size)
            )
        except OSError:
            continue
    return marks


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _redact(data: bytes, secrets: Sequence[str]) -> bytes:
    return redact_secret_bytes(data, secret_byte_pairs(list(secrets)))


def _start_offset(path: Path, size: int, mark: LogMark | None) -> int:
    """本次新写的部分从哪开始：已有且只是往后追加的（开头与记下位置之前的一段都没变）从
    记下的位置，其余从头——开头一样但被整个重写过的（每次运行先写同一段横幅的日志）靠
    位置之前那一段对不上认出来。"""

    if mark is None or size < mark.size:
        return 0
    try:
        head = _read_head(path)
        before = _read_before(path, mark.size)
    except OSError:
        return 0
    if head[: len(mark.head)] != mark.head or before != mark.tail:
        return 0
    return mark.size


def _read_range(path: Path, start: int, end: int, limit: int) -> tuple[bytes, int]:
    """读 ``[start, end)`` 里的最后 ``limit`` 字节（不够一整段时从下一行开始）。返回
    ``(内容, 截掉的字节)``。"""

    begin = max(start, end - limit)
    with path.open("rb") as handle:
        handle.seek(begin)
        data = handle.read(end - begin)
    if begin > start:
        newline = data.find(b"\n")
        data = data[newline + 1 :] if newline != -1 else b""
    return data, (end - start) - len(data)


def copy_project_log_delta(
    view: Path,
    marks: Mapping[str, LogMark],
    target: Path,
    *,
    secrets: Sequence[str] = (),
    tail_bytes: int = PROJECT_LOG_TAIL_BYTES,
    total_bytes: int = PROJECT_LOG_TOTAL_BYTES,
) -> ProjectLogDelta:
    """把视图里项目日志本次新写的部分（相对 ``marks``）打码后拼进 ``target``。

    没有任何新内容时不建文件。视图一个字节不动；读不了的文件跳过（正被独占写的、刚被轮转掉的）。
    """

    result = ProjectLogDelta()
    remaining = max(0, int(total_bytes))
    chunks: list[bytes] = []
    for rel, path in list_project_logs(view):
        try:
            size = path.stat().st_size
            start = _start_offset(path, size, marks.get(rel.casefold()))
        except OSError as exc:
            logger.debug(f"读取项目日志失败，跳过: {rel}: {exc}")
            continue
        added = size - start
        if added <= 0:
            continue
        if remaining <= 0:
            result.skipped.append((rel, added))
            continue
        try:
            data, cut = _read_range(path, start, size, min(tail_bytes, remaining))
        except OSError as exc:
            logger.debug(f"读取项目日志失败，跳过: {rel}: {exc}")
            continue
        if not data:
            # 能用的额度里放不下一整行：不写半行，按没收记下。
            result.skipped.append((rel, added))
            continue
        header = f"===== {rel}（本次新增 {_format_size(added)}）=====\n"
        if cut:
            header += (
                f"（只保留本次新增部分的末尾 {_format_size(len(data))}，"
                f"前面 {_format_size(cut)} 已截掉）\n"
            )
        if not data.endswith(b"\n"):
            data += b"\n"
        data = _redact(data, secrets)
        header_bytes = header.encode("utf-8")
        chunks.append(header_bytes + data)
        # 分隔头也算进总量，整份文件不超过上限（最多多出下一段的分隔头）。
        remaining -= len(header_bytes) + len(data)
        result.written_bytes += len(data)
        result.segments.append((rel, added, len(data)))
    if result.skipped:
        total = sum(added for _, added in result.skipped)
        names = "、".join(rel for rel, _ in result.skipped[:10])
        more = " 等" if len(result.skipped) > 10 else ""
        chunks.append(
            (
                f"===== 超出本次 {_format_size(total_bytes)} 总量上限，另有 "
                f"{len(result.skipped)} 个文件共 {_format_size(total)} 没保存：{names}{more} =====\n"
            ).encode("utf-8")
        )
    if chunks:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("ab") as handle:
            for chunk in chunks:
                handle.write(chunk)
    return result


__all__ = [
    "PROJECT_LOG_TAIL_BYTES",
    "PROJECT_LOG_TOTAL_BYTES",
    "LogMark",
    "ProjectLogDelta",
    "copy_project_log_delta",
    "list_project_logs",
    "snapshot_project_logs",
]
