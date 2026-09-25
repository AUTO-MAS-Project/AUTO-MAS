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
进度 / 速度 / ETA 上报抽象。

用一组回调（``ProgressListener``）把下载线程与展示层解耦，库与界面都能复用。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "ProgressSnapshot",
    "ProgressBase",
    "ProgressListener",
    "SilentProgressListener",
    "summarize_size",
]


def summarize_size(size: float) -> str:
    """把字节数格式化为人类可读字符串（1024 进制，保留 2 位小数）。

    ：按 B/KiB/MiB/GiB/TiB 递进，
    绝对值达到 1024 即升一档（``abs(size) < 1024`` 时停留在当前单位，故 ``1024``
    本身显示为 ``"1.00 KiB"``）；``B`` 档取整，其余档保留 2 位小数（如 ``1.5 GiB``）。

    Args:
        size: 字节数（可为任意数值）。

    Returns:
        带单位的体积字符串，如 ``"512 B"`` / ``"1.50 MiB"`` / ``"2.00 GiB"``。
    """
    size = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TiB"  # pragma: no cover


@dataclass
class ProgressSnapshot:
    """某一时刻的进度快照。"""

    activity: str = ""
    #: 所处阶段：``""`` 未标注、``verify`` 复核本地文件、``download`` 取数落盘
    stage: str = ""
    # 总进度
    total_size: int = 0
    current_size: int = 0
    total_count: int = 0
    current_count: int = 0
    # 单文件进度
    file_name: str = ""
    file_total_size: int = 0
    file_current_size: int = 0
    # 速率 / 剩余时间
    speed: float = 0.0
    time_left: float = 0.0

    @property
    def percentage(self) -> float:
        """总进度百分比（0–100）；``total_size <= 0`` 时返回 ``0.0``。"""
        if self.total_size <= 0:
            return 0.0
        return min(100.0, self.current_size / self.total_size * 100.0)


class ProgressBase:
    """线程安全的进度累加器 + 速度/ETA 计算。

    上报节流用 ``EMIT_INTERVAL_SEC``，速度用 ``SPEED_WINDOW_SEC`` 的滑动窗口——
    两者刻意分开：差分链路是「取回一段 → 停下打补丁 → 再取一段」，入账本身是
    整段一次性跳变，用 250ms 这么短的窗口算速度会把交替放大成尖峰与 0，
    界面上就是速度忽高忽低、剩余时间乱跳。
    """

    #: 两次上报的最小间隔（保持界面刷新手感）
    EMIT_INTERVAL_SEC = 0.25
    #: 速度滑动窗口长度；窗口未满时沿用上一个速度值
    SPEED_WINDOW_SEC = 1.0

    def __init__(self, listener: "Optional[ProgressListener]" = None) -> None:
        """初始化进度累加器与速率窗口。

        未传入 ``listener`` 时默认使用 :class:`SilentProgressListener`（静默）。
        内部用 :class:`threading.Lock` 保护快照，支持多线程并发 ``advance``。
        """
        self.listener = listener or SilentProgressListener()
        self._lock = threading.Lock()
        self._snapshot = ProgressSnapshot()
        self._last_emit = 0.0
        self._window_started = time.monotonic()
        self._window_bytes = 0

    # ---------------------------------------------------------------- 快照

    def snapshot(self) -> ProgressSnapshot:
        """返回当前进度快照的**拷贝**（加锁，避免调用方持有时被并发改写）。"""
        with self._lock:
            return ProgressSnapshot(**self._snapshot.__dict__)

    def _update(self, **kwargs: object) -> None:
        """在锁内覆盖快照字段（如 ``total_size=...`` / ``current_size=...``）。

        Args:
            **kwargs: 以 ``字段名=值`` 形式覆盖 :class:`ProgressSnapshot` 的字段。
        """
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._snapshot, key, value)

    # ---------------------------------------------------------------- 状态

    def set_activity(self, activity: str) -> None:
        """更新活动描述并立即强制上报一次。

        Args:
            activity: 当前活动文案（如「下载中」「校验中」）。
        """
        self._update(activity=activity)
        self.emit(force=True)

    def set_stage(self, stage: str, activity: str) -> None:
        """切换阶段并更新活动文案，立即强制上报一次。

        Args:
            stage: ``verify``（复核本地文件）或 ``download``（取数落盘）。
            activity: 与该阶段对应的活动文案。

        Note:
            文案不变、只换阶段时也强制上报，否则宿主那边按文本去重会把
            「开始下载」这条关键变化吞掉。
        """
        self._update(stage=stage, activity=activity)
        self.emit(force=True)

    def set_total(self, total_size: int = 0, total_count: int = 0) -> None:
        """设置总字节数与总文件数，并立即强制上报一次。

        Args:
            total_size: 预计总下载字节数。
            total_count: 预计总文件数。
        """
        self._update(total_size=total_size, total_count=total_count)
        self.emit(force=True)

    def set_current_file(self, file_name: str, file_size: int) -> None:
        """切换到下一个文件：记录文件名与大小，并把单文件已下载量归零。

        Args:
            file_name: 当前文件名（用于 UI 展示）。
            file_size: 当前文件总字节数。
        """
        self._update(
            file_name=file_name, file_total_size=file_size, file_current_size=0
        )
        self.emit(force=True)

    # ---------------------------------------------------------------- 累加

    def advance(self, size: int, count: int = 0) -> None:
        """累加已完成的字节数（以及可选的文件计数），并在锁内累加速率窗口。

        线程安全：多下载线程会并发调用本方法，所有累加都在 :class:`threading.Lock`
        保护下进行。

        Args:
            size: 本次新增的已完成字节数（应为非负）。
            count: 本次新增的已完成文件数，默认 ``0``。
        """
        with self._lock:
            self._snapshot.current_size += size
            self._snapshot.file_current_size += size
            self._snapshot.current_count += count
            self._window_bytes += size
        self.emit()

    def _recalculate_speed(self, force: bool) -> None:
        """按滑动窗口重算速度（字节/秒）与剩余时间。

        窗口未满 ``SPEED_WINDOW_SEC``（且非强制）时直接返回，沿用上次的速度值；
        速度 ≤ 0 或剩余字节 ≤ 0 时剩余时间归零。

        Args:
            force: 为 ``True`` 时忽略时间间隔限制，强制重算。
        """
        now = time.monotonic()
        elapsed = now - self._window_started
        # 开局还没有任何速度值时先按上报节奏算一次，否则刚开始下载会白显示 1 秒的
        # 0 B/s；之后仍按 1 秒窗口出数，这个初值会很快被修正
        cold_start = (
            self._snapshot.speed <= 0
            and self._window_bytes > 0
            and elapsed >= self.EMIT_INTERVAL_SEC
        )
        if not force and not cold_start and elapsed < self.SPEED_WINDOW_SEC:
            return
        if elapsed <= 0:
            return
        with self._lock:
            self._snapshot.speed = self._window_bytes / elapsed
            remaining = self._snapshot.total_size - self._snapshot.current_size
            if self._snapshot.speed > 0 and remaining > 0:
                self._snapshot.time_left = remaining / self._snapshot.speed
            else:
                self._snapshot.time_left = 0.0
            self._window_started = now
            self._window_bytes = 0

    # ---------------------------------------------------------------- 上报

    def emit(self, force: bool = False) -> None:
        """重新计算速度并（按节流间隔）把当前快照推送给 listener。

        Args:
            force: 为 ``True`` 时跳过节流，立即推送一次。
        """
        self._recalculate_speed(force)
        now = time.monotonic()
        if not force and now - self._last_emit < self.EMIT_INTERVAL_SEC:
            return
        self._last_emit = now
        self.listener.on_progress(self.snapshot())


class ProgressListener:
    """进度监听接口。子类按需覆写。"""

    def on_progress(self, snapshot: ProgressSnapshot) -> None:  # pragma: no cover
        """进度更新回调，子类按需覆写。

        Args:
            snapshot: 当前进度快照。
        """
        pass


class SilentProgressListener(ProgressListener):
    """什么都不做，供库调用方默认使用。"""
