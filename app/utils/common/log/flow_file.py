"""LogFlow 文件源的增量读取。

FlowFileSource 记录开始位置，按采集进程的轮询节奏交付完整行。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from stat import S_ISREG
from typing import BinaryIO, Optional, Union

from app.utils.common.tools import decode_bytes

if sys.platform == "win32":
    import ctypes
    import msvcrt

    import pywintypes
    import win32file

PathLike = Union[str, Path]


class LogReadLimitExceeded(ValueError):
    """一次增量超过已声明的读取预算。"""


@dataclass
class _ReadBatch:
    lines: list[str]
    offset: int
    has_more: bool = False


def file_identity(stat: os.stat_result) -> tuple[int, int]:
    """Windows 显式使用创建时间，路径与句柄返回的 ctime 可能不同。"""
    if sys.platform == "win32":
        return stat.st_ino, stat.st_birthtime_ns
    return stat.st_ino, stat.st_dev


LOG_READ_OPENER: Callable[[str, int], int] | None = None

if sys.platform == "win32":

    def _open_shared_read_fd(path: str, flags: int) -> int:
        """允许 Windows 上的日志写入者在采集器读文件时改名轮转。"""
        try:
            handle = win32file.CreateFile(
                path,
                win32file.GENERIC_READ,
                win32file.FILE_SHARE_READ
                | win32file.FILE_SHARE_WRITE
                | win32file.FILE_SHARE_DELETE,
                None,
                win32file.OPEN_EXISTING,
                win32file.FILE_ATTRIBUTE_NORMAL,
                None,
            )
        except pywintypes.error as exc:
            raise ctypes.WinError(exc.winerror) from exc
        try:
            descriptor = msvcrt.open_osfhandle(int(handle), flags | os.O_BINARY)
        except OSError:
            handle.Close()
            raise
        handle.Detach()  # 之后由 fd 关闭原生句柄。
        return descriptor

    LOG_READ_OPENER = _open_shared_read_fd


@dataclass(frozen=True)
class FileCursor:
    offset: int
    file_id: tuple[int, int] | None

    def __post_init__(self) -> None:
        if self.offset < 0 or (self.offset and self.file_id is None):
            raise ValueError("日志起点缺少有效的文件身份或偏移")


def capture_file_cursor(path: PathLike, *, start_from_end: bool) -> FileCursor:
    try:
        stat = Path(path).stat()
    except FileNotFoundError:
        return FileCursor(0, None)
    if not S_ISREG(stat.st_mode):
        raise ValueError("日志来源必须是普通文件")
    return FileCursor(stat.st_size if start_from_end else 0, file_identity(stat))


class FlowFileSource:
    """单个被采集文件的日志源

    - 起始位置：open() 记录；默认从当前文件末尾开始（仅采集会话内新增内容）。
    - 增量读取：read_new() 返回自上次位置以来的完整新行（未闭合行留待下次）。
    - 轮转补偿：检测到文件身份变化时，先找回被轮换的旧日志——有 inode 时
      一律按 inode 在同目录定位被重命名的旧文件（与 LogMonitor 同逻辑，
      宁缺勿错不猜名字）；文件系统不提供 inode 时才按命名探测（声明
      rotated_name 按模板，未声明回退 .bak 约定），再从头重读新文件，
      避免轮转前内容静默丢失。
    - 截断：文件变小（身份未变）时重置到文件头重读。
    """

    def __init__(
        self,
        path: PathLike,
        *,
        start_from_end: bool = True,
        rotated_name: Optional[str] = None,
        max_read_bytes: int | None = None,
    ) -> None:
        self.path = Path(path)
        self.start_from_end = start_from_end
        # 轮转文件名模板（完整文件名的 strftime 格式串，相对本目录）：
        # 有 inode 时轮转找回一律按 inode（与 LogMonitor 同逻辑），模板不
        # 参与；仅文件系统不提供 inode 时按模板探测（日期式滚动命名的唯一
        # 兜底），未声明则回退 .bak 通用约定
        self.rotated_name = rotated_name
        self.max_read_bytes = max_read_bytes
        self.has_more = False
        self.rotation_gap = ""
        self._offset = 0
        # 文件身份：Windows 沿用 inode + 创建时间；POSIX 使用 inode + 设备号，
        # 不能使用会随追加更新的 ctime，否则会把普通写入误判为轮转。
        self._file_id: Optional[tuple[int, int]] = None
        self._opened = False

    def open(self, *, cursor: FileCursor | None = None) -> None:
        """记录起始位置（幂等）。文件不存在时从文件头开始（等待新文件生成）。"""
        if cursor is None:
            cursor = capture_file_cursor(self.path, start_from_end=self.start_from_end)
        self._offset = cursor.offset
        self._file_id = cursor.file_id
        self.has_more = False
        self.rotation_gap = ""
        self._opened = True

    def read_new(self) -> list[str]:
        """读取自上次位置以来的完整新行（含轮转补偿 / 截断重读）

        Returns:
            新增的完整行列表；无新增或文件不存在时返回空列表
        """
        self.has_more = False
        if not self._opened:
            return []
        try:
            if not S_ISREG(self.path.stat().st_mode):
                raise OSError("日志来源必须是普通文件")
            file = open(self.path, "rb", opener=LOG_READ_OPENER)
        except FileNotFoundError:
            if self._file_id is None:
                return []
            # 轮转可能先改名，再创建当前文件。保留旧身份，供下轮继续排空。
            rotated = self._read_rotated(self._file_id)
            self._offset = rotated.offset
            self.has_more = rotated.has_more
            return rotated.lines
        with file:
            # 路径可能在 stat 与 open 之间被替换，以实际读取的句柄为准。
            stat = os.fstat(file.fileno())
            if not S_ISREG(stat.st_mode):
                raise OSError("日志来源必须是普通文件")
            current_id = file_identity(stat)
            offset = self._offset
            rotated_lines = []
            if self._file_id is not None and current_id != self._file_id:
                rotated = self._read_rotated(self._file_id)
                rotated_lines = rotated.lines
                if rotated.has_more:
                    self._offset = rotated.offset
                    self.has_more = True
                    return rotated_lines
                if rotated_lines and self.max_read_bytes is not None:
                    # 先交付已读完的旧批次。新文件独立读取，不影响旧节点交付。
                    self._file_id = current_id
                    self._offset = 0
                    self.has_more = stat.st_size > 0
                    return rotated_lines
                offset = 0
            elif stat.st_size < offset:
                offset = 0
            batch = self._read_stream(file, offset)
        self._file_id = current_id
        self._offset = batch.offset
        self.has_more = batch.has_more
        return rotated_lines + batch.lines

    def _read_rotated(self, file_id: tuple[int, int]) -> _ReadBatch:
        """读取被轮换的旧日志，避免轮转前内容静默丢失

        有 inode 时一律按 inode 在同目录找回被重命名的旧文件（与运行日志
        监控 LogMonitor 同一逻辑）：重命名不改变 inode，从原 offset 续读
        恰好是未读内容——不依赖命名猜测，也不会误读同名旧残留。inode 可用
        但未命中（旧文件已被删除、删除重建等非重命名式换身份）时不猜名字，
        宁缺勿错——声明了 ``rotated_name`` 也不猜，候选探测会命中昨天残留
        的轮转产物（上次零点轮转的正常产物几乎总在），把旧日志整份错当
        本次运行内容。文件系统不提供 inode（st_ino 为 0）时才回退命名
        探测：声明了 ``rotated_name`` 按昨天/今天的模板候选，未声明按
        ``.bak`` 通用约定。
        """
        if file_id[0]:
            batch = self._read_rotated_by_identity(file_id)
        else:
            batch = self._read_candidates()
        if batch is not None:
            return batch
        self.rotation_gap = "日志已轮转，无法定位上一个文件"
        return _ReadBatch([], self._offset)

    def _read_rotated_by_identity(self, file_id: tuple[int, int]) -> _ReadBatch | None:
        for candidate in self.path.parent.iterdir():
            if candidate == self.path:
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if not S_ISREG(stat.st_mode) or file_identity(stat) != file_id:
                continue
            try:
                with open(candidate, "rb", opener=LOG_READ_OPENER) as file:
                    if file_identity(os.fstat(file.fileno())) == file_id:
                        return self._read_stream(file, self._offset)
            except FileNotFoundError:
                continue
        return None

    def _read_candidates(self) -> _ReadBatch | None:
        """按候选路径探测旧日志，命中第一个存在且有未读内容的"""
        for bak in self._rotation_candidates():
            if not bak.is_file():
                continue
            try:
                stat = bak.stat()
            except OSError:
                continue
            offset = self._offset if self._offset <= stat.st_size else 0
            if stat.st_size <= offset:
                return _ReadBatch([], offset)  # 已找到排空的旧文件。
            with open(bak, "rb", opener=LOG_READ_OPENER) as file:
                return self._read_stream(file, offset)
        return None

    def _read_stream(self, file: BinaryIO, offset: int) -> _ReadBatch:
        file.seek(offset)
        has_more = False
        if self.max_read_bytes is None:
            raw = file.read()
        else:
            raw = file.read(self.max_read_bytes + 1)
            if len(raw) > self.max_read_bytes:
                has_more = True
                raw = raw[: self.max_read_bytes]
        start = 0
        if offset and raw:
            # 起点可能落在上一轮的未闭合行内，续写的部分也属于旧行。
            file.seek(offset - 1)
            if file.read(1) not in (b"", b"\n"):
                start = raw.find(b"\n") + 1
                if not start:
                    return _ReadBatch([], offset + len(raw), has_more)
        # 偏移只越过最后一个换行，未闭合尾部留待下次追加。
        end = raw.rfind(b"\n") + 1
        if end <= start:
            if not start and has_more:
                raise LogReadLimitExceeded("文件单行日志超过读取容量")
            return _ReadBatch([], offset + start, has_more)
        lines = [
            decode_bytes(line, encodings=("utf-8-sig", "gb18030"))
            for line in raw[start : end - 1].split(b"\n")
        ]
        return _ReadBatch(lines, offset + end, has_more)

    def _rotation_candidates(self) -> list[Path]:
        """轮转候选路径（按优先级，命中第一个存在且有未读内容的）

        仅在文件系统不提供 inode（st_ino 为 0）时使用：显式声明
        ``rotated_name``（完整轮转文件名的 strftime 模板，如
        ``ok-script.%Y-%m-%d.log``、``log.txt.%Y-%m-%d``）时按昨天/今天生成，
        昨天后缀是内容日期式命名的正主，今天后缀兜轮转时刻恰在零点边界
        的命名；未声明按 ``.bak`` 通用约定（``xxx.log`` → ``xxx.log.bak``，
        兼查 ``xxx.bak``）。offset 是在重命名前的同一文件上记录的，候选文件
        与它逐字节对应，从该位置续读即恰好是未读的旧内容。
        """
        if self.rotated_name:
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            return [
                self.path.with_name(yesterday.strftime(self.rotated_name)),
                self.path.with_name(today.strftime(self.rotated_name)),
            ]
        return [
            Path(str(self.path) + ".bak"),
            self.path.with_suffix(".bak"),
        ]
