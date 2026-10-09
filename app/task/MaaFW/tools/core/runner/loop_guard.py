"""MaaFW 任务原地打转检测（实验性，脚本级开关 ``Run.LoopGuard``，默认关）。

任务在短周期里反复执行同一串节点、每轮的识别结果又不变时，判定卡死。真实案例是
M9A「智能均衡刷材料」在主线章节列表划到底后无限右划
（``SwipeRightForStageList → SwipeRightAndFindStage``，每轮约 2 秒，每次卡满 117 分钟）。

判据（2026-09-30 用生产 119 个运行单元标定：正常 0 误报，卡死在循环开始约 10 分钟时检出）：

- 只看 ``Node.Recognition.*`` 与 ``Node.PipelineNode.*``。每条 ``Node.PipelineNode.*`` 结束
  一「步」：(节点名, 动作类型, 自上一步以来的识别集合)。识别 = (节点名, 成败, 识别结果指纹)，
  指纹去掉分数、id、耗时，非 OCR 算法丢掉没过阈值的 ``all`` 候选（渲染噪声）。
- 对周期 p = 1..8 各自维护一段「节点名以周期 p 连续重复」的循环；循环起点之后每满 p 步
  记一轮，一轮的内容指纹是这 p 步识别集合的元组。
- 卡死（stuck）同时满足：连续各轮都有物理动作（点击、滑动、按键……；Custom / DoNothing
  不算，等待型轮询本来就该一直等），没有物理动作的一轮让轮数与时长从头数；≥ 200 轮；持续 ≥ 10 分钟；最近 30 轮的内容指纹不超过 4 种；
  最近 30 轮单轮耗时中位数 ≤ 20 秒；循环里没有项目声明豁免的节点
  （``"attach": {"auto_mas_loop_guard": false}``，见 ``parse_loop_guard_exempt``）。
- 疑似（warn）同样条件、阈值 ≥ 100 轮 / ≥ 5 分钟，每段循环最多一次，只记日志。
- ``Node.Recognition.*`` 缺 ``reco_details`` 键、或 ``Node.PipelineNode.Succeeded`` 缺
  ``action_details`` 键（老 MaaFramework）时返回一次 ``unsupported`` 并永久停用：缺失绝不能
  当成「指纹恒定」，否则每个循环都必中。``Node.PipelineNode.Failed`` 在 5.12+ 上本来就只有
  ``name`` / ``node_id``（生产日志实测），不算缺失，按「无动作」处理。

本模块只用标准库、没有包内导入（标定回放脚本按文件路径直接加载它）；不加锁，调用方负责。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

LOOP_GUARD_ATTACH_KEY = "auto_mas_loop_guard"

RECOGNITION_MESSAGES = frozenset(
    {"Node.Recognition.Succeeded", "Node.Recognition.Failed"}
)
PIPELINE_NODE_MESSAGES = frozenset(
    {"Node.PipelineNode.Succeeded", "Node.PipelineNode.Failed"}
)
# 会改变画面 / 设备状态的动作。Custom 与 DoNothing 不算：等待型轮询（等加载、等结算）
# 本来就会一直转下去，不是卡死。
PHYSICAL_ACTIONS = frozenset(
    {
        "Click",
        "Swipe",
        "LongPress",
        "MultiSwipe",
        "ClickKey",
        "LongPressKey",
        "InputText",
        "Scroll",
        "TouchDown",
        "TouchMove",
        "TouchUp",
        "KeyDown",
        "KeyUp",
        "StartApp",
        "StopApp",
        "Command",
        "Shell",
    }
)

MAX_PERIOD = 8
WINDOW_ITERATIONS = 30
MAX_DISTINCT_FINGERPRINTS = 4
MAX_MEDIAN_ITERATION_SECONDS = 20.0
WARN_MIN_ITERATIONS = 100
WARN_MIN_SECONDS = 300.0
STUCK_MIN_ITERATIONS = 200
STUCK_MIN_SECONDS = 600.0

_DROPPED_RECO_KEYS = frozenset({"score", "reco_id", "elapsed", "cost"})


@dataclass(frozen=True)
class LoopGuardVerdict:
    kind: str  # "warn" / "stuck" / "unsupported"
    cycle: tuple[str, ...]  # 一轮里的节点名序列
    iterations: int
    elapsed_seconds: float  # 从这段循环开始算
    distinct_fingerprints: int  # 最近窗口里的识别指纹种数
    median_iteration_seconds: float
    detail: str = ""  # unsupported 时写缺了什么


def _canonical(value: Any, algorithm: Any = None) -> Any:
    if isinstance(value, dict):
        algorithm = value.get("algorithm", algorithm)
        drop_all = "filtered" in value and algorithm != "OCR"
        result = {}
        for key, item in value.items():
            if key in _DROPPED_RECO_KEYS or (drop_all and key == "all"):
                continue
            result[key] = _canonical(item, algorithm)
        return result
    if isinstance(value, list):
        return [_canonical(item, algorithm) for item in value]
    if isinstance(value, float):
        return round(value, 3)
    return value


def reco_signature(reco_details: Any) -> str | None:
    """识别结果的稳定指纹：去掉分数、id、耗时，非 OCR 丢掉没过阈值的 ``all``。"""

    if reco_details is None:
        reco_details = {}
    if not isinstance(reco_details, dict):
        return None
    text = json.dumps(
        _canonical(reco_details), sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def parse_loop_guard_exempt(node_data: Any) -> bool:
    """节点是否声明了不做原地打转检测：``"attach": {"auto_mas_loop_guard": false}``。

    不放进 ``attach.auto_mas``：信号节点解析遇到未知键会忽略整个节点，而且写了
    ``auto_mas`` 的节点会被 MAS 强开。
    """

    if not isinstance(node_data, dict):
        return False
    attach = node_data.get("attach")
    if not isinstance(attach, dict):
        return False
    return attach.get(LOOP_GUARD_ATTACH_KEY) is False


class _Step:
    __slots__ = ("name", "action", "recos", "time")

    def __init__(self, name: str, action: Any, recos: frozenset, at: float) -> None:
        self.name = name
        self.action = action
        self.recos = recos
        self.time = at


class _PeriodRun:
    """周期 p 上当前这段循环的状态。"""

    __slots__ = (
        "period",
        "start",
        "start_time",
        "iterations",
        "last_end",
        "window",
        "counts",
        "warned",
    )

    def __init__(self, period: int) -> None:
        self.period = period
        self.start = 0
        self.start_time = 0.0
        self.iterations = 0
        self.last_end = 0.0
        self.window: deque[tuple[int, float]] = deque()
        self.counts: dict[int, int] = {}
        self.warned = False

    def restart(self, start: int, start_time: float) -> None:
        self.start = start
        self.restart_count(start_time)

    def restart_count(self, start_time: float) -> None:
        """从 start_time 起重新数轮次与时长，轮的划分（start）不变。"""

        self.start_time = start_time
        self.iterations = 0
        self.last_end = start_time
        self.window.clear()
        self.counts.clear()
        self.warned = False

    def push(self, fingerprint: int, duration: float) -> None:
        self.iterations += 1
        self.window.append((fingerprint, duration))
        self.counts[fingerprint] = self.counts.get(fingerprint, 0) + 1
        if len(self.window) > WINDOW_ITERATIONS:
            old, _ = self.window.popleft()
            left = self.counts[old] - 1
            if left:
                self.counts[old] = left
            else:
                del self.counts[old]

    def median_duration(self) -> float:
        values = sorted(duration for _, duration in self.window)
        mid = len(values) // 2
        if len(values) % 2:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2


class MaaFWLoopGuard:
    """喂 MaaFW 原始通知，判定当前任务是否原地打转。每个任务投递前 ``reset()``。"""

    def __init__(
        self,
        *,
        exempt: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._exempt = exempt
        self._clock = clock
        self._exempt_cache: dict[str, bool] = {}
        self._disabled = False
        self._stuck_reported = False
        self._recos: set[tuple[Any, str, str | None]] = set()
        self._history: deque[_Step] = deque(maxlen=MAX_PERIOD + 1)
        self._step_index = -1
        self._runs = [_PeriodRun(p) for p in range(1, MAX_PERIOD + 1)]

    @property
    def disabled(self) -> bool:
        return self._disabled

    def reset(self) -> None:
        """新任务开始：清掉循环状态与本任务的卡死判定；``unsupported`` 不恢复。"""

        self._stuck_reported = False
        self._recos = set()
        self._history.clear()
        self._step_index = -1
        for run in self._runs:
            run.restart(0, 0.0)

    def feed(
        self, message: str, details: Any, now: float | None = None
    ) -> LoopGuardVerdict | None:
        if self._disabled or self._stuck_reported:
            return None
        if message in RECOGNITION_MESSAGES:
            if not isinstance(details, dict) or "reco_details" not in details:
                return self._unsupported(f"{message} 通知里没有 reco_details")
            self._recos.add(
                (
                    details.get("name"),
                    "S" if message.endswith("Succeeded") else "F",
                    reco_signature(details["reco_details"]),
                )
            )
            return None
        if message not in PIPELINE_NODE_MESSAGES:
            return None
        if not isinstance(details, dict):
            return self._unsupported(f"{message} 通知不是对象")
        # 只看 Succeeded：5.12+ 的 Node.PipelineNode.Failed 本来就只有 name / node_id，
        # 不带 node_details / action_details / reco_details，按「无动作」处理。
        if message.endswith("Succeeded") and "action_details" not in details:
            return self._unsupported(f"{message} 通知里没有 action_details")
        node_details = details.get("node_details")
        name = node_details.get("name") if isinstance(node_details, dict) else None
        if not name:
            name = details.get("name")
        action_details = details.get("action_details")
        action = (
            action_details.get("action") if isinstance(action_details, dict) else None
        )
        recos = frozenset(self._recos)
        self._recos = set()
        at = self._clock() if now is None else now
        return self._on_step(_Step(str(name), action, recos, at))

    def _unsupported(self, detail: str) -> LoopGuardVerdict:
        self._disabled = True
        return LoopGuardVerdict(
            kind="unsupported",
            cycle=(),
            iterations=0,
            elapsed_seconds=0.0,
            distinct_fingerprints=0,
            median_iteration_seconds=0.0,
            detail=detail,
        )

    def _on_step(self, step: _Step) -> LoopGuardVerdict | None:
        history = self._history
        self._step_index += 1
        index = self._step_index
        history.append(step)
        verdict: LoopGuardVerdict | None = None
        for run in self._runs:
            period = run.period
            # history[-1] 是本步，history[-1 - period] 是第 index - period 步
            if not (index >= period and history[-1 - period].name == step.name):
                start = max(0, index - period + 1)
                run.restart(start, history[start - index - 1].time)
            if (index - run.start + 1) % period:
                continue
            chunk = [history[k] for k in range(-period, 0)]
            if not any(item.action in PHYSICAL_ACTIONS for item in chunk):
                # 没有物理动作的一轮（等画面、识别失败、DoNothing）打断计数：要求连续
                # 各轮都有物理动作。否则同名节点空等几百轮后第一次点下去，就会带着
                # 前面的轮数和时长当场被判卡死。
                run.restart_count(step.time)
                continue
            fingerprint = hash(tuple(item.recos for item in chunk))
            run.push(fingerprint, step.time - run.last_end)
            run.last_end = step.time
            if verdict is not None:
                continue
            verdict = self._judge(run, chunk, step.time)
        if verdict is not None and verdict.kind == "stuck":
            self._stuck_reported = True
        return verdict

    def _judge(
        self, run: _PeriodRun, chunk: list[_Step], now: float
    ) -> LoopGuardVerdict | None:
        if run.iterations < WARN_MIN_ITERATIONS:
            return None
        elapsed = now - run.start_time
        if elapsed < WARN_MIN_SECONDS:
            return None
        if len(run.window) < WINDOW_ITERATIONS:
            return None
        distinct = len(run.counts)
        if distinct > MAX_DISTINCT_FINGERPRINTS:
            return None
        stuck = run.iterations >= STUCK_MIN_ITERATIONS and elapsed >= STUCK_MIN_SECONDS
        if not stuck and (run.warned or self._divisor_warned(run.period)):
            return None
        median = run.median_duration()
        if median > MAX_MEDIAN_ITERATION_SECONDS:
            return None
        cycle = tuple(item.name for item in chunk)
        if any(self._is_exempt(name) for name in cycle):
            return None
        run.warned = True
        return LoopGuardVerdict(
            kind="stuck" if stuck else "warn",
            cycle=cycle,
            iterations=run.iterations,
            elapsed_seconds=elapsed,
            distinct_fingerprints=distinct,
            median_iteration_seconds=median,
        )

    def _divisor_warned(self, period: int) -> bool:
        """更短的周期已经为同一段循环提示过：周期 p 的循环同时也是 2p、3p… 的循环。"""

        return any(
            self._runs[q - 1].warned for q in range(1, period) if period % q == 0
        )

    def _is_exempt(self, name: str) -> bool:
        if self._exempt is None:
            return False
        cached = self._exempt_cache.get(name)
        if cached is None:
            try:
                cached = bool(self._exempt(name))
            except Exception:
                cached = False
            self._exempt_cache[name] = cached
        return cached


__all__ = [
    "LOOP_GUARD_ATTACH_KEY",
    "LoopGuardVerdict",
    "MaaFWLoopGuard",
    "PHYSICAL_ACTIONS",
    "parse_loop_guard_exempt",
    "reco_signature",
]
