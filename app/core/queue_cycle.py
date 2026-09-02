#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""循环队列的调度计算

这里只做纯粹的时间推算，不碰任何运行状态，方便单独测试。

**时间口径**：下次运行时间是要落盘、跨重启存活的，所以只能用本地墙钟表示，
不能用单调时钟。代价是系统时钟跳变（夏令时切换、NTP 校时）会让推算结果偏移，
调用方必须按下面两条兜底：

1. 每轮循环都用当前时间重新推算，不要缓存推算结果；
2. 等待时对单次 sleep 设上限，跳变最多让一轮迟到那个上限，而不是无限期挂起。

夏令时的两种边界都不会漏跑：春季跳过的时刻（如 02:30）在时钟跳到 03:00 后
立刻满足「已到点」，表现为迟到而非跳过；秋季重复的时刻只会触发一次，因为跑完
是以「结束时间之后」为基准推算下一次的。

固定时间模式星期全不选表示「不排期」，推算函数返回 None、条目不参与调度——
与定时队列「执行周期为空则永不触发」的口径一致。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from app.utils.constants import CYCLE_DATETIME_FORMAT, CYCLE_EMPTY_TIME


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


@dataclass(frozen=True)
class CycleEntry:
    """循环队列中一个待运行的队列项。"""

    queue_item_id: str
    script_id: str
    script_name: str
    index: int  # 在任务脚本列表中的下标
    next_run_at: datetime
    is_due: bool


def format_cycle_time(value: datetime) -> str:
    """把时间格式化为落盘用的字符串。"""

    return value.strftime(CYCLE_DATETIME_FORMAT)


def parse_cycle_time(value: str | None) -> datetime | None:
    """解析落盘的时间字符串，无法解析时返回 None。"""

    if not value:
        return None
    try:
        return datetime.strptime(value, CYCLE_DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def is_empty_cycle_time(value: datetime | None) -> bool:
    """判断是否为空值哨兵，即「尚未推算」。"""

    if value is None:
        return True
    empty = parse_cycle_time(CYCLE_EMPTY_TIME)
    return empty is not None and value <= empty


def format_next_run(value: datetime | None) -> str:
    """下次运行时间落盘用：推算不出来（不排期）时写空值哨兵。"""

    return format_cycle_time(value) if value is not None else CYCLE_EMPTY_TIME


def next_fixed_time(
    *, days: Iterable[str], hhmm: str, after: datetime
) -> datetime | None:
    """推算固定时间模式下 ``after`` 之后的第一个执行时刻。

    Args:
        days: 允许执行的星期名，一个都没选表示不排期，返回 None。
        hhmm: 执行时间，格式 ``HH:MM``。
        after: 推算基准，返回值严格晚于它。
    """

    day_set = {day for day in days if day in WEEKDAY_NAMES}
    if not day_set:
        return None

    try:
        hour, minute = (int(part) for part in hhmm.split(":"))
    except (AttributeError, TypeError, ValueError):
        hour, minute = 0, 0

    # 最多看 8 天：一周内必定命中，第 8 天用于处理今天已过点的情况。
    for offset in range(8):
        candidate = (after + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate > after and WEEKDAY_NAMES[candidate.weekday()] in day_set:
            return candidate

    return (after + timedelta(days=1)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def _interval_minutes(queue_item) -> int:
    """取间隔分钟数，兜底为 1 分钟避免忙转。"""

    try:
        return max(1, int(queue_item.get("Schedule", "IntervalMinutes")))
    except (TypeError, ValueError):
        return 1


def resolve_next_run(queue_item, now: datetime) -> datetime | None:
    """取队列项的下次运行时间；尚未推算过时按模式给出初值。

    间隔模式的初值是「立刻」——用户刚打开循环，不该再等一个完整间隔。
    固定时间模式没选星期时返回 None，表示不排期。
    """

    next_run_at = parse_cycle_time(queue_item.get("Schedule", "NextRunAt"))
    if not is_empty_cycle_time(next_run_at):
        return next_run_at

    if queue_item.get("Schedule", "Mode") == "fixed_time":
        return next_fixed_time(
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
            after=now,
        )
    return now


def next_after_start(
    queue_item, started_at: datetime, after: datetime | None = None
) -> datetime | None:
    """按「上次开始」基准推算下次运行时间。

    ``after`` 用于跑得比间隔还久的情况：一路加间隔直到越过它，避免一结束就
    立刻再来一轮。
    """

    if queue_item.get("Schedule", "Mode") == "fixed_time":
        return next_fixed_time(
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
            after=after or started_at,
        )

    interval = timedelta(minutes=_interval_minutes(queue_item))
    next_run_at = started_at + interval
    while after is not None and next_run_at <= after:
        next_run_at += interval
    return next_run_at


def next_after_finish(queue_item, finished_at: datetime) -> datetime | None:
    """按「上次结束」基准推算下次运行时间。"""

    if queue_item.get("Schedule", "Mode") == "fixed_time":
        return next_fixed_time(
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
            after=finished_at,
        )

    return finished_at + timedelta(minutes=_interval_minutes(queue_item))


def collect_cycle_entries(queue, script_config, now: datetime) -> list[CycleEntry]:
    """收集队列中已启用循环的条目。

    ``index`` 必须与任务脚本列表对齐，所以过滤条件要和建任务时完全一致：
    先按 ``_TaskManager._queue_script_ids`` 去掉未选脚本，再按 ``Task.prepare``
    去掉已被删除的脚本；两步都会推进下标，之后才轮到「是否启用循环」。
    """

    entries: list[CycleEntry] = []
    index = -1

    for queue_item_id, queue_item in queue.QueueItem.items():
        script_id = str(queue_item.get("Info", "ScriptId") or "").strip()
        if not script_id or script_id == "-":
            continue

        try:
            script_uid = uuid.UUID(script_id)
        except ValueError:
            continue
        if script_uid not in script_config:
            continue

        index += 1

        if not queue_item.get("Schedule", "Enabled"):
            continue

        next_run_at = resolve_next_run(queue_item, now)
        if next_run_at is None:
            continue
        entries.append(
            CycleEntry(
                queue_item_id=str(queue_item_id),
                script_id=script_id,
                script_name=script_config[script_uid].get("Info", "Name"),
                index=index,
                next_run_at=next_run_at,
                is_due=next_run_at <= now,
            )
        )

    return entries


def due_entries(entries: list[CycleEntry]) -> list[CycleEntry]:
    """取已到点的条目，按队列顺序排列。"""

    return sorted((entry for entry in entries if entry.is_due), key=lambda e: e.index)


def sort_for_preview(entries: list[CycleEntry]) -> list[CycleEntry]:
    """预览排序：已到点的按队列顺序在前，其余按时间先后。"""

    waiting = sorted(
        (entry for entry in entries if not entry.is_due),
        key=lambda e: (e.next_run_at, e.index),
    )
    return due_entries(entries) + waiting


def is_script_success(script_status: str, user_statuses: Iterable[str]) -> bool:
    """判断这一轮脚本是否算跑成功。

    脚本级状态是「完成」直接算成功；否则要求所有用户都完成——用户全部完成而
    脚本状态没来得及更新时，不该判成失败。
    """

    if script_status == "完成":
        return True

    statuses = list(user_statuses)
    return bool(statuses) and all(status == "完成" for status in statuses)
