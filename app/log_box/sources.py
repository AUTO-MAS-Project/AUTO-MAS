"""日志源：单个被采集文件的 tail 读取

与回调型 LogMonitor 不同，本模块面向主动拉取：LogSource 记录起始位置并支持
增量读取（offset 增量 + 轮转/截断处理），由 log_collect 直接持有。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Union

from app.utils import strptime

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
    - 轮转/截断：检测到文件 inode 变化或文件变小（被截断）时重置到文件头重读。
    - 时间过滤：配置 start_time/time_format/time_range 时，仅保留时间戳晚于
      起始时间的行（对齐 LogMonitor 的按时间起始过滤语义）。
    """

    def __init__(
        self,
        path: PathLike,
        *,
        start_from_end: bool = True,
        start_time: Optional[datetime] = None,
        time_format: str = "",
        time_range: tuple[int, int] = (0, 0),
    ):
        self.path = Path(path)
        self.start_from_end = start_from_end
        self.start_time = start_time
        self.time_format = time_format
        self.time_range = time_range
        self._offset = 0
        self._ino: Optional[int] = None
        self._opened = False

    def open(self) -> None:
        """记录起始位置（幂等）。文件不存在时从文件头开始（等待新文件生成）。"""
        self._offset = 0
        self._ino = None
        if self.path.is_file():
            stat = self.path.stat()
            if self.start_from_end:
                self._offset = stat.st_size
            self._ino = stat.st_ino
        self._opened = True

    def read_new(self) -> list[str]:
        """读取自上次位置以来的完整新行（含轮转/截断重读）

        Returns:
            新增的完整行列表；无新增或文件不存在时返回空列表
        """
        if not self._opened:
            return []
        try:
            stat = self.path.stat()
        except OSError:
            return []
        # 轮转（inode 变化）或截断（文件变小）→ 重置到文件头重读
        if self._ino is not None and (
            stat.st_ino != self._ino or stat.st_size < self._offset
        ):
            self._offset = 0
        self._ino = stat.st_ino
        if stat.st_size <= self._offset:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self._offset)
                raw = f.read()
        except OSError:
            return []
        # 只取最后一个换行之前的完整行；未闭合尾部留待下次追加
        last_nl = raw.rfind(b"\n")
        if last_nl == -1:
            return []
        self._offset += last_nl + 1
        text = raw[: last_nl + 1].decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if self.start_time is None:
            return lines
        return [line for line in lines if self._after_start(line)]

    def _after_start(self, line: str) -> bool:
        """按时间戳判断该行是否在起始时间之后（解析失败时保留该行）"""
        if not self.time_format or not self.time_range:
            return True
        try:
            entry_time = strptime(
                line[self.time_range[0] : self.time_range[1]],
                self.time_format,
                datetime.now(),
            )
        except (IndexError, ValueError):
            return True
        return entry_time > self.start_time
