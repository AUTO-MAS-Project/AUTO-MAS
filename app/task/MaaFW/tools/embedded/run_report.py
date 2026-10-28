"""推送里给人看的 MFW 运行结果：用户级「统计报告」的任务时间线与结果、脚本级「代理结果」的用户行。

只用结构化运行记录（``run_record.py``）和 runner 给的 ``userMessage``。``errorMessage`` 不进
推送：节点链、框架失败事件、原生栈这些排障细节照旧完整留在任务日志、app.log 与 worker 日志里。

口径：
- 时间线只列最后一次尝试，一个任务一行 ``HH:MM - <图标> <状态>：<任务>（原因）``；前面尝试里已经
  完成、这次被重试跳过的任务按当时完成的时刻并进来，前面尝试的失败一律不列。
- 失败原因有 ``userMessage`` 用它（去掉节点名、框架事件这类片段），没有就按失败类别给一句固定的话。
- 最后一次一个任务都没开始：不列时间线，只写一句「MaaFW 运行失败：<原因>」。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_AGENT_EXITED,
    CATEGORY_ENVIRONMENT,
    CATEGORY_GAME_LAUNCH_FAILED,
    CATEGORY_GAME_UPDATE_REQUIRED,
    CATEGORY_HOST_ERROR,
    CATEGORY_INIT_FAILED,
    CATEGORY_LOOP_GUARD,
    CATEGORY_PRETASK_FAILED,
    CATEGORY_RESOURCE_FAILURE,
    CATEGORY_RUN_TIMEOUT,
    CATEGORY_SCRIPT_STOPPED,
    CATEGORY_SIGNAL,
    CATEGORY_TASK_FAILED,
    CATEGORY_TASK_TIMEOUT,
    CATEGORY_USER_STOPPED,
    OUTCOME_FAILED,
    OUTCOME_LOOP,
    OUTCOME_SKIPPED,
    OUTCOME_STOPPED,
    OUTCOME_SUCCEEDED,
    OUTCOME_TIMEOUT,
    STAGE_AGENT,
    STAGE_CLIENT,
    STAGE_CONTROLLER,
    STAGE_DEVICE,
    STAGE_ENVIRONMENT,
    STAGE_PRETASK,
    STAGE_RESOURCE,
    STAGE_RUNTIME,
    STAGE_START_GATE,
)

from .run_record import MaaFWAttemptRecord, MaaFWTaskRecord
from .signal_notice import CLIENT_UPDATE_REQUIRED, SERVER_MAINTENANCE

# 任务结局 → (图标, 状态)
OUTCOME_MARKS = {
    OUTCOME_SUCCEEDED: ("✅", "成功"),
    OUTCOME_FAILED: ("❌", "失败"),
    OUTCOME_TIMEOUT: ("⏱", "超时"),
    OUTCOME_LOOP: ("🔁", "原地打转"),
    OUTCOME_STOPPED: ("⏹", "停止"),
    OUTCOME_SKIPPED: ("⏭", "跳过"),
}

# 没有 userMessage 时各失败类别的一句话
CATEGORY_REASONS = {
    CATEGORY_TASK_FAILED: "任务没有完成",
    CATEGORY_TASK_TIMEOUT: "单任务超时",
    CATEGORY_RUN_TIMEOUT: "整次运行超时",
    CATEGORY_LOOP_GUARD: "原地打转",
    CATEGORY_SCRIPT_STOPPED: "被项目脚本停下",
    CATEGORY_USER_STOPPED: "手动停止",
    CATEGORY_GAME_LAUNCH_FAILED: "游戏未能启动",
    CATEGORY_AGENT_EXITED: "Agent 进程已退出",
    CATEGORY_RESOURCE_FAILURE: "资源加载失败",
    CATEGORY_ENVIRONMENT: "运行环境不可用",
    CATEGORY_PRETASK_FAILED: "运行前设置失败",
    CATEGORY_GAME_UPDATE_REQUIRED: "需要更新游戏客户端",
    CATEGORY_HOST_ERROR: "MAS 运行出错",
    CATEGORY_INIT_FAILED: "初始化失败",
}

# 一个任务都没开始就失败、类别又只说得出「初始化失败」时，按失败在哪一步说
STAGE_REASONS = {
    STAGE_RUNTIME: "MaaFramework 没能加载",
    STAGE_DEVICE: "设备（ADB）没有就绪",
    STAGE_RESOURCE: "资源加载失败",
    STAGE_CONTROLLER: "没能连上游戏 / 模拟器",
    STAGE_AGENT: "Agent 没能启动",
    STAGE_START_GATE: "游戏启动后没等到可操作的画面",
    STAGE_PRETASK: "运行前设置失败",
    STAGE_CLIENT: "游戏未能启动",
    STAGE_ENVIRONMENT: "运行环境准备失败",
}

SIGNAL_REASONS = {
    SERVER_MAINTENANCE: "游戏停服维护中",
    CLIENT_UPDATE_REQUIRED: "需要更新游戏客户端",
}

# 这几个类别只说明「失败了 / 超时了 / 打转了」，状态本身已经说了，任务后面不再加括号
_OUTCOME_DEFAULT_CATEGORY = {
    OUTCOME_FAILED: CATEGORY_TASK_FAILED,
    OUTCOME_TIMEOUT: CATEGORY_TASK_TIMEOUT,
    OUTCOME_LOOP: CATEGORY_LOOP_GUARD,
}
# 计入失败与否都让本轮失败的类别（收尾任务被放过时也一样）
_FATAL_CATEGORIES = frozenset(
    {CATEGORY_GAME_LAUNCH_FAILED, CATEGORY_AGENT_EXITED, CATEGORY_RUN_TIMEOUT}
)
# 只给排障看的片段：节点名 / 节点链、框架事件、原生栈、日志文件指引
_DIAGNOSTIC_MARKERS = (
    "停在",
    "入口 ",
    "未能走完",
    "画面文字",
    "框架失败事件",
    "Node.",
    "Tasker.",
    "→",
    "Traceback",
    ".log",
    "task_id",
    "MaaTaskerPostStop",
    "MaaFramework 未给出失败原因",
)
# 时间线里后面的任务行、单列的打转 / 超时行已经说了的话
_REDUNDANT_MARKERS = ("本轮剩余任务已跳过", "本轮已结束", "此前另有", "另有 ")
_REDUNDANT_SEGMENTS = frozenset({"任务失败", "任务执行失败"})
_MULTI_FAILURE_RE = re.compile(r"^\d+ 个任务失败：")
_CJK_RE = re.compile(r"[一-鿿]")
_OPEN, _CLOSE = "（", "）"


@dataclass(frozen=True)
class MaaFWAttemptReport:
    """一次尝试：运行记录，加上 worker 回报的 userMessage 与失败任务名（没有就是 None）。"""

    record: MaaFWAttemptRecord
    user_message: str | None = None
    failed_task: str | None = None


def _split_top_level(text: str) -> list[str]:
    """按顶层的「；」「，」切开，全角括号里的不切。"""

    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == _OPEN:
            depth += 1
        elif char == _CLOSE and depth:
            depth -= 1
        if depth == 0 and char in "；，":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _drop_diagnostic_groups(text: str) -> str:
    """去掉内容带排障片段的全角括号（如「原地打转（A → B 已循环 200 轮）」里的节点循环）。"""

    result: list[str] = []
    stack: list[int] = []
    for char in text:
        if char == _OPEN:
            stack.append(len(result))
        result.append(char)
        if char == _CLOSE and stack:
            start = stack.pop()
            inner = "".join(result[start + 1 : -1])
            if any(marker in inner for marker in _DIAGNOSTIC_MARKERS):
                del result[start:]
    return "".join(result)


def human_reason(text: str | None) -> str:
    """把 runner 的 userMessage（或其中一段）收成只给人看的一句话；什么都不剩返回空串。"""

    first = next(
        (line.strip() for line in str(text or "").splitlines() if line.strip()), ""
    )
    if not first:
        return ""
    kept: list[str] = []
    for segment in _split_top_level(_drop_diagnostic_groups(first)):
        segment = segment.strip().rstrip("：:").strip()
        if not segment or segment in _REDUNDANT_SEGMENTS:
            continue
        if any(marker in segment for marker in _DIAGNOSTIC_MARKERS):
            continue
        if any(marker in segment for marker in _REDUNDANT_MARKERS):
            continue
        # 没有一个汉字的多半是异常原文（英文报错、路径、错误码）
        if not _CJK_RE.search(segment):
            continue
        if segment not in kept:
            kept.append(segment)
    return "，".join(kept)


def _balanced_after(text: str, start: int) -> str:
    """``text[start]`` 是「（」：取到与它配对的「）」为止的内容。"""

    depth = 0
    for index in range(start, len(text)):
        if text[index] == _OPEN:
            depth += 1
        elif text[index] == _CLOSE:
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return text[start + 1 :]


def _message_part_for(message: str, label: str) -> str | None:
    """userMessage 里说这个任务的那一段：``<任务>：…`` 或多任务失败里的 ``<任务>（…）``。"""

    first = next((line.strip() for line in message.splitlines() if line.strip()), "")
    if not label or not first:
        return None
    if first.startswith(f"{label}："):
        return first[len(label) + 1 :]
    for prefix in ("：", "；"):
        position = first.find(f"{prefix}{label}{_OPEN}")
        if position >= 0:
            return _balanced_after(first, position + len(prefix) + len(label))
    return None


def _task_label(task: MaaFWTaskRecord) -> str:
    return task.label or task.name


def task_reason(task: MaaFWTaskRecord, attempt: MaaFWAttemptReport) -> str:
    """时间线里任务后面括号里的那句话；状态已经说清楚了就是空串（不加括号）。"""

    outcome = task.outcome
    if outcome in (OUTCOME_SUCCEEDED, OUTCOME_SKIPPED):
        return ""
    category = task.category
    if category == CATEGORY_SIGNAL:
        return SIGNAL_REASONS.get(str(attempt.record.signal or ""), "")
    if category and category != _OUTCOME_DEFAULT_CATEGORY.get(outcome):
        reason = CATEGORY_REASONS.get(category, "")
        if reason:
            return reason
    if outcome != OUTCOME_FAILED or not attempt.user_message:
        return ""
    part = _message_part_for(attempt.user_message, _task_label(task))
    if part is not None:
        return human_reason(part)
    # 特调关键任务的那句话（「切换账号失败，本轮已结束：…」）不带任务名
    if attempt.failed_task == task.name and not _MULTI_FAILURE_RE.match(
        attempt.user_message.strip()
    ):
        return human_reason(attempt.user_message)
    return ""


def attempt_reason(attempt: MaaFWAttemptReport) -> str:
    """整次尝试的失败原因（一个任务都没开始、或失败不落在某个任务上时用）。"""

    record = attempt.record
    if record.category == CATEGORY_SIGNAL:
        return SIGNAL_REASONS.get(str(record.signal or ""), "")
    reason = human_reason(attempt.user_message)
    if reason:
        return reason
    category = record.category
    if category in (
        None,
        CATEGORY_INIT_FAILED,
        CATEGORY_HOST_ERROR,
        CATEGORY_TASK_FAILED,
    ) and (stage_reason := STAGE_REASONS.get(str(record.failedStage or ""))):
        return stage_reason
    return CATEGORY_REASONS.get(str(category or ""), "")


def _task_entry(task: MaaFWTaskRecord, attempt: MaaFWAttemptReport) -> str:
    """``<状态>：<任务>（原因）``，不带时间与图标。"""

    _, status = OUTCOME_MARKS.get(task.outcome, ("", task.outcome))
    reason = task_reason(task, attempt)
    return f"{status}：{_task_label(task)}" + (f"（{reason}）" if reason else "")


def _clock(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


def _any_task_started(record: MaaFWAttemptRecord) -> bool:
    return any(task.startedAt is not None for task in record.tasks)


def _timeline_rows(
    attempts: Sequence[MaaFWAttemptReport],
) -> list[tuple[float, MaaFWTaskRecord, MaaFWAttemptReport]]:
    """最后一次尝试的任务，加上前面尝试里完成过、这次没再排进计划的任务（重试跳过的）。"""

    last = attempts[-1]
    fallback = last.record.endedAt or last.record.startedAt
    rows = [
        (task.endedAt or task.startedAt or fallback, task, last)
        for task in last.record.tasks
    ]
    planned = Counter(task.name for task in last.record.tasks)
    carried: set[str] = set()
    # 倒着找：同一个任务在前面几次都完成过时取最近那次
    for earlier in reversed(attempts[:-1]):
        for task in earlier.record.tasks:
            if (
                task.outcome != OUTCOME_SUCCEEDED
                or planned[task.name]
                or task.name in carried
            ):
                continue
            carried.add(task.name)
            time_key = task.endedAt or task.startedAt or earlier.record.startedAt
            rows.append((time_key, task, earlier))
    # 稳定排序：同一时刻的保持计划顺序
    rows.sort(key=lambda row: row[0])
    return rows


def format_timeline(attempts: Sequence[MaaFWAttemptReport]) -> str:
    """逐任务时间线；最后一次一个任务都没开始时返回空串。"""

    if not attempts or not _any_task_started(attempts[-1].record):
        return ""
    lines = []
    for time_key, task, attempt in _timeline_rows(attempts):
        icon, _ = OUTCOME_MARKS.get(task.outcome, ("", ""))
        lines.append(f"{_clock(time_key)} - {icon} {_task_entry(task, attempt)}")
    return "\n".join(lines)


def failure_summary(attempts: Sequence[MaaFWAttemptReport]) -> str:
    """最后一次失败时的一句话：失败在哪些任务、为什么；一个任务都没开始就说整次为什么没跑成。"""

    if not attempts:
        return ""
    last = attempts[-1]
    failing = [
        task
        for task in last.record.tasks
        if task.outcome not in (OUTCOME_SUCCEEDED, OUTCOME_SKIPPED)
        and (task.counted or task.category in _FATAL_CATEGORIES)
    ]
    if failing:
        return "；".join(_task_entry(task, last) for task in failing)
    reason = attempt_reason(last)
    return f"MaaFW 运行失败：{reason}" if reason else "MaaFW 运行失败"


__all__ = [
    "CATEGORY_REASONS",
    "OUTCOME_MARKS",
    "SIGNAL_REASONS",
    "STAGE_REASONS",
    "MaaFWAttemptReport",
    "attempt_reason",
    "failure_summary",
    "format_timeline",
    "human_reason",
    "task_reason",
]
