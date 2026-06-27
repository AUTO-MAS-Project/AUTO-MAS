from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


QUEUE_CYCLE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
QUEUE_CYCLE_EMPTY_TIME = "2000-01-01 00:00:00"


@dataclass(frozen=True)
class QueueCycleEntry:
    queue_item_id: str
    script_id: str
    script_name: str
    index: int
    mode: str
    next_run_at: datetime
    is_due: bool


def format_cycle_time(value: datetime) -> str:
    return value.strftime(QUEUE_CYCLE_DATETIME_FORMAT)


def parse_cycle_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, QUEUE_CYCLE_DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def is_empty_cycle_time(value: datetime | None) -> bool:
    empty_time = parse_cycle_time(QUEUE_CYCLE_EMPTY_TIME)
    return value is None or (empty_time is not None and value <= empty_time)


def _next_fixed_time(
    *,
    now: datetime,
    days: Iterable[str],
    hhmm: str,
    after: datetime | None = None,
) -> datetime:
    day_set = set(days)
    if not day_set:
        day_set = {
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        }

    hour, minute = [int(part) for part in hhmm.split(":")]
    base = after or now
    for offset in range(8):
        candidate = (base + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= base:
            continue
        if candidate.strftime("%A") in day_set:
            return candidate
    return (base + timedelta(days=1)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def resolve_queue_item_next_run(queue_item, now: datetime) -> datetime:
    mode = queue_item.get("Schedule", "Mode")
    next_run_at = parse_cycle_time(queue_item.get("Schedule", "NextRunAt"))
    if not is_empty_cycle_time(next_run_at):
        return next_run_at

    if mode == "fixed_time":
        return _next_fixed_time(
            now=now,
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
        )
    return now


def calculate_next_after_start(
    queue_item, started_at: datetime, after: datetime | None = None
) -> datetime:
    mode = queue_item.get("Schedule", "Mode")
    if mode == "fixed_time":
        return _next_fixed_time(
            now=started_at,
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
            after=after or started_at,
        )

    interval = max(1, int(queue_item.get("Schedule", "IntervalMinutes")))
    next_run_at = started_at + timedelta(minutes=interval)
    while after is not None and next_run_at <= after:
        next_run_at += timedelta(minutes=interval)
    return next_run_at


def calculate_next_after_finish(queue_item, finished_at: datetime) -> datetime:
    mode = queue_item.get("Schedule", "Mode")
    if mode == "fixed_time":
        return _next_fixed_time(
            now=finished_at,
            days=queue_item.get("Schedule", "Days"),
            hhmm=queue_item.get("Schedule", "Time"),
            after=finished_at,
        )

    interval = max(1, int(queue_item.get("Schedule", "IntervalMinutes")))
    return finished_at + timedelta(minutes=interval)


def collect_queue_cycle_entries(queue, script_config, now: datetime) -> list[QueueCycleEntry]:
    entries: list[QueueCycleEntry] = []
    script_index = -1
    for queue_item_id, queue_item in queue.QueueItem.items():
        script_id = queue_item.get("Info", "ScriptId")
        if script_id == "-":
            continue
        script_index += 1

        if not queue_item.get("Schedule", "Enabled"):
            continue

        script_uid = None
        try:
            script_uid = uuid.UUID(script_id)
        except (TypeError, ValueError):
            continue
        if script_uid not in script_config:
            continue

        next_run_at = resolve_queue_item_next_run(queue_item, now)
        entries.append(
            QueueCycleEntry(
                queue_item_id=str(queue_item_id),
                script_id=script_id,
                script_name=script_config[script_uid].get("Info", "Name"),
                index=script_index,
                mode=queue_item.get("Schedule", "Mode"),
                next_run_at=next_run_at,
                is_due=next_run_at <= now,
            )
        )
    return entries


def pick_next_cycle_entry(entries: list[QueueCycleEntry]) -> QueueCycleEntry | None:
    if not entries:
        return None
    due_entries = [entry for entry in entries if entry.is_due]
    if due_entries:
        return sorted(due_entries, key=lambda item: item.index)[0]
    return sorted(entries, key=lambda item: (item.next_run_at, item.index))[0]


def collect_waiting_cycle_entries(
    entries: list[QueueCycleEntry], active_entry: QueueCycleEntry
) -> list[QueueCycleEntry]:
    return sorted(
        (
            entry
            for entry in entries
            if entry.is_due and entry.queue_item_id != active_entry.queue_item_id
        ),
        key=lambda item: item.index,
    )


def is_cycle_script_success(script_status: str, user_statuses: Iterable[str]) -> bool:
    if script_status == "完成":
        return True

    status_list = list(user_statuses)
    return bool(status_list) and all(status == "完成" for status in status_list)
