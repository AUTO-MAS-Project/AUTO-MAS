"""#1297 本地验证：维护消费排期但不留执行记录、不立即重试。"""

import uuid
from contextlib import nullcontext
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Config
from app.core import task_manager as scheduler
from app.core.queue_cycle import CycleEntry, format_cycle_time
from app.models.config import MaaConfig, QueueItem
from app.models.task import ScriptItem, UserItem


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 10, 10, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("anchor", ["start", "finish"])
@pytest.mark.parametrize("mode", ["interval", "fixed_time"])
async def test_cycle_skip_preserves_last_run_and_schedules_future(
    monkeypatch, anchor, mode
):
    queue_id, item_id, script_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    item = QueueItem()
    await item.set("Schedule", "Mode", mode)
    await item.set("Schedule", "IntervalAnchor", anchor)
    await item.set("Schedule", "IntervalMinutes", 60)
    await item.set("Schedule", "Time", "12:00")
    await item.set("Data", "LastCycleStartedAt", "2026-10-09 10:00:00")
    await item.set("Data", "LastCycleFinishedAt", "2026-10-09 10:15:00")
    monkeypatch.setattr(
        Config, "QueueConfig", {queue_id: SimpleNamespace(QueueItem={item_id: item})}
    )
    monkeypatch.setattr(Config, "ScriptConfig", {script_id: MaaConfig()})
    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
    monkeypatch.setattr(scheduler, "_exclusive_resources", lambda _: ((), None))
    info = scheduler.TaskInfo("AutoProxy", "test", str(queue_id), None, None)
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    script = ScriptItem(str(script_id), "test", "等待")
    info.script_list = [script]
    task = scheduler.Task(info, [])
    monkeypatch.setattr(task, "_build_task_item", lambda *args, **kwargs: object())
    monkeypatch.setattr(task, "_publish_cycle_preview", AsyncMock())
    monkeypatch.setattr(task, "_observe_script_run", lambda *args: nullcontext())

    async def skip(*args):
        script.user_list = [UserItem("u", "test", "跳过", maintenance_skipped=True)]
        script.status = "跳过"

    monkeypatch.setattr(task, "_spawn_with_preview", skip)
    entry = CycleEntry(
        str(item_id), str(script_id), "test", 0, FixedDatetime.now(), True
    )
    assert await task._run_cycle_entry(queue_id, entry, [entry]) == "skipped"
    assert item.get("Data", "LastCycleStartedAt") == "2026-10-09 10:00:00"
    assert item.get("Data", "LastCycleFinishedAt") == "2026-10-09 10:15:00"
    expected = datetime(2026, 10, 10, 11 if mode == "interval" else 12)
    assert item.get("Schedule", "NextRunAt") == format_cycle_time(expected)
    assert task.script_reservations.try_acquire(
        script_id, "next-task", root_paths=(), emulator_key=None
    )
    task.script_reservations.release(script_id, "next-task")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,retries", [("skipped", 0), ("success", 0), ("failed", 1)]
)
async def test_maintenance_does_not_trigger_immediate_retry(
    monkeypatch, result, retries
):
    task = scheduler.Task(scheduler.TaskInfo("AutoProxy", "test", None, None, None), [])
    entry = CycleEntry(
        str(uuid.uuid4()), str(uuid.uuid4()), "test", 0, datetime.now(), True
    )
    monkeypatch.setattr(task, "_collect_entries", lambda _: [entry])
    monkeypatch.setattr(task, "_run_cycle_entry", AsyncMock(return_value=result))
    sleep = AsyncMock()
    monkeypatch.setattr(scheduler.asyncio, "sleep", sleep)
    await task._run_due_entries(uuid.uuid4(), [entry])
    assert sleep.await_count == retries
