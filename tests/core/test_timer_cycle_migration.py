import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.core.queue_schedule import next_item_run
from app.core.timer import _MainTimer
from app.models.config.queue import QueueItemEntry
from app.utils.constants import UTC8


def test_interval_from_start_skips_missed_rounds():
    async def check():
        now = datetime(2026, 10, 9, 12, tzinfo=UTC8)
        entry = QueueItemEntry.build(payload={"schedule": {"mode": "interval", "interval_minutes": 30}, "data": {"last_cycle_started_at": now - timedelta(hours=2)}})
        await entry.activate()
        assert next_item_run(entry, now=now, completed=True) == now + timedelta(minutes=30)
    asyncio.run(check())


def test_timer_dispatches_only_one_due_item(monkeypatch):
    async def check():
        from app.core import timer
        now = datetime(2026, 10, 9, 12, tzinfo=UTC8)
        script_id = str(uuid4())
        entry = QueueItemEntry.build(payload={"info": {"script_id": script_id}, "schedule": {"mode": "interval", "interval_minutes": 30}})
        await entry.activate()
        start = AsyncMock()
        monkeypatch.setattr(timer, "Config", SimpleNamespace(ScriptConfig={script_id: object()}))
        monkeypatch.setattr(timer, "TaskDispatcher", SimpleNamespace(start=start))
        instance = _MainTimer()
        monkeypatch.setattr(instance, "schedule_game_sign_for_task", lambda: None)
        item_id = uuid4()
        queue = SimpleNamespace(items={item_id: entry, uuid4(): entry})
        await instance.cycle_start(str(uuid4()), queue, now=now)
        start.assert_awaited_once()
        assert start.call_args.kwargs["queue_item_id"] == str(item_id)
        assert entry.schedule.next_run_at == now + timedelta(minutes=30)
    asyncio.run(check())


def test_fixed_schedule_without_days_does_not_run():
    async def check():
        entry = QueueItemEntry.build(payload={"schedule": {"days": []}})
        await entry.activate()
        assert next_item_run(entry, now=datetime.now(tz=UTC8)) is None
    asyncio.run(check())
