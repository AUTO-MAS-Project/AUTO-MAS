from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable, Sequence, TypeVar


CYCLE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CYCLE_EMPTY_DATETIME = datetime(2000, 1, 1)

_DAY_NAME_TO_WEEKDAY = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

_T = TypeVar("_T")


def parse_cycle_datetime(value: object) -> datetime | None:
    """解析持久化的循环时间，空值和旧哨兵均视为未设置。"""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.strptime(value.strip(), CYCLE_DATETIME_FORMAT)
        except ValueError:
            return None
    else:
        return None

    return None if parsed <= CYCLE_EMPTY_DATETIME else parsed


def format_cycle_datetime(value: datetime | None) -> str:
    """将循环时间格式化为稳定的持久化字符串。"""

    return (value or CYCLE_EMPTY_DATETIME).strftime(CYCLE_DATETIME_FORMAT)


def calculate_next_cycle_run(
    *,
    now: datetime,
    mode: str,
    days: Iterable[str],
    time_text: str,
    interval_minutes: int,
    interval_anchor: str,
    next_run_at: object = None,
    last_started_at: object = None,
    last_finished_at: object = None,
) -> datetime:
    """计算队列项的下一次运行时间。

    ``next_run_at`` 是一次性权威覆盖；消费后调用方应使用实际开始/结束
    时间再次计算并写回。固定时间按本地分钟精度运行，间隔模式在没有历史
    锚点时立即到期。
    """

    explicit_next = parse_cycle_datetime(next_run_at)
    if explicit_next is not None:
        return explicit_next

    if mode == "interval":
        if not 1 <= interval_minutes <= 10080:
            raise ValueError("IntervalMinutes 必须在 1 到 10080 之间")
        if interval_anchor not in {"start", "finish"}:
            raise ValueError("IntervalAnchor 必须是 start 或 finish")

        anchor_value = (
            last_started_at if interval_anchor == "start" else last_finished_at
        )
        anchor = parse_cycle_datetime(anchor_value)
        return now if anchor is None else anchor + timedelta(minutes=interval_minutes)

    if mode != "fixed_time":
        raise ValueError("循环模式必须是 fixed_time 或 interval")

    try:
        run_time = time.fromisoformat(time_text)
    except (TypeError, ValueError) as error:
        raise ValueError("Time 必须是 HH:MM 格式") from error

    allowed_weekdays = {
        _DAY_NAME_TO_WEEKDAY[day]
        for day in days
        if day in _DAY_NAME_TO_WEEKDAY
    }
    if not allowed_weekdays:
        allowed_weekdays = set(range(7))

    base = now.replace(second=0, microsecond=0)
    for day_offset in range(8):
        candidate_date = (base + timedelta(days=day_offset)).date()
        candidate = datetime.combine(candidate_date, run_time)
        if candidate.weekday() in allowed_weekdays and candidate >= base:
            return candidate

    raise RuntimeError("无法计算固定时间循环的下一次运行时间")


def select_due_cycle_item(
    candidates: Sequence[tuple[int, _T, datetime]],
    *,
    now: datetime,
) -> tuple[int, _T, datetime] | None:
    """选择已经到期的最早队列项，同一时刻保持队列顺序。"""

    due = [candidate for candidate in candidates if candidate[2] <= now]
    if not due:
        return None
    return min(due, key=lambda candidate: (candidate[2], candidate[0]))


def is_cycle_script_success(
    script_status: str,
    user_statuses: Iterable[str],
) -> bool:
    """判断单次脚本运行是否成功，明确失败状态拥有最高优先级。"""

    if script_status in {"异常", "失败", "取消", "已取消"}:
        return False
    if script_status == "完成":
        return True

    statuses = list(user_statuses)
    return bool(statuses) and all(status == "完成" for status in statuses)
