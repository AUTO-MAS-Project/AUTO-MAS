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

"""游戏启动看门狗：Unity 游戏启动时卡死就强停、重新拉起（崩坏三偶尔卡在 miHoYo 标志页）。

两条规则照搬 aemu-lab ``tools/avdbench/watchdog.py``（判据和阈值都在那边真机上调过，见其 README
「看门狗」）；那边的就绪模板（登录页截图比对）不搬，启动成功以后改成看一段固定时长：

- **启动卡死（规则 d）**：拉起后 T 秒（默认 45）起，画面 S 秒（默认 15）没变、进程空闲，并且
  还没有渲染线程 ``UnityGfxDeviceW``（``no_gfx``），或者它在但几乎没动过（``gfx_stalled``，API 34
  的情形）。进程忙但没有渲染线程，要到 ``hard_s``（120 秒）才算。画面在变 = 有进展（下载 / 校验页）。
  Unity 一开始画画（渲染线程 CPU ≥ 0.5 秒，或渲染线程在时画面变了）这条规则就对这次启动解除。
- **启动后死锁（StallSec）**：启动成功以后，画面静止 ≥ ``stall_s``（60 秒），这段时间进程平均
  ≤ 0.1 核，并且 ``UnityMain`` 或 Java 主线程（tid = pid）连续 3 次停在无超时的 futex 上
  （09-27：GL 初始化后标志页一直挂着、所有线程停住；另一次是「检查资源更新」时主线程卡在锁上、
  系统弹「无响应」）。正常的加载页进程是忙的（标志页阶段约 1 核），Unity 自己的对话框 Unity 循环
  照跑，Java 对话框盖在上面时两个线程都在 epoll——都不会误判。

命中就留证据（各线程 stat / syscall / wchan、游戏的 TCP 连接，写到 ``<根>\\logs``）、强停、重新
拉起，次数有上限。判据都是纯状态机，喂样本就能测，不需要真模拟器。
"""

from __future__ import annotations

import asyncio
import ctypes
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from app.utils import get_logger

logger = get_logger("官方模拟器启动看门狗")

# ---------------------------------------------------------------------------------------------------------
# 判据（纯状态机）


@dataclass
class StartupSample:
    t: float  # 这次拉起以来的秒数（宿主时钟）
    pid: int | None
    gfx: bool | None  # 游戏进程里有没有 UnityGfxDevice* 线程（None = 不知道）
    gfx_ticks: int | None  # 这些线程到目前为止的 CPU tick（None = 不知道 / 没有线程）
    proc_cpu: float | None  # 整个进程自上一样本以来的核数（None = 不知道）
    screen_changed: bool | None  # 画面和参考画面比有没有变（None = 不知道）


class StartupHangDetector:
    """状态：starting / suspect / hang / started / exited / no_process（规则 d，见模块说明）。
    不知道 CPU 不挡判卡死；不知道画面绝不判卡死（没有「画面静止」的证据）。"""

    def __init__(
        self,
        after_s: float = 45,
        static_s: float = 15,
        idle_cores: float = 0.3,
        hard_s: float = 120,
        gfx_ticks_min: int = 50,
    ):
        self.after_s, self.static_s, self.idle_cores, self.hard_s = (
            after_s,
            static_s,
            idle_cores,
            hard_s,
        )
        self.gfx_ticks_min = gfx_ticks_min
        self.reset()

    def reset(self) -> None:
        self.pid: int | None = None
        self.had_pid = False
        self.started = False
        self.last_change = 0.0  # 拉起时刻算最后一次画面变化
        self.gfx_prev = False
        self.cpu: list[tuple[float, float]] = []
        self.kind: str | None = None

    def static_for(self, t: float) -> float:
        return t - self.last_change

    def _idle(self) -> bool:
        vals = [c for t, c in self.cpu if t >= self.last_change]
        return not vals or sum(vals) / len(vals) <= self.idle_cores

    def update(self, s: StartupSample) -> str:
        if not s.pid:
            if self.had_pid:
                self.kind = "exited"
                return "exited"
            if s.t >= self.after_s:
                self.kind = "no_process"
                return "no_process"
            return "starting"
        if s.pid != self.pid:
            if self.pid is not None:  # 游戏自己重启了：从现在起判新进程
                self.last_change, self.started, self.gfx_prev, self.cpu = (
                    s.t,
                    False,
                    False,
                    [],
                )
            self.pid, self.had_pid = s.pid, True
        if self.started:
            return "started"
        if s.gfx and s.gfx_ticks is not None and s.gfx_ticks >= self.gfx_ticks_min:
            self.started = True
        if s.screen_changed:
            self.last_change = s.t
            if self.gfx_prev:  # 画面变化之前渲染线程就在了：是 Unity 画出来的
                self.started = True
        self.gfx_prev = bool(s.gfx)
        if self.started:
            self.kind = None
            return "started"
        if s.proc_cpu is not None:
            self.cpu.append((s.t, s.proc_cpu))
        if s.screen_changed is None:
            return "starting"
        still = self.static_for(s.t) >= self.static_s
        if s.t >= self.after_s and still:
            idle = self._idle()
            if not s.gfx and (idle or s.t >= self.hard_s):
                self.kind = "no_gfx" if idle else "no_gfx_busy"
                return "hang"
            if s.gfx and idle:
                self.kind = "gfx_stalled"
                return "hang"
        return "suspect" if still else "starting"


class ReadyStallDetector:
    """启动成功之后的死锁（StallSec，见模块说明）。画面静止 ≥ stall_s、进程在最近 stall_s 内平均
    ≤ idle_cores、关键线程连续 parked_n 次停在无超时 futex 上，三条同时成立判 ``stalled``。"""

    def __init__(self, stall_s: float = 60, idle_cores: float = 0.1, parked_n: int = 3):
        self.stall_s, self.idle_cores, self.parked_n = stall_s, idle_cores, parked_n
        self.reset(0.0)

    def reset(self, t: float) -> None:
        self.last_change, self.pid, self.cpu, self.parked = t, None, [], 0

    def update(self, s: StartupSample, parked: bool | None) -> str:
        if not s.pid:
            return "exited"
        if s.pid != self.pid:
            if self.pid is not None:  # 游戏自己重启了：从现在起判新进程
                self.last_change, self.cpu, self.parked = s.t, [], 0
            self.pid = s.pid
        self.parked = self.parked + 1 if parked else 0
        if s.screen_changed:
            self.last_change, self.cpu = s.t, []
            return "waiting"
        if s.proc_cpu is not None:
            self.cpu.append((s.t, s.proc_cpu))
        # 只看最近 stall_s 的 CPU：静止段开头渲染线程那一秒的忙，不能让一个早已停住的进程不算空闲
        vals = [c for t, c in self.cpu if t >= s.t - self.stall_s]
        if s.screen_changed is None or not vals or self.parked < self.parked_n:
            return "waiting"
        if (
            s.t - self.last_change >= self.stall_s
            and sum(vals) / len(vals) <= self.idle_cores
        ):
            return "stalled"
        return "waiting"


# ---------------------------------------------------------------------------------------------------------
# 画面


class ScreenDiff:
    """和参考画面比有没有「有意义的变化」。参考画面 = 上一次变化时的画面，所以慢慢淡入也能累积出来。
    ``grab()`` 返回 int16 的 BGR 缩略图（numpy 数组），拿不到画面返回 ``None``。"""

    def __init__(
        self, grab: Callable[[], Any], pix_thr: int = 16, min_frac: float = 0.0005
    ):
        self.grab, self.pix_thr, self.min_frac = grab, pix_thr, min_frac
        self.ref = None
        self.last_frac: float | None = None

    def set_reference(self) -> None:
        self.ref, self.last_frac = self.grab(), None

    def update(self) -> bool | None:
        import numpy as np

        img = self.grab()
        if img is None:
            self.last_frac = None
            return None
        if self.ref is None or img.shape != self.ref.shape:
            known = self.ref is not None
            self.ref, self.last_frac = img, (1.0 if known else None)
            return True if known else None
        frac = float(np.mean(np.max(np.abs(img - self.ref), axis=2) > self.pix_thr))
        self.last_frac = frac
        if frac >= self.min_frac:
            self.ref = img
            return True
        return False


#: 截图共享内存的头：u32 宽、高、fps、帧号，u64 时间戳（微秒），之后是自上而下的 BGRA 行。
_SHM_HEADER = 24


def shm_thumb(console_port: int, step: int = 8) -> Callable[[], Any]:
    """``SHM_videmulator<控制台端口>`` 的缩略图（每 ``step`` 个像素取一个，BGR int16）。每次读都开、关映射。"""

    def grab():
        import numpy as np

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError):
            return None
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.OpenFileMappingW.argtypes = (
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_wchar_p,
        )
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_size_t,
        )
        kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.OpenFileMappingW(0x0004, 0, f"SHM_videmulator{console_port}")
        if not handle:
            return None
        view = kernel32.MapViewOfFile(handle, 0x0004, 0, 0, 0)
        try:
            if not view:
                return None
            width, height = (ctypes.c_uint32 * 2).from_address(view)
            if not width or not height or width > 8192 or height > 8192:
                return None
            buffer = (ctypes.c_ubyte * (width * height * 4)).from_address(
                view + _SHM_HEADER
            )
            pixels = np.frombuffer(buffer, np.uint8).reshape(height, width, 4)
            return pixels[::step, ::step, :3].astype(np.int16)
        finally:
            if view:
                kernel32.UnmapViewOfFile(view)
            kernel32.CloseHandle(handle)

    return grab


# ---------------------------------------------------------------------------------------------------------
# 客体侧采样

#: 每个样本一次 ``su 0`` shell（应用的 ``/proc/<tid>/syscall`` 要 root）。占位符 @PKG@（不用花括号：
#: 脚本里全是 shell 的 ${...}）。不能有单引号：脚本放在 su 0 sh -c '...' 里。
STARTUP_PROBE = (
    'p=$(pidof @PKG@); p=${p%% *}; read -r up x < /proc/uptime; echo "SU $up ${p:-0}"; '
    'if [ -n "$p" ]; then s=; read -r s < /proc/$p/stat; echo "SP $s"; '
    'for t in /proc/$p/task/*; do s=; c=; read -r s < $t/stat; read -r c < $t/syscall; echo "ST $s @@ $c"; done; fi'
)
EVIDENCE_PROBE = (
    'p=@PID@; echo "uptime $(cat /proc/uptime) pid $p"; for t in /proc/$p/task/*; do s=; c=; '
    'read -r s < $t/stat; read -r c < $t/syscall; w=$(cat $t/wchan); echo "$s @@ sc=$c @@ wchan=$w"; done; '
    # 网络侧（09-27）：游戏的 TCP 连接（st 01 已建立、02 正在连、08 close-wait）和计数器，
    # 用来分清「网络错误」页和本地问题
    'u=$(awk "/^Uid:/{print \\$2}" /proc/$p/status); echo "== tcp uid $u"; '
    'awk -v u=$u "FNR>1 && \\$8==u" /proc/net/tcp /proc/net/tcp6; grep "^Tcp:" /proc/net/snmp; '
    'ip route get 1.1.1.1 | head -1; echo "dns $(getprop net.dns1)"'
)


def su_command(script: str) -> str:
    if "'" in script:
        raise ValueError("script must not contain single quotes")
    return f"su 0 sh -c '{script}'"


@dataclass
class ThreadInfo:
    tid: int
    comm: str
    state: str
    ticks: int
    syscall: str


def _split_stat(line: str) -> tuple[int, str, list[str]] | None:
    """``pid (comm) S ...`` → (pid, comm, comm 之后的字段)；comm 里可以有空格和括号。"""
    lp, rp = line.find("("), line.rfind(")")
    if lp < 0 or rp < lp:
        return None
    try:
        return int(line[:lp].split()[-1]), line[lp + 1 : rp], line[rp + 1 :].split()
    except (ValueError, IndexError):
        return None


@dataclass
class StartupCounters:
    uptime: float
    pid: int | None
    proc_ticks: int | None
    threads: list[ThreadInfo]


def parse_startup(text: str) -> StartupCounters:
    up, pid, proc, threads = None, None, None, []
    for ln in text.splitlines():
        if ln.startswith("SU "):
            parts = ln.split()
            up, pid = (
                float(parts[1]),
                (int(parts[2]) or None) if len(parts) > 2 else None,
            )
        elif ln.startswith("SP "):
            st = _split_stat(ln[3:])
            if st and len(st[2]) > 12:
                proc = int(st[2][11]) + int(st[2][12])
        elif ln.startswith("ST "):
            stat, _, sc = ln[3:].partition(" @@ ")
            st = _split_stat(stat)
            if st and len(st[2]) > 12:
                threads.append(
                    ThreadInfo(
                        st[0],
                        st[1],
                        st[2][0],
                        int(st[2][11]) + int(st[2][12]),
                        sc.strip(),
                    )
                )
    if up is None:
        raise ValueError(f"no startup counters in probe output: {text[:200]!r}")
    return StartupCounters(up, pid, proc, threads)


def futex_untimed(syscall: str) -> bool:
    """``/proc/<tid>/syscall`` 为 ``202 uaddr op val timeout ...`` 且 timeout 为 NULL（x86_64 futex，无超时）。"""
    parts = syscall.split()
    return len(parts) > 4 and parts[0] == "202" and parts[4] in ("0x0", "0")


def _thread_summary(th: ThreadInfo) -> dict[str, Any]:
    return {
        "tid": th.tid,
        "state": th.state,
        "ticks": th.ticks,
        "syscall": " ".join(th.syscall.split()[:5]),
        "futex_untimed": futex_untimed(th.syscall),
    }


class StartupSampler:
    """一次 ``sample()`` = 一次客体探测 + 一次画面比较。``shell`` 是异步的「跑一条 adb shell 命令」。"""

    def __init__(
        self,
        shell: Callable[[str], Awaitable[str]],
        package: str,
        screen: ScreenDiff | None = None,
        clk_tck: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.shell, self.package, self.screen, self.clk_tck, self.clock = (
            shell,
            package,
            screen,
            clk_tck,
            clock,
        )
        self.t0 = clock()
        self.prev: StartupCounters | None = None
        self.last: StartupCounters | None = None

    def begin(self) -> None:
        """拉起前一刻调：时间零点 + 参考画面（例如桌面）。"""
        self.prev = self.last = None
        if self.screen:
            self.screen.set_reference()
        self.t0 = self.clock()

    async def sample(self) -> StartupSample:
        cur = parse_startup(
            await self.shell(su_command(STARTUP_PROBE.replace("@PKG@", self.package)))
        )
        changed = self.screen.update() if self.screen else None
        prev, self.prev, self.last = self.prev, cur, cur
        gfx_threads = [th for th in cur.threads if th.comm.startswith("UnityGfxDevice")]
        cpu = None
        if (
            prev
            and cur.pid
            and cur.pid == prev.pid
            and cur.uptime > prev.uptime
            and None not in (cur.proc_ticks, prev.proc_ticks)
            and cur.proc_ticks >= prev.proc_ticks
        ):
            cpu = (
                (cur.proc_ticks - prev.proc_ticks)
                / self.clk_tck
                / (cur.uptime - prev.uptime)
            )
        gfx = None if not cur.pid else bool(gfx_threads)
        return StartupSample(
            round(self.clock() - self.t0, 2),
            cur.pid,
            gfx,
            sum(th.ticks for th in gfx_threads) if gfx_threads else None,
            cpu,
            changed,
        )

    def main_thread(self) -> dict[str, Any] | None:
        """应用的 Java 主线程（tid = pid）——卡在这里 = 应用无响应。"""
        if not self.last:
            return None
        ths = [th for th in self.last.threads if th.tid == self.last.pid]
        return _thread_summary(ths[0]) if ths else None

    def unity_main(self) -> dict[str, Any] | None:
        """Unity 主线程 = 名叫 UnityMain 的线程里 tid 最小的那个（IL2CPP 线程会重名）。"""
        ths = [
            th
            for th in (self.last.threads if self.last else [])
            if th.comm == "UnityMain"
        ]
        return _thread_summary(min(ths, key=lambda x: x.tid)) if ths else None


# ---------------------------------------------------------------------------------------------------------
# 守护拉起


class StartupGuard:
    """强停 → 拉起 → 每 ``interval`` 秒采样。

    启动阶段（规则 d）：卡死 / 进程没了 / ``start_timeout_s`` 内没启动成功 → 留证据，下一次（强停 + 拉起）。
    启动成功后看到拉起后第 ``watch_s`` 秒（StallSec）：死锁 → 留证据，下一次。这一段里游戏退出了不重开
    ——那多半是脚本自己关的，看门狗不跟脚本抢。最多 ``retries`` 次重开（= ``retries + 1`` 次拉起）。

    ``started`` 在第一次启动成功时置位：调用方等到它就可以把游戏交给脚本，守护继续在后台看。
    """

    def __init__(
        self,
        sampler: StartupSampler,
        detector: StartupHangDetector,
        *,
        launch: Callable[[], Awaitable[object]],
        stop: Callable[[], Awaitable[object]],
        retries: int = 5,
        interval: float = 3.0,
        start_timeout_s: float = 180,
        stall: ReadyStallDetector | None = None,
        watch_s: float = 300,
        evidence: Callable[[str, int, int | None], Awaitable[object]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        log: Callable[[dict[str, Any]], None] = lambda record: None,
        settle_s: float = 1.0,
    ):
        self.sampler, self.detector, self.launch, self.stop = (
            sampler,
            detector,
            launch,
            stop,
        )
        self.retries, self.interval, self.start_timeout_s = (
            retries,
            interval,
            start_timeout_s,
        )
        self.stall, self.watch_s, self.evidence = stall, watch_s, evidence
        self.clock, self.sleep, self.log, self.settle_s = clock, sleep, log, settle_s
        self.started = asyncio.Event()

    async def _evidence(
        self, res: dict[str, Any], why: str, n: int, pid: int | None
    ) -> None:
        if self.evidence is None:
            return
        try:
            res["evidence"] = await self.evidence(why, n, pid)
        except Exception as e:  # noqa: BLE001 - 证据尽力而为，绝不挡重开
            res["evidence_error"] = str(e)[:200]

    async def _wait(self, t_loop: float) -> None:
        await self.sleep(max(0.0, self.interval - (self.clock() - t_loop)))

    async def _attempt(self, n: int) -> dict[str, Any]:
        await self.stop()
        if self.settle_s:
            await self.sleep(self.settle_s)
        self.detector.reset()
        self.sampler.begin()
        t_launch = self.clock()
        await self.launch()
        res: dict[str, Any] = {"attempt": n}
        while True:
            t_loop = self.clock()
            s = await self.sampler.sample()
            st = self.detector.update(s)
            self.log(
                {
                    "attempt": n,
                    "phase": "start",
                    **asdict(s),
                    "state": st,
                    "kind": self.detector.kind,
                    "unity_main": self.sampler.unity_main(),
                }
            )
            if st == "started":
                res.update(result="started", t_started=s.t)
                self.started.set()
                break
            if st in ("hang", "exited", "no_process") or s.t >= self.start_timeout_s:
                why = st if st in ("hang", "exited", "no_process") else "timeout"
                res.update(
                    result=why,
                    kind=self.detector.kind,
                    t_detect=s.t,
                    gfx=s.gfx,
                    unity_main=self.sampler.unity_main(),
                )
                await self._evidence(res, why, n, s.pid)
                res["seconds"] = round(self.clock() - t_launch, 1)
                return res
            await self._wait(t_loop)
        if self.stall is None:
            res["seconds"] = round(self.clock() - t_launch, 1)
            return res
        self.stall.reset(s.t)
        while True:
            await self._wait(t_loop)
            t_loop = self.clock()
            s2 = await self.sampler.sample()
            um, mt = self.sampler.unity_main(), self.sampler.main_thread()
            parked = bool(
                (um and um.get("futex_untimed")) or (mt and mt.get("futex_untimed"))
            )
            state = self.stall.update(s2, parked)
            self.log(
                {
                    "attempt": n,
                    "phase": "watch",
                    **asdict(s2),
                    "stall": state,
                    "unity_main": um,
                    "main_thread": mt,
                }
            )
            if state == "stalled":
                res.update(
                    result="hang",
                    kind="ready_stall",
                    t_detect=s2.t,
                    unity_main=um,
                    main_thread=mt,
                )
                await self._evidence(res, "hang", n, s2.pid)
                break
            if state == "exited":
                res.update(watch="exited", t_exit=s2.t)
                break
            if s2.t >= self.watch_s:
                res.update(watch="done")
                break
        res["seconds"] = round(self.clock() - t_launch, 1)
        return res

    async def run(self) -> dict[str, Any]:
        t0 = self.clock()
        attempts: list[dict[str, Any]] = []
        for n in range(1, self.retries + 2):
            attempt = await self._attempt(n)
            attempts.append(attempt)
            if attempt["result"] == "started":
                break
        last = attempts[-1]["result"]
        return {
            "result": "started" if last == "started" else "gave_up",
            "attempts": attempts,
            "relaunches": len(attempts) - 1,
            "hangs": sum(1 for a in attempts if a["result"] == "hang"),
            "seconds": round(self.clock() - t0, 1),
        }


__all__ = [
    "EVIDENCE_PROBE",
    "STARTUP_PROBE",
    "ReadyStallDetector",
    "ScreenDiff",
    "StartupGuard",
    "StartupHangDetector",
    "StartupSample",
    "StartupSampler",
    "futex_untimed",
    "parse_startup",
    "shm_thumb",
    "su_command",
]
