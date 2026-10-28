"""MAA 队列日志的任务级结果解析。"""

import re
from dataclasses import dataclass

from .constants import MAA_TASKS, MAA_TASKS_ZH

_TASK_START_RE = re.compile(r"开始任务:\s*(?P<name>[^\r\n]+)")
_SANITY_CONSUMPTION_RE = re.compile(r"开始行动\s+\d+(?:~\d+)?\s*次,\s*-[1-9]\d*\s*理智")
_ERROR_SUMMARY_RE = re.compile(r"任务已结束，以下任务出现错误[:：]?\s*(.*)")
_EVENT_ERROR_SUMMARY_RE = re.compile(r"任务已结束，以下任务出现错误[:：]\s*([^\r\n]+)")
_EVENT_ERROR_RE = re.compile(
    r"任务出错:\s*(?:活动关均衡理智|活动库存保持)"
    r"(?:\s+#\d+| \(仓库识别\))?\s*$",
    re.M,
)
_EVENT_COMPLETION_RE = re.compile(
    r"完成任务: (?:活动关均衡理智|活动库存保持)"
    r"(?:\s+#\d+| \(仓库识别\))?\s*$",
    re.M,
)

_ALIASES = {
    **{task: {name} for task, name in zip(MAA_TASKS, MAA_TASKS_ZH, strict=True)},
    "EventDepotMaintain": {"活动关均衡理智", "活动库存保持"},
}
_ALIASES["DepotMaintain"].update(("库存保持", "养成计划"))
_ALIASES["Fight"].update(("理智作战", "剿灭作战"))


@dataclass(frozen=True)
class MaaTaskResult:
    completed: frozenset[str]
    skipped: frozenset[str]
    errors: frozenset[str | None]
    sanity_spent: frozenset[str]
    failed: bool


def _canonical_task(name: str) -> str | None:
    name = name.removesuffix(" (仓库识别)").partition(" #")[0]
    for task, aliases in _ALIASES.items():
        if name in aliases:
            return task
    return None


def parse_maa_task_result(log: str) -> MaaTaskResult:
    """将一次 MAA 日志归一为队列任务结果，保留任务开始行提供的错误作用域。"""

    # 保留常规任务原有的全文子串匹配，不受错误清单的读取范围影响。
    completed = {
        task
        for task in MAA_TASKS
        if any(f"完成任务: {name}" in log for name in _ALIASES[task])
    }
    skipped = {
        task
        for task in MAA_TASKS
        if any(f"{name} 任务跳过" in log for name in _ALIASES[task])
    }
    errors: set[str | None] = set()
    sanity_spent: set[str] = set()
    current_task: str | None = None
    in_error_summary = False

    for line in log.splitlines():
        task_match = _TASK_START_RE.search(line)
        if task_match:
            current_task = _canonical_task(task_match.group("name").strip())
            in_error_summary = False

        summary_match = _ERROR_SUMMARY_RE.search(line)
        if summary_match:
            in_error_summary = True
            summary_name = summary_match.group(1).strip()
            if summary_name:
                errors.add(_canonical_task(summary_name))
            continue

        if in_error_summary:
            summary_name = line.strip()
            if not summary_name or "(用时" in summary_name:
                in_error_summary = False
            elif not summary_name.startswith("["):
                errors.add(_canonical_task(summary_name))
            continue

        if current_task and _SANITY_CONSUMPTION_RE.search(line):
            sanity_spent.add(current_task)
        if "任务出错:" in line or (
            current_task == "DepotMaintain" and "理智不足" in line and "已跳过" in line
        ):
            errors.add(current_task)

    # 活动阶段必须由 MAA 确认整段完成；摘要正则保留跨行读取首项的兼容行为。
    error_summaries = _EVENT_ERROR_SUMMARY_RE.findall(log)
    event_failed = bool(_EVENT_ERROR_RE.search(log)) or any(
        name in summary
        for summary in error_summaries
        for name in _ALIASES["EventDepotMaintain"]
    )
    if not event_failed:
        if _EVENT_COMPLETION_RE.search(log) and (
            "任务已全部完成！" in log or error_summaries
        ):
            completed.add("EventDepotMaintain")
        if any(f"{name} 任务跳过" in log for name in _ALIASES["EventDepotMaintain"]):
            skipped.add("EventDepotMaintain")

    # 错误集合用于归属，序列失败仍服从 MAA 收尾与同名任务最后一次完成/出错。
    failed = (
        "任务已完成，但出现错误！" in log
        or "任务已结束，以下任务出现错误" in log
        or any(
            log.rfind(f"任务出错: {name}") > log.rfind(f"完成任务: {name}")
            for name in re.findall(r"任务出错: ([^\r\n]+)", log)
        )
    )

    return MaaTaskResult(
        completed=frozenset(completed),
        skipped=frozenset(skipped),
        errors=frozenset(errors),
        sanity_spent=frozenset(sanity_spent),
        failed=failed,
    )
