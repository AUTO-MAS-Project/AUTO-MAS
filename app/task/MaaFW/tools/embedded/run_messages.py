"""运行这一块给人看的文案与格式化：账号日志的行、运行总览、失败摘要、重试与周期的提示。

全是纯函数和常量：吃计划（``MaaFWRunPlan``）、运行结果（``MaaFWRunResult``）、worker 推来的运行
记录事件这类普通数据，返回字符串或普通数据。不读配置、不碰调用方的对象；写日志、置状态、记账、
上报进度点都由调用方（各专项的账号流程）照原来的先后做。

**不导入 maa**：管理器（运行前更新日志的行格式，``update_log_lines``）也用它，导入闭包只有解析一侧、
运行记录事件与 worker 协议常量。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.task.MaaFW.blocks.maafw_interface.log_redact import DETAIL_LOG_PREFIX
from app.task.MaaFW.blocks.maafw_interface.runner.models import (
    MaaFWRunPlan,
    MaaFWSkippedTaskPlan,
)
from app.task.MaaFW.blocks.maafw_interface.runner.plan_transforms import (
    PERIOD_DONE_REASONS,
)
from app.task.MaaFW.blocks.maafw_interface.runner.plan_transforms import (
    RETRY_SKIP_REASON as RETRY_SKIP_REASON,
)
from app.task.MaaFW.blocks.maafw_interface.runner.run_plan import (
    QUEUE_SKIPPED_TASK_REASON,
)
from app.task.MaaFW.blocks.maafw_interface.runner.task_selection import (
    OFF_DAY_REASON_SUFFIX,
)
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_SCRIPT_STOPPED,
    CATEGORY_USER_STOPPED,
    MaaFWTaskEndEvent,
    MaaFWTaskStartEvent,
)
from app.task.MaaFW.tools.core.worker_protocol import SIGNAL_SCREENSHOT_KINDS

if TYPE_CHECKING:  # pragma: no cover - 只给类型检查用
    from app.task.run_flow import PointState

_RUN_OVERVIEW_LOG_VALUE_LIMIT = 1200

#: 任务报告里「失效任务」一行的前缀：队列里的任务 interface 已没有，本次跳过。
MISSING_TASK_NOTICE_PREFIX = (
    "失效任务（interface 内已无，已跳过，请到账号配置里重新添加）"
)
#: 其余任务都跑完、但队列里有失效任务时统计报告的结果：照常算完成，不说「全部完成」。
MISSING_TASK_USER_RESULT = "代理任务完成，但有失效任务"
#: ``RETRY_SKIP_REASON``：重试时被剔掉的任务的跳过原因（进 skippedTasks 与尝试日志），
#: 定义在 ``plan_transforms``，从这里一并给出。


def format_user_log_line(message: str) -> str:
    """一条账号日志：每行前面加 ``[HH:MM:SS]``（本机时间），行尾换行。"""

    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    lines = str(message).splitlines() or [""]
    return "".join(f"[{timestamp}] {line}\n" for line in lines)


def update_log_lines(message: str, now: datetime) -> list[str] | None:
    """运行前更新的一条日志在账号日志里的样子（与 ``format_user_log_line`` 同一格式，并进账号日志后
    看不出接缝）；详情行（``DETAIL_LOG_PREFIX`` 开头，比如健康检查的完整 traceback）只进后端日志，
    返回 None。"""

    if str(message).startswith(DETAIL_LOG_PREFIX):
        return None
    timestamp = now.strftime("%H:%M:%S")
    return [f"[{timestamp}] {line}\n" for line in str(message).splitlines() or [""]]


# worker 截图文件名是 ``[<前缀>.]<kind>-<HHMMSS>-<任务>.png``，信号证据图的 kind 与 worker
# 共用 worker_protocol.SIGNAL_SCREENSHOT_KINDS。
_SIGNAL_EVIDENCE_NAME_RE = re.compile(
    r"(?:^|\.)(?:"
    + "|".join(re.escape(kind) for kind in SIGNAL_SCREENSHOT_KINDS.values())
    + r")-\d{6}-"
)


def signal_evidence_shot(result: Any) -> Any | None:
    """信号命中那个任务的证据图；找不到就不带图（宁缺勿错）。"""

    for shot in getattr(result, "failureScreenshots", None) or ():
        if shot.task == result.failedTask and _SIGNAL_EVIDENCE_NAME_RE.search(
            Path(shot.path).name
        ):
            return shot
    return None


_FAILURE_REASON_MAX_CHARS = 300


def failure_reason_for_user(result: Any) -> str:
    """从运行结果里取一句可读的失败原因。

    runner 会把异常原文放进 ``errorMessage``，但它同时也用
    ``MaaFW 任务执行失败: {exc}`` 发一条日志——那条命中
    ``worker_protocol._RAW_FAILURE_UI_LOG_MARKERS`` 会被当框架噪声过滤掉。若这里再不取，
    Python 侧异常（如缺模块）在任务页上就只剩「任务执行失败」四个字。

    框架自身的失败原文可能是整段原生 backtrace，因此只取首个非空行并截断；
    完整内容仍在本次运行的 ``*.worker.log`` 里。
    """

    raw = str(
        getattr(result, "userMessage", None)
        or getattr(result, "errorMessage", "")
        or ""
    ).strip()
    if not raw:
        return ""
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    while len(first_line) > _FAILURE_REASON_MAX_CHARS and "；" in first_line:
        first_line = first_line.rsplit("；", 1)[0]
    if len(first_line) > _FAILURE_REASON_MAX_CHARS:
        first_line = first_line[: _FAILURE_REASON_MAX_CHARS - 1] + "…"
    return first_line


def failed_task_user_summary(result: Any, plan: Any | None) -> str:
    """一次失败的尝试给人看的一句话：失败在哪个任务、为什么。"""

    if getattr(result, "userMessage", None):
        return failure_reason_for_user(result)
    failed_task = str(getattr(result, "failedTask", "") or "").strip()
    reason = failure_reason_for_user(result)
    if not failed_task:
        # 还没投递任何任务就失败了（ADB 未就绪、Agent 连接超时、资源加载失败……）：
        # 不把原因挂到第一个任务头上，用户会去查错任务
        return f"MaaFW 运行失败{'：' + reason if reason else ''}"
    suffix = f"：任务执行失败{'：' + reason if reason else ''}"
    tasks = tuple(getattr(plan, "tasks", ()) or ()) if plan is not None else ()
    if tasks:
        for task in tasks:
            task_name = str(getattr(task, "name", "") or "").strip()
            task_entry = str(getattr(task, "entry", "") or "").strip()
            if failed_task and failed_task not in {task_name, task_entry}:
                continue
            return f"{task_display_name(task)}{suffix}"
    return f"{failed_task or 'MaaFW 任务'}{suffix}"


def task_display_name(task: Any) -> str:
    """任务在日志与报告里的称呼：有可读的 label 用 label，否则用任务名。"""

    label = getattr(task, "label", None)
    # 红灯记录的 label 已在建计划时解析；用户自己起的名字可以以 $ 开头。
    queue_skipped = (
        isinstance(task, MaaFWSkippedTaskPlan)
        and task.reason == QUEUE_SKIPPED_TASK_REASON
    )
    if (
        isinstance(label, str)
        and label.strip()
        and (queue_skipped or not label.lstrip().startswith("$"))
    ):
        return label.strip()
    return str(getattr(task, "name", ""))


def format_completed_task_labels(
    plan: MaaFWRunPlan | None,
    task_names: list[str],
) -> list[str]:
    """任务名换成计划里的称呼；计划里没有的原样保留。"""

    labels_by_name = (
        {task.name: task_display_name(task) for task in plan.tasks}
        if plan is not None
        else {}
    )
    return [labels_by_name.get(task_name, task_name) for task_name in task_names]


def format_run_overview_log(
    plan: MaaFWRunPlan,
    *,
    selected_preset: str,
) -> str:
    """账号日志开头的「MaaFW 运行总览」那一行。

    问题包导出（``frontend/electron/services/maafwIssueReportService.ts``）按这一行的格式认主日志，
    两边一起改。
    """

    task_names = " -> ".join(task_display_name(task) for task in plan.tasks) or "-"
    if len(task_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        task_names = task_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    project_name = (
        plan.projectLabel.strip()
        if isinstance(plan.projectLabel, str)
        and plan.projectLabel.strip()
        and not plan.projectLabel.lstrip().startswith("$")
        else plan.projectName
    )
    project_version = str(plan.piEnv.get("PI_VERSION") or "").strip() or "未知"
    overview = (
        "MaaFW 运行总览: "
        f"project={project_name}; version={project_version}; "
        f"controller={plan.controllerName}; resource={plan.resourceName}; "
        f"preset={selected_preset or '自定义'}; "
        f"enabled_tasks({len(plan.tasks)})={task_names}"
    )
    if not plan.skippedTasks:
        return overview

    # 被跳过的任务此前没有任何出口，用户把任务加进队列却看不出它为什么没跑。
    skipped_names = " -> ".join(
        f"{task_display_name(task)}({task.reason})" for task in plan.skippedTasks
    )
    if len(skipped_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        skipped_names = skipped_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    return f"{overview}; skipped_tasks({len(plan.skippedTasks)})={skipped_names}"


def retry_skipped_tasks(plan: MaaFWRunPlan) -> list[MaaFWSkippedTaskPlan]:
    """计划里因「前面的尝试已完成」被重试剔掉的任务。"""

    return [task for task in plan.skippedTasks if task.reason == RETRY_SKIP_REASON]


def retry_skip_log_lines(
    plan: MaaFWRunPlan | None, rerun_duplicates: list[str]
) -> list[str]:
    """重试开头要写的几行：被重试剔掉的任务，以及同名多份、全部重跑的任务；计划为 None 时没有。"""

    if plan is None:
        return []
    lines: list[str] = []
    skipped = retry_skipped_tasks(plan)
    if skipped:
        lines.append(
            f"{RETRY_SKIP_REASON}，不再补跑: "
            + "、".join(task_display_name(task) for task in skipped)
        )
    duplicates = list(dict.fromkeys(rerun_duplicates))
    if duplicates:
        labels = format_completed_task_labels(plan, duplicates)
        lines.append(
            f"{'、'.join(labels)} 在队列里有多份，分不清完成的是哪一份，重试时全部重跑"
        )
    return lines


def remaining_done_message(plan: MaaFWRunPlan) -> str:
    """重试前刷新计划后剩不下任务时停止重试的那一行；计划被重试跳过剔空的，不能说成「周期任务」。"""

    return (
        "MaaFW 剩余任务都已完成，停止本轮重试"
        if retry_skipped_tasks(plan)
        else "MaaFW 剩余周期任务已完成，停止本轮重试"
    )


def describe_failed_result(
    result: Any, plan: MaaFWRunPlan | None, *, run_time_limit: Any
) -> str:
    """一次失败的尝试（不是资源包加载失败）进账号日志与日志状态的那句话。

    整次运行超时：限制几分钟、完成了几个、最后停在哪；其余：失败在哪个任务、为什么，计划有不止
    一个任务且完成过的再补「（共 N 个任务，完成 M 个）」（前面尝试已完成、这次被剔掉的算进去）。
    ``run_time_limit`` 是 ``Run.RunTimeLimit`` 的原值，原样写进超时那句。
    """

    if result.timedOut:
        total = len(plan.tasks) if plan is not None else 0
        stopped_at = ""
        if result.failedTask and plan is not None:
            labels = format_completed_task_labels(plan, [result.failedTask])
            stopped_at = f"，最后停在 {labels[0]}"
        return (
            f"MaaFW 任务运行超时（限制 {run_time_limit} 分钟，已完成 "
            f"{len(result.completedTasks)}/{total}{stopped_at}）"
        )
    message = failed_task_user_summary(result, plan)
    retry_skipped = (
        sum(1 for skipped in plan.skippedTasks if skipped.reason == RETRY_SKIP_REASON)
        if plan is not None
        else 0
    )
    total = len(plan.tasks) + retry_skipped if plan is not None else 0
    done = len(result.completedTasks) + retry_skipped
    if total > 1 and done > 0:
        message += f"（共 {total} 个任务，完成 {done} 个）"
    return message


_PERIOD_DONE_LABELS = {
    PERIOD_DONE_REASONS["daily"]: "今日",
    PERIOD_DONE_REASONS["weekly"]: "本周",
    PERIOD_DONE_REASONS["monthly"]: "本月",
}


def period_all_done_message(plan: MaaFWRunPlan) -> str:
    """队列里的任务都因周期限制被跳过时的提示，按实际跳过原因说今日 / 本周 / 本月。"""

    periods: list[str] = []
    for task in plan.skippedTasks:
        label = _PERIOD_DONE_LABELS.get(task.reason or "")
        if label and label not in periods:
            periods.append(label)
    ordered = [label for label in ("今日", "本周", "本月") if label in periods]
    # 运行日的说法只在跳过原因全是「不在运行日」（或再加周期已完成）时用；混了红灯、失效任务
    # 等别的原因时，照改动前这种情况原本的提示说
    reasons = [task.reason or "" for task in plan.skippedTasks]
    off_day = any(reason.endswith(OFF_DAY_REASON_SUFFIX) for reason in reasons)
    only_off_day_or_period = all(
        reason.endswith(OFF_DAY_REASON_SUFFIX) or reason in _PERIOD_DONE_LABELS
        for reason in reasons
    )
    if off_day and only_off_day_or_period and not ordered:
        return "MaaFW 队列里的任务今天都不在运行日，跳过本次运行"
    if off_day and only_off_day_or_period:
        return (
            f"MaaFW 队列里的任务今天不在运行日或已在{' / '.join(ordered)}完成，"
            "跳过本次运行"
        )
    if not periods:
        return "MaaFW 队列里的周期任务都已在本周期内完成，跳过本次运行"
    return f"MaaFW 队列里的周期任务都已在{' / '.join(ordered)}完成，跳过本次运行"


@dataclass(frozen=True)
class MaaFWSignalFacts:
    """worker 回报信号节点命中时，收尾要用的事实（都从结果与计划里算出，不含项目名）。

    ``labels`` 是这次完成的任务称呼；``report_shots`` 是进统计与汇总的失败截图（标签, 路径），
    不含证据图；``evidence_path`` 是只随信号通知发一次的证据图。项目名要读 interface 的显示名，
    由调用方在工作线程里取。
    """

    signal: str
    message: str
    labels: list[str]
    report_shots: list[tuple[str, Path]]
    evidence_path: Path | None
    resource_name: str
    resource_label: str
    node: str | None


def signal_attempt_facts(
    result: Any,
    plan: MaaFWRunPlan | None,
    *,
    user_messages: Mapping[str, str],
) -> MaaFWSignalFacts:
    """信号命中这次尝试的事实。``user_messages`` 是「信号 → 给人看的原因」（``SIGNAL_USER_MESSAGES``），
    没有的信号用结果里的错误原文，再没有就用信号名。"""

    signal = str(result.signal)
    message = user_messages.get(signal, str(result.errorMessage or signal))
    # 证据图只认命中那个任务、kind 是信号那种的：前面任务普通失败的 failed 图不算。
    evidence = signal_evidence_shot(result)
    labels = (
        format_completed_task_labels(plan, result.completedTasks)
        if plan is not None
        else list(result.completedTasks)
    )
    # 证据图只随信号通知发一次，不再进统计信息与代理结果汇总；前面任务的普通
    # 失败截图照常进。
    report_shots = [
        (
            format_completed_task_labels(plan, [shot.task])[0]
            if plan is not None
            else shot.task,
            Path(shot.path),
        )
        for shot in result.failureScreenshots
        if shot is not evidence
    ]
    resource_label = ""
    if plan is not None:
        label = str(plan.resource.label or "").strip()
        resource_label = (
            label if label and not label.startswith("$") else plan.resourceName
        )
    return MaaFWSignalFacts(
        signal=signal,
        message=message,
        labels=labels,
        report_shots=report_shots,
        evidence_path=Path(evidence.path) if evidence is not None else None,
        resource_name=plan.resourceName if plan is not None else result.resourceName,
        resource_label=resource_label,
        node=result.signalNode,
    )


def record_event_point(event: Any) -> tuple[str, PointState] | None:
    """worker 推来的任务起止事件对应的进度点 ``(任务名, 状态)``（阶段一律是 ``special``）；
    别的事件没有进度点，返回 None。

    结束事件：成功 / 跳过照原样；用户停止算 cancelled；脚本侧强停计入失败的算 failed，
    不计入的与其它原因的停止算 stopped；其余结局（超时、失败……）算 failed。
    """

    if isinstance(event, MaaFWTaskStartEvent):
        return event.name, "entered"
    if isinstance(event, MaaFWTaskEndEvent):
        state: PointState = "failed"
        if event.outcome in ("succeeded", "skipped"):
            state = event.outcome
        elif event.outcome == "stopped":
            if event.category == CATEGORY_USER_STOPPED:
                state = "cancelled"
            elif event.category != CATEGORY_SCRIPT_STOPPED or not event.counted:
                state = "stopped"
        return event.name, state
    return None


__all__ = [
    "MISSING_TASK_NOTICE_PREFIX",
    "MISSING_TASK_USER_RESULT",
    "RETRY_SKIP_REASON",
    "MaaFWSignalFacts",
    "describe_failed_result",
    "failed_task_user_summary",
    "failure_reason_for_user",
    "format_completed_task_labels",
    "format_run_overview_log",
    "format_user_log_line",
    "period_all_done_message",
    "record_event_point",
    "remaining_done_message",
    "retry_skip_log_lines",
    "retry_skipped_tasks",
    "signal_attempt_facts",
    "signal_evidence_shot",
    "task_display_name",
    "update_log_lines",
]
