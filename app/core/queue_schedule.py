"""新配置队列项的时间推算；触发统一由主计时器负责。"""

from datetime import datetime, timedelta

from app.models.config.queue import QueueItemEntry

from .queue_cycle import next_fixed_time


def next_item_run(
    item: QueueItemEntry, *, now: datetime, completed: bool = False
) -> datetime | None:
    """按固定时间或开始/结束间隔计算下一次，跨过运行期间已错过的间隔。"""
    schedule = item.schedule
    if schedule.mode == "fixed_time":
        return next_fixed_time(
            days=schedule.days, hhmm=schedule.time.strftime("%H:%M"), after=now
        )
    anchor = (
        item.data.last_cycle_started_at
        if schedule.interval_anchor == "start"
        else item.data.last_cycle_finished_at
    )
    if anchor is None:
        return now
    interval = timedelta(minutes=schedule.interval_minutes)
    candidate = anchor + interval
    if completed and candidate <= now:
        candidate += interval * (int((now - candidate) // interval) + 1)
    return candidate
