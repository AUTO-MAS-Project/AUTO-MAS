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

"""气球开着时，开机后「突发读盘」读完就在客体清一次页缓存（用户 10-04 定的规则）。

每台虚拟机每天第一次开机，``system_server`` 会在 20–42 秒读 4–5 GB（10-04 iotrace 实测 5.3 GB），
客体缓存冲到 4–5 GB；气球只还空闲页，这部分缓存不清就整场不还给宿主。平时开机读得远少于这个量，
清了反而让游戏启动重新读盘，所以只在真有突发读盘时清：

1. 客体开机约 60 秒开始判断，读 ``system_server`` 的 ``read_bytes``；
2. 不到 2 GB：这次开机没有突发读盘，不清；
3. 超过 2 GB：每 5 秒再读一次，增量小于 50 MB 算读完，立刻清一次；
4. 客体开机到 180 秒还没读完：放弃，不清。

每次开机最多判断 / 清一次：判完就在客体打标记（``debug.mas.dropped``，属性重启即失效），之后
不管是同一后端再次 open、换了后端进程还是重新连上，看到标记都跳过。判断逻辑只依赖注入的
``probe`` / ``drop`` / ``mark`` / ``sleep``，单测不需要模拟器。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from .constants import (
    DROP_CACHES_BURST_BYTES,
    DROP_CACHES_CHECK_UPTIME_SECONDS,
    DROP_CACHES_GIVE_UP_UPTIME_SECONDS,
    DROP_CACHES_MARKER_PROP,
    DROP_CACHES_POLL_SECONDS,
    DROP_CACHES_SETTLED_DELTA_BYTES,
)


@dataclass
class GuestIoSample:
    marked: bool  # 本次开机已经判过 / 清过
    uptime_s: float | None
    read_bytes: int | None  # system_server 的 /proc/<pid>/io read_bytes；读不到为 None


@dataclass
class DropResult:
    action: str  # dropped / no_burst / gave_up / skipped / no_data / failed
    read_bytes: int | None
    reason: str
    cached_before_kb: int | None = None
    cached_after_kb: int | None = None


#: 一次 ``su 0`` 读齐：标记、客体开机秒数、system_server 的 read_bytes。不能有单引号（放在 su -c '' 里）。
PROBE_SCRIPT = (
    f"echo M=$(getprop {DROP_CACHES_MARKER_PROP}); "
    'read -r up x < /proc/uptime; echo "U=$up"; '
    "p=$(pidof system_server); p=${p%% *}; "
    'echo "R=$(grep ^read_bytes /proc/$p/io 2>/dev/null | tr -cd 0-9)"'
)
#: 清缓存与打标记放在同一条命令里，执行前再查一次标记（两个后端进程同时排到也只清一次）。
DROP_SCRIPT = (
    f'if [ "$(getprop {DROP_CACHES_MARKER_PROP})" = 1 ]; then echo SKIP; else '
    'echo "B=$(grep ^Cached: /proc/meminfo | tr -cd 0-9)"; '
    "echo 1 > /proc/sys/vm/drop_caches; "
    f"setprop {DROP_CACHES_MARKER_PROP} 1; "
    'echo "A=$(grep ^Cached: /proc/meminfo | tr -cd 0-9)"; fi'
)
MARK_SCRIPT = f"setprop {DROP_CACHES_MARKER_PROP} 1"


def _fields(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep:
            result[key] = value.strip()
    return result


def _int(raw: str | None) -> int | None:
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def parse_probe(text: str) -> GuestIoSample:
    fields = _fields(text)
    try:
        uptime = float(fields.get("U") or "")
    except ValueError:
        uptime = None
    return GuestIoSample(fields.get("M") == "1", uptime, _int(fields.get("R")))


@dataclass
class DropOutcome:
    status: str  # dropped / skip（别处已经清过）/ failed（命令本身没跑成）
    cached_before_kb: int | None = None
    cached_after_kb: int | None = None
    detail: str = ""


def parse_drop(text: str) -> DropOutcome:
    """清缓存那条命令的输出。既没有 ``SKIP`` 也没有清前的 ``B=`` 行，就是命令本身失败了
    （``su`` 不可用、adb 断了等），不能当成「别处刚清过」。"""
    if "SKIP" in text:
        return DropOutcome("skip")
    fields = _fields(text)
    if "B" not in fields:
        return DropOutcome("failed", detail=text.strip()[-200:])
    return DropOutcome("dropped", _int(fields.get("B")), _int(fields.get("A")))


async def run_drop_caches(
    *,
    probe: Callable[[], Awaitable[GuestIoSample]],
    drop: Callable[[], Awaitable[DropOutcome]],
    mark: Callable[[], Awaitable[object]],
    sleep: Callable[[float], Awaitable[object]],
) -> DropResult:
    """按模块说明的规则判断并（最多）清一次。调用方负责把结果写进日志。"""
    sample = await probe()
    if sample.marked:
        return DropResult("skipped", sample.read_bytes, "本次开机已经判断过")
    if (
        sample.uptime_s is not None
        and sample.uptime_s < DROP_CACHES_CHECK_UPTIME_SECONDS
    ):
        await sleep(DROP_CACHES_CHECK_UPTIME_SECONDS - sample.uptime_s)
        sample = await probe()
        if sample.marked:
            return DropResult("skipped", sample.read_bytes, "本次开机已经判断过")
    if sample.read_bytes is None or sample.uptime_s is None:
        await mark()
        return DropResult("no_data", None, "读不到 system_server 的 read_bytes，不清")
    if sample.read_bytes < DROP_CACHES_BURST_BYTES:
        await mark()
        return DropResult("no_burst", sample.read_bytes, "没有突发读盘，不清")
    previous = sample.read_bytes
    while True:
        if sample.uptime_s >= DROP_CACHES_GIVE_UP_UPTIME_SECONDS:
            await mark()
            return DropResult(
                "gave_up",
                sample.read_bytes,
                f"客体开机 {DROP_CACHES_GIVE_UP_UPTIME_SECONDS:.0f} 秒还没读完，放弃，不清",
            )
        await sleep(DROP_CACHES_POLL_SECONDS)
        sample = await probe()
        if sample.marked:
            return DropResult("skipped", sample.read_bytes, "本次开机已经判断过")
        if sample.read_bytes is None or sample.uptime_s is None:
            await mark()
            return DropResult(
                "no_data", None, "读不到 system_server 的 read_bytes，不清"
            )
        if sample.read_bytes - previous < DROP_CACHES_SETTLED_DELTA_BYTES:
            outcome = await drop()
            if outcome.status == "skip":
                return DropResult("skipped", sample.read_bytes, "别处刚清过")
            if outcome.status == "failed":
                # 尽量打上标记：本次开机不再反复尝试（标记命令本身也可能失败，那就算了）
                with suppress(Exception):
                    await mark()
                return DropResult(
                    "failed",
                    sample.read_bytes,
                    f"突发读盘已读完，但清缓存命令失败（{outcome.detail or '无输出'}），没清",
                )
            return DropResult(
                "dropped",
                sample.read_bytes,
                "突发读盘已读完，清了一次",
                outcome.cached_before_kb,
                outcome.cached_after_kb,
            )
        previous = sample.read_bytes


__all__ = [
    "DROP_SCRIPT",
    "MARK_SCRIPT",
    "PROBE_SCRIPT",
    "DropOutcome",
    "DropResult",
    "GuestIoSample",
    "parse_drop",
    "parse_probe",
    "run_drop_caches",
]
