"""日志源：单个被采集文件的 tail 读取

与回调型 LogMonitor 不同，本模块面向主动拉取：LogSource 记录起始位置并支持
增量读取（offset 增量 + 轮转/截断处理），由 log_collect 直接持有。
"""

from __future__ import annotations

import os
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
    - 轮转补偿：检测到文件身份变化时，先读取被轮换的旧日志（.bak 备份），
      再从头重读新文件，避免轮转前内容静默丢失。
    - 截断：文件变小（身份未变）时重置到文件头重读。
    """

    def __init__(
        self,
        path: PathLike,
        *,
        start_from_end: bool = True,
    ):
        self.path = Path(path)
        self.start_from_end = start_from_end
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
        """读取自上次位置以来的完整新行（含轮转 .bak 补偿 / 截断重读）

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
            # 轮转（文件身份变化）：先读被轮换的旧日志（.bak 补偿），再从头读新文件
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
            with open(self.path, "rb") as f:
                f.seek(self._offset)
                raw = f.read()
        except OSError:
            return []
        return self._decode_lines(raw)

    def _read_rotated(self) -> list[str]:
        """读取被轮换的旧日志（.bak 备份），避免轮转前内容静默丢失

        备份常见命名约定：``xxx.log`` → ``xxx.log.bak``（兼查 ``xxx.bak``）。
        备份被截断时从头读，避免遗漏尚未读过的内容；无备份则返回空列表。
        """
        for bak in self._bak_candidates():
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
                with open(bak, "rb") as f:
                    f.seek(offset)
                    raw = f.read()
            except OSError:
                continue
            return self._decode_lines(raw)
        return []

    def _bak_candidates(self) -> list[Path]:
        """轮转备份候选路径（按常见命名约定猜测，命中第一个存在的）"""
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
