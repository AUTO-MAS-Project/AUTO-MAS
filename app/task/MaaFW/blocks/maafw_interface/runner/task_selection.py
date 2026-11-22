"""展开任务快照：把账号的任务快照变成「今天真要跑的队列」与「被排除的实例及原因」。

调用顺序（宿主给有规则的脚本类型建计划时）：

1. ``inspect_task_snapshot``：只看快照本身——interface 里已没有的任务名、对不上的选项值、
   红灯与今天不在运行日的实例。不会失败。
2. ``expand_task_snapshot``：归一化出勾选的实例，**先**按规则表剔掉不可选任务、**再**把今天不在
   运行日的实例拿出来，剩下的就是交给调用方排队列的今日队列。顺序不能反：队列剔空了，调用方就
   不该给它补首尾任务。
3. 调用方按自己的规则排队列（可以补受管任务；自动补任务时跳过 ``excluded_task_ids``）。
4. ``merge_arranged_queue``：调用方补回的同一实例照常运行、不受运行日限制；没补回的停跑日实例
   排回队尾，交给建计划按原因记成跳过（不校验它们的选项）。
5. 建计划，再 ``apply_plan_rules`` 把规则表的标记落到计划上，``attach_snapshot_findings`` 把第 1 步
   的发现接到计划上。建计划失败时用 ``describe_plan_failure`` 补上原因。

第 4、5 步合成一个 ``build_arranged_plan``：调用方先后调 ``expand_task_snapshot``、自己排队列、
``build_arranged_plan``，排队列不经回调。

本模块与 ``run_plan`` 一样只依赖核心包与标准库，不认识具体项目。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.task.MaaFW.blocks.maafw_interface.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)
from app.task.MaaFW.blocks.maafw_interface.interface.plan_rules import MaaFWPlanRules
from app.task.MaaFW.blocks.maafw_interface.interface.task_config import (
    excluded_task_ids_for_weekday,
    find_missing_task_names,
    unchecked_task_ids,
)

from .models import MaaFWRunPlan, MaaFWSkippedTaskPlan
from .run_plan import (
    ALL_TASKS_SKIPPED_MESSAGE,
    NO_RUNNABLE_TASKS_MESSAGE,
    QUEUE_SKIPPED_TASK_REASON,
    build_maafw_run_plan,
    describe_stale_option_values,
    select_snapshot_tasks,
)

logger = logging.getLogger("automas.maafw.runner.task_selection")

#: ISO 星期（1=周一）对应的叫法，运行日跳过原因用。
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
#: 运行日跳过原因的后半句：「今天周一，不在运行日」。
OFF_DAY_REASON_SUFFIX = "，不在运行日"
#: 队列里的任务在当前 interface 里已没有时的跳过原因。
MISSING_TASK_REASON = "interface 内已无该任务"

ExcludedKind = Literal["unselectable", "unchecked", "off_day"]


def off_day_reason(iso_weekday: int) -> str:
    """今天不在运行日的实例的跳过原因（「今天周一，不在运行日」）。"""

    return f"今天{WEEKDAY_NAMES[iso_weekday - 1]}{OFF_DAY_REASON_SUFFIX}"


@dataclass(frozen=True)
class MaaFWExcludedTask:
    """被排除、这一轮不跑的一个实例。"""

    task_id: str
    name: str
    """显示名：任务 label（不是 ``$`` 开头的 i18n 键时），否则任务名。"""
    reason: str
    kind: ExcludedKind


@dataclass(frozen=True)
class MaaFWSnapshotInspection:
    """只看快照本身得到的发现（不归一化队列、不会失败）。"""

    missing_task_names: tuple[str, ...]
    """勾选了、但 interface 里已没有的任务名（队列顺序，每份实例一项）。"""
    stale_option_warnings: tuple[str, ...]
    """保存的选项值在当前 interface 里已对不上时给运行日志的提示。"""
    unchecked_ids: tuple[str, ...]
    """用户设成红灯的实例。"""
    off_day_ids: tuple[str, ...]
    """勾选了、但今天不在运行日的实例（快照里的全部，不只是归一化后还在的）。"""
    off_day_reason: str

    def off_day_reasons(self) -> dict[str, str]:
        """``{实例 id: 跳过原因}``，建计划的 ``excluded_task_reasons`` 用。"""

        return dict.fromkeys(self.off_day_ids, self.off_day_reason)

    def missing_skips(self) -> list[MaaFWSkippedTaskPlan]:
        return [
            MaaFWSkippedTaskPlan(name=name, reason=MISSING_TASK_REASON)
            for name in self.missing_task_names
        ]


def inspect_task_snapshot(
    base_dir: str | Path,
    interface_model: MaaFWInterface,
    task_snapshot: dict[str, Any] | None,
    *,
    iso_weekday: int,
) -> MaaFWSnapshotInspection:
    """只看快照（密码字段已解开的那份）：失效任务名、失效选项值、红灯与今天不在运行日的实例。

    今天是星期几由调用方按本机时间给（与队列「执行日期」同口径），只在开跑建计划时判这一次。
    """

    stale: list[str] = []
    if task_snapshot:
        try:
            stale = describe_stale_option_values(
                base_dir, interface_model, task_snapshot
            )
        except Exception:  # noqa: BLE001 - 只是提示，算不出来不挡运行
            logger.warning("MaaFW 失效选项值检查失败", exc_info=True)
    return MaaFWSnapshotInspection(
        missing_task_names=tuple(
            find_missing_task_names(task_snapshot, interface_model)
        ),
        stale_option_warnings=tuple(stale),
        unchecked_ids=tuple(unchecked_task_ids(task_snapshot)),
        off_day_ids=tuple(excluded_task_ids_for_weekday(task_snapshot, iso_weekday)),
        off_day_reason=off_day_reason(iso_weekday),
    )


@dataclass(frozen=True)
class MaaFWSnapshotExpansion:
    """展开任务快照的结果：今日队列与被排除的实例。"""

    inspection: MaaFWSnapshotInspection
    task_ids: tuple[str, ...]
    """今天真要跑的实例（剔掉了不可选任务与今天不在运行日的实例），交给调用方排队列。"""
    task_options: Mapping[str, Any]
    """今日队列里各实例的选项（归一化过）。"""
    global_options: Mapping[str, Any]
    """账号的全局选项表（归一化过）。"""
    unselectable: tuple[MaaFWExcludedTask, ...] = ()
    """按规则表剔掉的不可选实例（队列顺序）。"""
    off_day_queued_ids: tuple[str, ...] = ()
    """归一化后还在队列里、因今天不在运行日而拿出来的实例（队列顺序）。"""
    off_day_options: Mapping[str, Any] = field(default_factory=dict)
    excluded: tuple[MaaFWExcludedTask, ...] = ()
    """被排除的实例及原因：不可选、红灯、今天不在运行日（同一实例只列第一种，按这个顺序）。"""
    notices: tuple[str, ...] = ()
    """要写进账号运行日志的话（剔掉不可选任务时按原因合并的一行）。"""

    @property
    def excluded_task_ids(self) -> frozenset[str]:
        """本轮不跑的实例：红灯与今天不在运行日的。调用方自动补任务时不要补回它们。"""

        return frozenset([*self.inspection.unchecked_ids, *self.inspection.off_day_ids])

    def unselectable_names(self) -> list[str]:
        """剔掉的不可选任务显示名（去重、按队列）。"""

        return list(dict.fromkeys(item.name for item in self.unselectable))


def _task_display_name(task: Any) -> str:
    label = getattr(task, "label", None)
    if isinstance(label, str) and label.strip() and not label.lstrip().startswith("$"):
        return label.strip()
    return str(getattr(task, "name", ""))


def _task_lookup(interface_model: MaaFWInterface) -> Callable[[str], Any]:
    """实例 id → interface 里的任务（重复实例按任务名认）；找不到返回 None。"""

    task_by_name = {task.name: task for task in interface_model.task}

    def task_of(task_id: str) -> Any:
        return task_by_name.get(resolve_task_instance_name(str(task_id), task_by_name))

    return task_of


def _excluded_tasks(
    interface_model: MaaFWInterface,
    unselectable: list[MaaFWExcludedTask],
    inspection: MaaFWSnapshotInspection,
) -> tuple[MaaFWExcludedTask, ...]:
    task_of = _task_lookup(interface_model)
    listed = {item.task_id for item in unselectable}
    result = list(unselectable)
    groups: tuple[tuple[ExcludedKind, tuple[str, ...], str], ...] = (
        ("unchecked", inspection.unchecked_ids, QUEUE_SKIPPED_TASK_REASON),
        ("off_day", inspection.off_day_ids, inspection.off_day_reason),
    )
    for kind, ids, reason in groups:
        for task_id in ids:
            if task_id in listed:
                continue
            listed.add(task_id)
            task = task_of(task_id)
            result.append(
                MaaFWExcludedTask(
                    task_id=task_id,
                    name=_task_display_name(task) if task is not None else task_id,
                    reason=reason,
                    kind=kind,
                )
            )
    return tuple(result)


def _drop_unselectable(
    interface_model: MaaFWInterface,
    task_ids: list[str],
    task_options: dict[str, Any],
    entries: Mapping[str, str],
) -> tuple[list[str], dict[str, Any], list[MaaFWExcludedTask], list[str]]:
    """剔掉规则表里不可选的任务（连同选项）；日志按原因合并成一行（同名任务只列一次）。"""

    if not entries:
        return task_ids, task_options, [], []
    task_of = _task_lookup(interface_model)

    def entry_of(task_id: str) -> str:
        task = task_of(task_id)
        return str(task.entry or "") if task is not None else ""

    kept: list[str] = []
    dropped: list[MaaFWExcludedTask] = []
    # 原因 → 被剔任务显示名（dict 保序：原因按首次出现，名字按队列，同名只列一次）
    by_reason: dict[str, dict[str, None]] = {}
    for task_id in task_ids:
        entry = entry_of(task_id)
        if entry not in entries:
            kept.append(task_id)
            continue
        name = _task_display_name(task_of(task_id))
        by_reason.setdefault(entries[entry], {})[name] = None
        dropped.append(
            MaaFWExcludedTask(
                task_id=task_id, name=name, reason=entries[entry], kind="unselectable"
            )
        )
    notices = [
        "已跳过" + "".join(f"「{name}」" for name in names) + f"：{reason}"
        for reason, names in by_reason.items()
    ]
    if not dropped:
        return task_ids, task_options, [], notices
    options = {
        key: value
        for key, value in task_options.items()
        if entry_of(key) not in entries
    }
    return kept, options, dropped, notices


def expand_task_snapshot(
    base_dir: str | Path,
    interface_model: MaaFWInterface,
    *,
    task_snapshot: dict[str, Any] | None,
    selected_preset: str | None,
    iso_weekday: int,
    rules: MaaFWPlanRules,
    inspection: MaaFWSnapshotInspection | None = None,
) -> MaaFWSnapshotExpansion:
    """展开账号的任务快照（快照为空时按预设或默认勾选），顺序见模块说明。

    ``inspection`` 是同一份快照先算好的 ``inspect_task_snapshot``（调用方要在归一化失败时也拿到
    失效任务名），不给就在这里算。归一化失败（全部设为跳过、预设找不到……）照常抛
    ``MaaFWRunPlanError``。
    """

    if inspection is None:
        inspection = inspect_task_snapshot(
            base_dir, interface_model, task_snapshot, iso_weekday=iso_weekday
        )
    task_ids, task_options, global_options = select_snapshot_tasks(
        interface_model,
        selected_preset=selected_preset,
        task_snapshot=task_snapshot or None,
    )
    task_ids, task_options, unselectable, notices = _drop_unselectable(
        interface_model, task_ids, task_options, rules.unselectable
    )
    off_day = set(inspection.off_day_ids) & set(task_ids)
    off_day_queued = [task_id for task_id in task_ids if task_id in off_day]
    return MaaFWSnapshotExpansion(
        inspection=inspection,
        task_ids=tuple(task_id for task_id in task_ids if task_id not in off_day),
        task_options={
            key: value for key, value in task_options.items() if key not in off_day
        },
        global_options=global_options,
        unselectable=tuple(unselectable),
        off_day_queued_ids=tuple(off_day_queued),
        off_day_options={
            task_id: task_options[task_id]
            for task_id in off_day_queued
            if task_id in task_options
        },
        excluded=_excluded_tasks(interface_model, unselectable, inspection),
        notices=tuple(notices),
    )


@dataclass(frozen=True)
class MaaFWArrangedQueue:
    """调用方排好的队列，合上今天不在运行日的实例之后交给建计划。"""

    task_ids: list[str]
    task_options: dict[str, Any]
    excluded_task_reasons: dict[str, str]
    """没被调用方补回的停跑日实例 → 跳过原因（建计划的 ``excluded_task_reasons``）。"""


def merge_arranged_queue(
    expansion: MaaFWSnapshotExpansion,
    task_ids: Iterable[str],
    task_options: Mapping[str, Any],
) -> MaaFWArrangedQueue:
    """调用方按自己的规则补回的同一实例（受管任务）照常运行、不受运行日限制；其余停跑日实例
    排在队尾、带上原来的选项，由建计划在建覆盖前排除并按原因记成跳过（不校验它们的选项）。"""

    arranged = list(task_ids)
    restored = set(arranged)
    extra = [
        task_id for task_id in expansion.off_day_queued_ids if task_id not in restored
    ]
    return MaaFWArrangedQueue(
        task_ids=[*arranged, *extra],
        task_options={
            **task_options,
            **{
                task_id: expansion.off_day_options[task_id]
                for task_id in extra
                if task_id in expansion.off_day_options
            },
        },
        excluded_task_reasons=dict.fromkeys(extra, expansion.inspection.off_day_reason),
    )


def apply_plan_rules(plan: MaaFWRunPlan, rules: MaaFWPlanRules) -> MaaFWRunPlan:
    """把规则表的标记落到计划任务上：失败即结束本轮（``abortRoundMessage``）与失败不计
    （``nonFatalMessage``），都按任务 entry 认。没有这两类规则时原样返回。"""

    if not rules.abort_round and not rules.nonfatal:
        return plan
    tasks = []
    for task in plan.tasks:
        update: dict[str, str] = {}
        if task.entry in rules.abort_round:
            update["abortRoundMessage"] = rules.abort_round[task.entry]
        if task.entry in rules.nonfatal:
            update["nonFatalMessage"] = rules.nonfatal[task.entry]
        tasks.append(task.model_copy(update=update) if update else task)
    return plan.model_copy(update={"tasks": tasks})


def attach_snapshot_findings(
    plan: MaaFWRunPlan, inspection: MaaFWSnapshotInspection
) -> MaaFWRunPlan:
    """把快照发现接到计划上：失效选项值的提示接在计划自己的提示后面（重复的只留一条），
    interface 内已无的任务排在计划自己的跳过项前面。"""

    if inspection.stale_option_warnings:
        plan = plan.model_copy(
            update={
                "warnings": list(
                    dict.fromkeys([*plan.warnings, *inspection.stale_option_warnings])
                )
            }
        )
    missing = inspection.missing_skips()
    if missing:
        plan = plan.model_copy(update={"skippedTasks": [*missing, *plan.skippedTasks]})
    return plan


def build_arranged_plan(
    base_dir: str | Path,
    interface: MaaFWInterface,
    *,
    expansion: MaaFWSnapshotExpansion,
    inspection: MaaFWSnapshotInspection,
    task_ids: Iterable[str],
    task_options: Mapping[str, Any],
    task_snapshot: dict[str, Any],
    controller_name: str | None,
    resource_name: str | None,
    script_hotkeys: dict[str, dict[str, str]] | None,
    rules: MaaFWPlanRules,
    client_version: str = "",
) -> MaaFWRunPlan:
    """按调用方排好的队列建计划（有规则的专项：展开快照 → 专项自己排队列 → 这里）。

    依次：合上没被补回的停跑日实例（:func:`merge_arranged_queue`）→ 建计划（已选任务拆成
    ``task_ids`` 交进去；仍带上原始快照，让用户显式设为跳过的实例写进 ``skippedTasks``，并从它取
    从密文解出来的字段；全局选项取展开时那份；规则表里不回落 default 的字段照规则）→ 落规则表的
    标记（:func:`apply_plan_rules`）→ 接上快照发现（:func:`attach_snapshot_findings`）。

    异常原样抛出，由调用方统一包成 ``MaaFWRunPlanError(describe_plan_failure(...))``。排队列不经
    回调：展开与这里之间是调用方自己的普通代码。

    ``client_version`` 原样交给 :func:`build_maafw_run_plan`（写进 ``PI_CLIENT_VERSION``）。
    """

    queue = merge_arranged_queue(expansion, task_ids, task_options)
    plan = build_maafw_run_plan(
        base_dir,
        interface,
        controller_name=controller_name,
        resource_name=resource_name,
        task_snapshot=task_snapshot,
        task_ids=queue.task_ids,
        task_options=queue.task_options,
        global_options=dict(expansion.global_options),
        script_hotkeys=script_hotkeys,
        no_default_fallback_inputs=rules.no_default_fallback_inputs,
        excluded_task_reasons=queue.excluded_task_reasons,
        client_version=client_version,
    )
    return attach_snapshot_findings(apply_plan_rules(plan, rules), inspection)


def describe_plan_failure(
    message: str,
    inspection: MaaFWSnapshotInspection | None,
    expansion: MaaFWSnapshotExpansion | None,
) -> str:
    """建计划报「没有可执行任务」/「全部设为跳过」时补上原因：队列里只剩 interface 已没有的
    任务、或只剩不可选任务时，光这一句说不清（「已跳过」那行在账号日志里，报错里看不到）。
    别的报错与它们无关，原样返回。"""

    if (
        NO_RUNNABLE_TASKS_MESSAGE not in message
        and ALL_TASKS_SKIPPED_MESSAGE not in message
    ):
        return message
    if inspection is not None and inspection.missing_task_names:
        names = "、".join(dict.fromkeys(inspection.missing_task_names))
        message = f"{message}（interface 内已无：{names}）"
    if expansion is not None and expansion.unselectable:
        names = "、".join(expansion.unselectable_names())
        message = f"{message}（已跳过不可选任务：{names}）"
    return message


__all__ = [
    "MISSING_TASK_REASON",
    "OFF_DAY_REASON_SUFFIX",
    "WEEKDAY_NAMES",
    "MaaFWArrangedQueue",
    "MaaFWExcludedTask",
    "MaaFWSnapshotExpansion",
    "MaaFWSnapshotInspection",
    "apply_plan_rules",
    "attach_snapshot_findings",
    "build_arranged_plan",
    "describe_plan_failure",
    "expand_task_snapshot",
    "inspect_task_snapshot",
    "merge_arranged_queue",
    "off_day_reason",
]
