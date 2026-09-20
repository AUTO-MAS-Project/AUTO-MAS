"""日志源：单个被采集文件的 tail 读取

与回调型 LogMonitor 不同，本模块面向主动拉取：LogSource 记录起始位置并支持
增量读取（offset 增量 + 轮转/截断处理），由 log_collect 直接持有。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Union

PathLike = Union[str, Path]

# 脚本宿主缺省日志位置的注入环境变量（由 MAS 侧在拉起脚本时设置）
_DEFAULT_PATHS_ENV = "MAS_SCRIPT_LOG_PATH"


def resolve_sources(paths: Optional[Union[PathLike, Iterable[PathLike]]]) -> list[Path]:
    """把 str/Path/Iterable 归一为路径列表

    None 时回退到环境变量 ``MAS_SCRIPT_LOG_PATH``（分号分隔，MAS 配置的日志
    位置）；未设置则返回空列表。MAS 进程宿主（专项适配器）始终显式传参。
    """
    if paths is None:
        raw = os.environ.get(_DEFAULT_PATHS_ENV, "").strip()
        return [Path(item) for item in raw.split(";") if item.strip()] if raw else []
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(item) for item in paths]


class LogSource:
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
    ):
        self.path = Path(path)
        self.start_from_end = start_from_end
        # 轮转文件名模板（完整文件名的 strftime 格式串，相对本目录）：
        # 有 inode 时轮转找回一律按 inode（与 LogMonitor 同逻辑），模板不
        # 参与；仅文件系统不提供 inode 时按模板探测（日期式滚动命名的唯一
        # 兜底），未声明则回退 .bak 通用约定
        self.rotated_name = rotated_name
        self._offset = 0
        # 文件身份：轮转/替换检测用。Windows 下 st_ino 不可靠，追加 st_ctime_ns
        # （Windows 为创建时间，文件被替换时变化），两者任一变化即视为轮转。
        self._file_id: Optional[tuple[int, int]] = None
        self._opened = False

    def open(self) -> None:
        """记录起始位置（幂等）。文件不存在时从文件头开始（等待新文件生成）。"""
        self._offset = 0
        self._file_id = None
        if self.path.is_file():
            stat = self.path.stat()
            if self.start_from_end:
                self._offset = stat.st_size
            self._file_id = (stat.st_ino, stat.st_ctime_ns)
        self._opened = True

    def read_new(self) -> list[str]:
        """读取自上次位置以来的完整新行（含轮转补偿 / 截断重读）

        Returns:
            新增的完整行列表；无新增或文件不存在时返回空列表
        """
        if not self._opened:
            return []
        try:
            stat = self.path.stat()
        except OSError:
            return []
        current_id = (stat.st_ino, stat.st_ctime_ns)
        if self._file_id is not None and current_id != self._file_id:
            # 轮转（文件身份变化）：先读被轮换的旧日志，再从头读新文件
            lines = self._read_rotated()
            self._offset = 0
            lines.extend(self._read_tail())
        elif stat.st_size < self._offset:
            # 截断（文件变小但身份未变）：重置到文件头重读
            self._offset = 0
            lines = self._read_tail()
        else:
            lines = self._read_tail()
        self._file_id = current_id
        return lines

    def _read_tail(self) -> list[str]:
        """从当前 offset 读取新增的完整行；无新增或文件不存在时返回空列表"""
        try:
            stat = self.path.stat()
        except OSError:
            return []
        if stat.st_size <= self._offset:
            return []
        try:
            return self._read_from(self.path, self._offset)
        except OSError:
            return []

    def _read_rotated(self) -> list[str]:
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
        old_ino = self._file_id[0] if self._file_id is not None else 0
        if old_ino:
            rotated = self._find_rotated_file(old_ino)
            if rotated is not None:
                try:
                    return self._read_from(rotated, self._offset)
                except OSError:
                    return []
            return []
        return self._read_candidates()

    def _find_rotated_file(self, old_ino: int) -> Path | None:
        """在同目录里按 inode 找回被重命名的旧日志文件（与 LogMonitor 同逻辑）

        重命名前后是同一文件，离开时记录的 offset 逐字节对应。st_ino 为 0
        （文件系统不提供 inode）或未找到（旧文件已被删除）时返回 None。
        """
        if not old_ino:
            return None
        try:
            for candidate in self.path.parent.iterdir():
                if candidate == self.path or not candidate.is_file():
                    continue
                try:
                    if candidate.stat().st_ino == old_ino:
                        return candidate
                except OSError:
                    continue
        except OSError:
            return None
        return None

    def _read_candidates(self) -> list[str]:
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
                continue
            try:
                return self._read_from(bak, offset)
            except OSError:
                continue
        return []

    def _read_from(self, path: Path, offset: int) -> list[str]:
        """从 path 的 offset 起读取字节并按行解码；文件访问错误向上抛出"""
        with open(path, "rb") as f:
            f.seek(offset)
            raw = f.read()
        return self._decode_lines(raw)

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

    def _decode_lines(self, raw: bytes) -> list[str]:
        """把按字节读取的内容切成完整行

        只取最后一个换行之前的完整行；未闭合尾部留待下次追加（offset 不越过它）。
        """
        last_nl = raw.rfind(b"\n")
        if last_nl == -1:
            return []
        self._offset += last_nl + 1
        text = raw[: last_nl + 1].decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return lines
