"""运行计划的两种变换：周期任务过滤与记账、重试时剔除本次已完成的任务。

都是纯函数：吃计划、名单、记录、当前时刻这类普通数据，返回新值，不读配置、不写配置。
宿主（``runner_task``）负责从配置里读出名单与记录、把返回的新记录写回配置。

- 周期任务：脚本把任务名分进「每日 / 每周 / 每月仅一次」三张名单；某个任务在当前周期里正常
  完成过（记录里它的周期键等于当前周期键）就跳过。周期键按游戏日界 UTC+4 算，与代理次数的
  「今天」（``LastProxyDate``）同一口径。
- 重试剔除：本轮有任务失败要再试一次时，把调用方允许剔除的 entry 里、本次运行前面的尝试已经
  完成过的任务剔掉，不再补跑。

本模块与 ``run_plan`` 一样只依赖核心包与标准库，不认识具体项目。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import MaaFWRunPlan, MaaFWSkippedTaskPlan

#: 游戏日界：周期键按 UTC+4 算（与宿主 ``app.utils.UTC4`` 相同；核心包不导入宿主）。
GAME_DAY_TZ = timezone(timedelta(hours=4))

#: 周期名（也是记录里的键）→ 本周期已完成时的跳过原因。
PERIOD_DONE_REASONS: dict[str, str] = {
    "daily": "今日已正常完成",
    "weekly": "本周已正常完成",
    "monthly": "本月已正常完成",
}
#: 同一个周期限制的任务在队列里有多份时，第二份起的跳过原因。
PERIOD_DUPLICATE_REASON = "本轮已安排一次"
#: 重试时被剔掉的任务的跳过原因（进 ``skippedTasks`` 与尝试日志）。
RETRY_SKIP_REASON = "前面的尝试已完成"

#: ``{"daily": {任务名: 周期键}, "weekly": {...}, "monthly": {...}}``
PeriodRecords = dict[str, dict[str, str]]


@dataclass(frozen=True)
class MaaFWPeriodLimits:
    """每日 / 每周 / 每月仅一次的任务名单。"""

    daily: frozenset[str] = frozenset()
    weekly: frozenset[str] = frozenset()
    monthly: frozenset[str] = frozenset()

    @classmethod
    def of(
        cls,
        daily: Iterable[str] = (),
        weekly: Iterable[str] = (),
        monthly: Iterable[str] = (),
    ) -> MaaFWPeriodLimits:
        return cls(frozenset(daily), frozenset(weekly), frozenset(monthly))

    @property
    def empty(self) -> bool:
        return not self.daily and not self.weekly and not self.monthly

    def by_period(self) -> dict[str, frozenset[str]]:
        return {"daily": self.daily, "weekly": self.weekly, "monthly": self.monthly}

    def limits(self, task_name: str) -> bool:
        return (
            task_name in self.daily
            or task_name in self.weekly
            or task_name in self.monthly
        )


def period_keys(now: datetime) -> dict[str, str]:
    """``now`` 所在的日 / 周 / 月周期键（按 UTC+4）：``YYYY-MM-DD``、``YYYY-Www``、``YYYY-MM``。

    带时区的 ``now`` 先换到 UTC+4；不带时区的按原样当作 UTC+4 的时刻。
    """

    current = now.astimezone(GAME_DAY_TZ) if now.tzinfo is not None else now
    iso_year, iso_week, _ = current.isocalendar()
    return {
        "daily": current.strftime("%Y-%m-%d"),
        "weekly": f"{iso_year}-W{iso_week:02d}",
        "monthly": current.strftime("%Y-%m"),
    }


def parse_period_records(raw: Mapping[str, Any]) -> PeriodRecords:
    """把配置里读出的记录归一成三张 ``{任务名: 周期键}``；不成形的部分丢掉。"""

    records: PeriodRecords = {period: {} for period in PERIOD_DONE_REASONS}
    for period in records:
        raw_period_records = raw.get(period, {})
        if isinstance(raw_period_records, dict):
            records[period] = {
                str(task_name): str(period_key)
                for task_name, period_key in raw_period_records.items()
            }
    return records


def filter_period_once_tasks(
    plan: MaaFWRunPlan,
    limits: MaaFWPeriodLimits,
    records: Mapping[str, Mapping[str, str]],
    now: datetime,
) -> MaaFWRunPlan:
    """剔掉本周期已正常完成的周期任务，并让同一个周期任务本轮只安排一次。

    剔掉的按原因追加到 ``skippedTasks``。没有任何周期名单时原样返回同一个对象。
    """

    if limits.empty:
        return plan

    keys = period_keys(now)
    by_period = limits.by_period()
    runnable_tasks = []
    skipped_tasks = []
    # 周期限制按任务算，不按队列里的份数算：同一个任务被重复加入队列时，
    # 本轮也只安排一次。否则「仅一次」在一轮内形同虚设，而且先跑的那份一
    # 成功就会把整个任务名记成已完成，还没跑的副本会被当作已完成跳过。
    period_limited_seen: set[str] = set()
    for task in plan.tasks:
        done = {
            period: task.name in names
            and records.get(period, {}).get(task.name) == keys[period]
            for period, names in by_period.items()
        }
        if any(done.values()):
            # 同时命中时说法的优先级：今日 > 本月 > 本周（与改动前一致）
            if done["daily"]:
                reason = PERIOD_DONE_REASONS["daily"]
            elif done["monthly"]:
                reason = PERIOD_DONE_REASONS["monthly"]
            else:
                reason = PERIOD_DONE_REASONS["weekly"]
            skipped_tasks.append(_skipped(task, reason))
            continue
        if limits.limits(task.name):
            if task.name in period_limited_seen:
                skipped_tasks.append(_skipped(task, PERIOD_DUPLICATE_REASON))
                continue
            period_limited_seen.add(task.name)
        runnable_tasks.append(task)
    return plan.model_copy(
        update={
            "tasks": runnable_tasks,
            "skippedTasks": [*plan.skippedTasks, *skipped_tasks],
        },
    )


def record_period_completions(
    records: Mapping[str, Mapping[str, str]],
    limits: MaaFWPeriodLimits,
    completed_tasks: Iterable[str],
    now: datetime,
) -> PeriodRecords:
    """把本次正常完成的周期任务记到当前周期，返回新的记录（不改传入的 ``records``）。

    只记在对应名单里的任务；调用方比较新旧记录，变了才写回配置。
    """

    new_records: PeriodRecords = {
        period: dict(records.get(period, {})) for period in PERIOD_DONE_REASONS
    }
    if limits.empty:
        return new_records
    keys = period_keys(now)
    completed = list(dict.fromkeys(completed_tasks))
    for period, names in limits.by_period().items():
        for task_name in completed:
            if task_name in names:
                new_records[period][task_name] = keys[period]
    return new_records


@dataclass(frozen=True)
class MaaFWRetrySkip:
    """重试剔除的结果。

    ``rerun_duplicates``：允许剔除、本次已完成过，但在计划里有多份同名的任务名（按计划顺序、
    每份一条）——分不清完成的是哪一份，一份都没剔、全部重跑，调用方据此写一行说明。
    """

    plan: MaaFWRunPlan
    rerun_duplicates: list[str] = field(default_factory=list)


def skip_tasks_completed_this_run(
    plan: MaaFWRunPlan,
    completed_this_run: Iterable[str],
    entries: frozenset[str] | set[str],
) -> MaaFWRetrySkip:
    """剔掉 ``entries`` 里、本次运行前面的尝试已完成过的任务。

    按 entry 认任务、按任务名计份数（``completed_this_run`` 是各次尝试累计的已完成任务名）。
    同名任务在计划里有多份时一份都不剔，全部重跑（见下面注释）。``entries`` 为空，或没有
    可剔的，原样返回同一个计划对象。剔掉的以 ``RETRY_SKIP_REASON`` 追加到 ``skippedTasks``。
    """

    if not entries:
        return MaaFWRetrySkip(plan=plan)
    remaining = Counter(completed_this_run)
    # runner 只回报任务名，同名的几份（比如关卡不同的两份「作战」）分不清完成的是
    # 哪一份：按队列顺序剔会剔掉失败的那份、把完成的再跑一遍。所以名字在计划里
    # 不止一份时一份都不剔，全部重跑（#1296 之前的行为）；只有一份的照常剔。
    occurrences = Counter(task.name for task in plan.tasks)
    rerun_duplicates = [
        task.name
        for task in plan.tasks
        if task.entry in entries
        and occurrences[task.name] > 1
        and remaining[task.name] > 0
    ]
    tasks = []
    skipped: list[MaaFWSkippedTaskPlan] = []
    for task in plan.tasks:
        if (
            task.entry in entries
            and occurrences[task.name] == 1
            and remaining[task.name] > 0
        ):
            remaining[task.name] -= 1
            skipped.append(_skipped(task, RETRY_SKIP_REASON))
            continue
        tasks.append(task)
    if not skipped:
        return MaaFWRetrySkip(plan=plan, rerun_duplicates=rerun_duplicates)
    return MaaFWRetrySkip(
        plan=plan.model_copy(
            update={"tasks": tasks, "skippedTasks": [*plan.skippedTasks, *skipped]}
        ),
        rerun_duplicates=rerun_duplicates,
    )


def _skipped(task: Any, reason: str) -> MaaFWSkippedTaskPlan:
    return MaaFWSkippedTaskPlan(
        name=task.name,
        label=task.label,
        entry=task.entry,
        reason=reason,
    )


__all__ = [
    "GAME_DAY_TZ",
    "PERIOD_DONE_REASONS",
    "PERIOD_DUPLICATE_REASON",
    "RETRY_SKIP_REASON",
    "MaaFWPeriodLimits",
    "MaaFWRetrySkip",
    "PeriodRecords",
    "filter_period_once_tasks",
    "parse_period_records",
    "period_keys",
    "record_period_completions",
    "skip_tasks_completed_this_run",
]
