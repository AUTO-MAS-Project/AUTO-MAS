"""MAA 队列日志的任务级结果解析。"""

import re
from dataclasses import dataclass

from .constants import MAA_TASKS, MAA_TASKS_ZH

_TASK_START_RE = re.compile(r"开始任务:\s*(?P<name>[^\r\n]+)")
_SANITY_CONSUMPTION_RE = re.compile(
    r"开始行动\s+\d+(?:~\d+)?\s*次,\s*-[1-9]\d*\s*理智"
)
_ERROR_SUMMARY_RE = re.compile(r"任务已结束，以下任务出现错误[:：]?\s*(.*)")
_EVENT_ERROR_SUMMARY_RE = re.compile(
    r"任务已结束，以下任务出现错误[:：]\s*([^\r\n]+)"
)
_EVENT_ERROR_RE = re.compile(
    r"任务出错:\s*(?:活动关均衡理智|活动库存保持)"
    r"(?:\s+#\d+| \(仓库识别\))?\s*$"
)
_EVENT_COMPLETION_RE = re.compile(
    r"完成任务: (?:活动关均衡理智|活动库存保持)"
    r"(?:\s+#\d+| \(仓库识别\))?\s*$"
)

_ALIASES = {
    **{task: {name} for task, name in zip(MAA_TASKS, MAA_TASKS_ZH, strict=True)},
    "EventDepotMaintain": {"活动关均衡理智", "活动库存保持"},
}
_ALIASES["DepotMaintain"].update(("库存保持", "养成计划"))
_ALIASES["Fight"].update(("理智作战", "剿灭作战"))
_STOCK_TASK = "DepotMaintain"


@dataclass(frozen=True)
class MaaTaskResult:
    completed: frozenset[str]
    skipped: frozenset[str]
    errors: frozenset[str | None]
    sanity_spent: frozenset[str]
    event_failed: bool
    event_completed: bool
    event_completion_known: bool
    partial_completion_title: bool
    error_after_completion: bool

    @property
    def stock_error(self) -> bool:
        return _STOCK_TASK in self.errors

    @property
    def other_error(self) -> bool:
        return bool(self.errors - {_STOCK_TASK})


def _task_name_matches(name: str, aliases: set[str] | frozenset[str]) -> bool:
    return any(
        name == alias
        or name.startswith(f"{alias} #")
        or name == f"{alias} (仓库识别)"
        for alias in aliases
    )


def _canonical_task(name: str) -> str | None:
    for task, aliases in _ALIASES.items():
        if _task_name_matches(name, aliases):
            return task
    return None


def parse_maa_task_result(log: str) -> MaaTaskResult:
    """将一次 MAA 日志归一为队列任务结果，保留任务开始行提供的错误作用域。"""

    completed: set[str] = set()
    skipped: set[str] = set()
    errors: set[str | None] = set()
    sanity_spent: set[str] = set()
    current_task: str | None = None
    in_error_summary = False
    event_failed = False
    event_completed = False
    event_completion_known = False

    def record_error(task: str | None) -> None:
        errors.add(task)

    for line in log.splitlines():
        if _EVENT_ERROR_RE.search(line):
            event_failed = True
        if _EVENT_COMPLETION_RE.search(line):
            event_completed = True

        task_match = _TASK_START_RE.search(line)
        if task_match:
            current_task = _canonical_task(task_match.group("name").strip())
            in_error_summary = False

        summary_match = _ERROR_SUMMARY_RE.search(line)
        if summary_match:
            in_error_summary = True
            summary_name = summary_match.group(1).strip()
            if summary_name:
                record_error(_canonical_task(summary_name))
            event_summary_match = _EVENT_ERROR_SUMMARY_RE.search(line)
            if event_summary_match:
                event_completion_known = True
                if any(
                    name in event_summary_match.group(1)
                    for name in _ALIASES["EventDepotMaintain"]
                ):
                    event_failed = True
            continue

        if in_error_summary:
            summary_name = line.strip()
            if not summary_name or "(用时" in summary_name:
                in_error_summary = False
            elif not summary_name.startswith("["):
                record_error(_canonical_task(summary_name))
            continue

        for task, aliases in _ALIASES.items():
            if any(f"完成任务: {name}" in line for name in aliases):
                completed.add(task)
            if any(f"{name} 任务跳过" in line for name in aliases):
                skipped.add(task)

        if current_task == _STOCK_TASK:
            if _SANITY_CONSUMPTION_RE.search(line):
                sanity_spent.add(current_task)
            if "任务出错:" in line or ("理智不足" in line and "已跳过" in line):
                record_error(current_task)
        elif "任务出错:" in line:
            record_error(current_task)

    all_completed = "任务已全部完成！" in log
    partial_completion = "任务已完成，但出现错误！" in log
    event_completion_known = all_completed or event_completion_known
    error_after_completion = any(
        log.rfind(f"任务出错: {name}") > log.rfind(f"完成任务: {name}")
        for name in re.findall(r"任务出错: ([^\r\n]+)", log)
    )

    return MaaTaskResult(
        completed=frozenset(completed),
        skipped=frozenset(skipped),
        errors=frozenset(errors),
        sanity_spent=frozenset(sanity_spent),
        event_failed=event_failed,
        event_completed=event_completed,
        event_completion_known=event_completion_known,
        partial_completion_title=partial_completion
        or "任务已结束，以下任务出现错误" in log,
        error_after_completion=error_after_completion,
    )
