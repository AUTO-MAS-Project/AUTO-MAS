"""宿主侧的结构化运行记录：把 worker 推来的事件（``core/runner/run_events.py``）按尝试归并。

一次尝试一份记录，与该尝试的 history 记录一一对应（键是那份 ``LogRecord`` 的 id），存进
history 的 ``data[RUN_RECORD_HISTORY_KEY]``（snapshot）。读的一方用 :func:`read_run_record`：
没有这个键的旧历史、或版本 / 形状不认识的，一律当作没有记录。

记录只用来回看与推送摘要，不参与重试判断：重试仍按 ``MaaFWRunResult`` 的现有字段走。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.models.task import UserTaskProgress
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_INIT_FAILED,
    CATEGORY_LOOP_GUARD,
    CATEGORY_RUN_TIMEOUT,
    CATEGORY_TASK_FAILED,
    CATEGORY_TASK_TIMEOUT,
    CATEGORY_USER_STOPPED,
    OUTCOME_FAILED,
    OUTCOME_LOOP,
    OUTCOME_SKIPPED,
    OUTCOME_STOPPED,
    OUTCOME_SUCCEEDED,
    OUTCOME_TIMEOUT,
    MaaFWStageEvent,
    MaaFWTaskEndEvent,
    MaaFWTaskOutcome,
    MaaFWTaskStartEvent,
    parse_run_record_event,
)
from app.utils import get_logger

logger = get_logger("MaaFW 运行记录")

# history 记录 data 里的键；值是 {"kind": "snapshot", "value": <MaaFWAttemptRecord>}
RUN_RECORD_HISTORY_KEY = "maafw_run_record"
RUN_RECORD_VERSION = 1

MaaFWAttemptOutcome = Literal["success", "failed", "stopped", "skipped"]

# 推送里单列的两类：每类一行，后面列「哪一次尝试 · 哪个任务」
INCIDENT_LINE_PREFIXES = {
    CATEGORY_LOOP_GUARD: "原地打转",
    CATEGORY_TASK_TIMEOUT: "单任务超时",
}


class MaaFWStageRecord(BaseModel):
    stage: str
    startedAt: float
    endedAt: float | None = None
    # None：开始了没收到结束（worker 被强杀、用户停止）
    ok: bool | None = None


class MaaFWTaskRecord(BaseModel):
    index: int
    name: str
    label: str | None = None
    startedAt: float | None = None
    endedAt: float | None = None
    outcome: MaaFWTaskOutcome = OUTCOME_SKIPPED
    category: str | None = None
    counted: bool = True


class MaaFWAttemptRecord(BaseModel):
    version: int = RUN_RECORD_VERSION
    attempt: int
    title: str
    startedAt: float
    endedAt: float | None = None
    outcome: MaaFWAttemptOutcome | None = None
    category: str | None = None
    # 没走到任务就失败时，失败在哪一步（run_events 的 STAGE_*）
    failedStage: str | None = None
    signal: str | None = None
    # 本次计划之前已被重试跳过的任务数（前面的尝试完成过的），调度台进度据此补齐总数
    retrySkipped: int = 0
    stages: list[MaaFWStageRecord] = Field(default_factory=list)
    tasks: list[MaaFWTaskRecord] = Field(default_factory=list)


@dataclass(frozen=True)
class MaaFWRunIncident:
    category: str
    attempt_title: str
    task_label: str


def _round(value: float) -> float:
    return round(value, 3)


class MaaFWRunRecorder:
    """一个用户本次运行的全部尝试。宿主在事件循环线程里调用，不加锁。"""

    def __init__(self) -> None:
        self._attempts: dict[int, MaaFWAttemptRecord] = {}
        self._current: int | None = None

    @property
    def current(self) -> MaaFWAttemptRecord | None:
        if self._current is None:
            return None
        return self._attempts.get(self._current)

    def attempts(self) -> list[MaaFWAttemptRecord]:
        return list(self._attempts.values())

    def attempt_items(self) -> list[tuple[int, MaaFWAttemptRecord]]:
        """各次尝试连同它的键（该尝试日志的 id），按开始先后。"""

        return list(self._attempts.items())

    def begin_attempt(
        self,
        key: int,
        *,
        attempt: int,
        title: str,
        planned: Iterable[tuple[str, str | None]],
        retry_skipped: int = 0,
        now: float | None = None,
    ) -> None:
        """开始一次尝试；``planned`` 是本次计划的任务（名字, 标签），先都记成没轮到。"""

        self._attempts[key] = MaaFWAttemptRecord(
            attempt=attempt,
            title=title,
            startedAt=_round(time.time() if now is None else now),
            retrySkipped=max(0, retry_skipped),
            tasks=[
                MaaFWTaskRecord(index=index, name=name, label=label)
                for index, (name, label) in enumerate(planned)
            ],
        )
        self._current = key

    @contextmanager
    def stage(self, stage: str, *, enabled: bool = True) -> Iterator[None]:
        """宿主自己的一个阶段：正常走完记成功，异常（含取消）穿出记失败。

        记录本身是旁路：起止记账出错只写一行 WARNING，被包住的那段照常执行、
        它自己的异常照常穿出。"""

        if not enabled:
            yield
            return
        self._stage_mark(stage, None)
        ok = False
        try:
            yield
            ok = True
        finally:
            self._stage_mark(stage, ok)

    def _stage_mark(self, stage: str, ok: bool | None) -> None:
        try:
            if ok is None:
                self.stage_begin(stage)
            else:
                self.stage_end(stage, ok=ok)
        except Exception as exc:  # noqa: BLE001 - 旁路不能拖垮运行
            logger.opt(exception=True).warning(
                f"MaaFW 运行记录出错（不影响运行）: 阶段 {stage} "
                f"{'开始' if ok is None else '结束'}记账失败: {exc}"
            )

    def stage_begin(self, stage: str, *, now: float | None = None) -> None:
        record = self.current
        if record is None or record.endedAt is not None:
            return
        record.stages.append(
            MaaFWStageRecord(
                stage=stage, startedAt=_round(time.time() if now is None else now)
            )
        )

    def stage_end(self, stage: str, *, ok: bool, now: float | None = None) -> None:
        record = self.current
        if record is None or record.endedAt is not None:
            return
        for item in reversed(record.stages):
            if item.stage == stage and item.endedAt is None:
                item.endedAt = _round(time.time() if now is None else now)
                item.ok = ok
                return

    def apply(self, data: Any) -> UserTaskProgress | None:
        """收一条 worker 事件；任务开始时返回调度台要显示的进度（「3/12 · 当前任务」），
        其余返回 None。认不出的事件丢掉。"""

        record = self.current
        event = parse_run_record_event(data)
        if record is None or event is None or record.endedAt is not None:
            return None
        if isinstance(event, MaaFWStageEvent):
            if event.state == "begin":
                self.stage_begin(event.stage, now=event.at)
            else:
                self.stage_end(event.stage, ok=bool(event.ok), now=event.at)
            return None
        task = self._task(record, event.index, event.name)
        if isinstance(event, MaaFWTaskStartEvent):
            if event.label and not task.label:
                task.label = event.label
            task.startedAt = _round(event.at)
            return UserTaskProgress(
                current=record.retrySkipped + event.index + 1,
                total=record.retrySkipped + max(event.total, len(record.tasks)),
                task=task.label or task.name,
            )
        if isinstance(event, MaaFWTaskEndEvent):
            task.endedAt = _round(event.at)
            task.outcome = event.outcome
            task.category = event.category
            task.counted = event.counted
        return None

    @staticmethod
    def _task(record: MaaFWAttemptRecord, index: int, name: str) -> MaaFWTaskRecord:
        if 0 <= index < len(record.tasks) and record.tasks[index].name == name:
            return record.tasks[index]
        # 计划对不上（不该发生）：按 worker 说的补一条，不丢事件；同一个任务的 end 找回它的 start
        for task in record.tasks:
            if task.index == index and task.name == name:
                return task
        task = MaaFWTaskRecord(index=index, name=name)
        record.tasks.append(task)
        return task

    def finish_attempt(
        self,
        *,
        outcome: MaaFWAttemptOutcome,
        category: str | None = None,
        signal: str | None = None,
        now: float | None = None,
    ) -> MaaFWAttemptRecord | None:
        """当前尝试收尾：开始了没收到结束的任务按 ``outcome`` 补一个结局。只收尾一次。"""

        record = self.current
        if record is None or record.endedAt is not None:
            return None
        ended_at = _round(time.time() if now is None else now)
        record.endedAt = ended_at
        record.outcome = outcome
        record.signal = signal
        for task in record.tasks:
            if task.startedAt is not None and task.endedAt is None:
                # worker 被强杀 / 用户停止时最后那个任务收不到 task_end
                task.endedAt = ended_at
                if outcome == "stopped":
                    task.outcome = OUTCOME_STOPPED
                    task.category = CATEGORY_USER_STOPPED
                elif category == CATEGORY_RUN_TIMEOUT:
                    # worker 到点没能自己停下、被宿主强杀
                    task.outcome = OUTCOME_TIMEOUT
                    task.category = category
                else:
                    task.outcome = OUTCOME_FAILED
                    task.category = category
        if outcome != "success":
            record.failedStage = next(
                (
                    stage.stage
                    for stage in reversed(record.stages)
                    if stage.ok is not True
                ),
                None,
            )
        record.category = category
        if outcome == "failed" and category is None:
            record.category = self._task_failure_category(record)
        return record

    @staticmethod
    def _task_failure_category(record: MaaFWAttemptRecord) -> str:
        """尝试失败、宿主没给类别时：第一个计入失败的任务的类别；任务都没开始就是初始化失败。"""

        started = [task for task in record.tasks if task.startedAt is not None]
        if not started:
            return CATEGORY_INIT_FAILED
        for task in started:
            if task.counted and task.outcome not in (
                OUTCOME_SUCCEEDED,
                OUTCOME_SKIPPED,
            ):
                return task.category or CATEGORY_TASK_FAILED
        return CATEGORY_TASK_FAILED

    def history_value(self, key: int) -> dict[str, Any] | None:
        record = self._attempts.get(key)
        if record is None:
            return None
        return record.model_dump(mode="json")

    def incidents(self) -> list[MaaFWRunIncident]:
        """各次尝试里被原地打转检测或单任务时限停下的任务，按发生先后。"""

        found: list[MaaFWRunIncident] = []
        for record in self._attempts.values():
            for task in record.tasks:
                # 看结局不看类别：收尾任务停下后发现游戏没起来时类别会被细化成
                # game_launch_failed，停下它的仍是这两种之一。整次运行的时限另有一句话，
                # 不在这里重复。
                if task.outcome == OUTCOME_LOOP:
                    category = CATEGORY_LOOP_GUARD
                elif (
                    task.outcome == OUTCOME_TIMEOUT
                    and task.category != CATEGORY_RUN_TIMEOUT
                ):
                    category = CATEGORY_TASK_TIMEOUT
                else:
                    continue
                found.append(
                    MaaFWRunIncident(
                        category=category,
                        attempt_title=record.title,
                        task_label=task.label or task.name,
                    )
                )
        return found


def format_incident_lines(incidents: Iterable[MaaFWRunIncident]) -> str:
    """推送里单列的行：每类一行「原地打转: 第 1 次尝试 · 刷材料」，多次用顿号接。"""

    grouped: dict[str, list[str]] = {}
    for incident in incidents:
        grouped.setdefault(incident.category, []).append(
            f"{incident.attempt_title} · {incident.task_label}"
        )
    return "\n".join(
        f"{prefix}: " + "、".join(grouped[category])
        for category, prefix in INCIDENT_LINE_PREFIXES.items()
        if grouped.get(category)
    )


def read_run_record(data: Mapping[str, Any] | None) -> MaaFWAttemptRecord | None:
    """从 history 记录的 ``data`` 里取运行记录；旧历史没有这个键、版本不认识都返回 None。

    ``data`` 可以是 ``HistoryRecord.data``（值为统计模型）或它的 JSON 形式（值为 dict）。
    """

    if not data:
        return None
    entry = data.get(RUN_RECORD_HISTORY_KEY)
    if entry is None:
        return None
    value = getattr(entry, "value", None)
    if value is None and isinstance(entry, Mapping):
        if entry.get("kind") != "snapshot":
            return None
        value = entry.get("value")
    if not isinstance(value, Mapping) or value.get("version") != RUN_RECORD_VERSION:
        return None
    try:
        return MaaFWAttemptRecord.model_validate(value)
    except ValidationError:
        return None


__all__ = [
    "INCIDENT_LINE_PREFIXES",
    "RUN_RECORD_HISTORY_KEY",
    "RUN_RECORD_VERSION",
    "MaaFWAttemptRecord",
    "MaaFWRunIncident",
    "MaaFWRunRecorder",
    "MaaFWStageRecord",
    "MaaFWTaskRecord",
    "format_incident_lines",
    "read_run_record",
]
