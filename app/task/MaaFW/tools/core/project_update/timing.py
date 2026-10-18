"""更新各段的计时与给人看的用时文案（纯函数，零宿主耦合）。

新版本构建分好几段（下载 → 解压 → 比对 → 复制旧版本 → 套用更新包 → 预检 → 并入共用库 →
生成清单），生产上一次 359 MB 的更新在「下载完成」之后近 6 分钟没有任何日志，看不出慢在
哪一段。每段结束的那行日志都带用时，收尾再打一行分段汇总；用时的写法只在这里定一次。
"""

from __future__ import annotations

import time
from collections.abc import Callable

_BYTES_PER_MB = 1024 * 1024
# 汇总里没归到任何一段的零头（找包根、读版本号、清理解压目录……）够这么长才单列「其他」。
_OTHER_MIN_SECONDS = 0.5


def format_duration(seconds: float) -> str:
    """用时 → 「12.3 秒」（60 秒以下，一位小数）/「1 分 46 秒」/「1 小时 2 分」。

    一律向下取整到显示精度：四舍五入会把 59.96 说成「60.0 秒」、119.7 说成「2 分 0 秒」。
    """

    value = max(0.0, float(seconds or 0.0))
    if value < 60:
        # 加一点余量再截：2.3 * 10 在浮点里是 22.999…，直接截会说成「2.2 秒」。
        return f"{int(value * 10 + 1e-6) / 10:.1f} 秒"
    total = int(value)
    if total < 3600:
        return f"{total // 60} 分 {total % 60} 秒"
    return f"{total // 3600} 小时 {(total % 3600) // 60} 分"


def format_megabytes(size: int | float | None) -> str:
    """字节数 → 「342.9 MB」。"""

    return f"{(size or 0) / _BYTES_PER_MB:.1f} MB"


class StageTimer:
    """按顺序计各段用时；同名段可以多次进出，时间累加。

    ``current`` 是正在计时的段名，失败 / 取消时拿它说「在哪一段停下的」。只在一次更新里
    顺序使用（跨线程也是先后交接，不并发），不加锁。
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._current: str | None = None
        self._last: str | None = None
        self._current_started = self._started
        self.durations: dict[str, float] = {}

    @property
    def current(self) -> str | None:
        """正在计时的段；段与段之间为 None。"""

        return self._current

    @property
    def last(self) -> str | None:
        """最近进入过的段（收掉之后也还在）。"""

        return self._last

    def start(self, name: str) -> None:
        """进入一段；上一段没收就先收掉。"""

        if self._current is not None:
            self.finish()
        self._current = name
        self._last = name
        self._current_started = self._clock()

    def finish(self) -> float:
        """收掉当前段，返回这段的用时；没有在计的段时返回 0。"""

        if self._current is None:
            return 0.0
        elapsed = max(0.0, self._clock() - self._current_started)
        self.durations[self._current] = self.durations.get(self._current, 0.0) + elapsed
        self._current = None
        return elapsed

    def elapsed(self) -> float:
        """从建这个计时器到现在的总用时。"""

        return max(0.0, self._clock() - self._started)

    def summary(self) -> str:
        """「1 分 8 秒（下载 1 分 8 秒，解压 12.3 秒，…）」：总用时 + 各段明细。"""

        total = self.elapsed()
        parts = [
            f"{name} {format_duration(value)}" for name, value in self.durations.items()
        ]
        other = total - sum(self.durations.values())
        if other >= _OTHER_MIN_SECONDS:
            parts.append(f"其他 {format_duration(other)}")
        detail = f"（{'，'.join(parts)}）" if parts else ""
        return f"{format_duration(total)}{detail}"


__all__ = ["StageTimer", "format_duration", "format_megabytes"]
