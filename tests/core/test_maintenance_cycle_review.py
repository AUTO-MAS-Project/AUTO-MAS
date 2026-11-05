"""timer 统一派发启动、定时和循环；执行与收尾不参与循环计时。"""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.config import UiVisibility
from app.config.errors import ConfigAggregateError
from app.config.wire import ConfigInput, ConfigPayload
from app.core import Config
from app.core.timer import _MainTimer
from app.models.config import QueueConfig, QueueItem, TimeSet
from app.models.task import TaskMode, TaskTriggerReason
from tests.core.test_task_tree_dispatch import Builtin
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@contextmanager
def creation_time(now):
    with patch("app.core.task_manager.datetime") as clock:
        clock.now.return_value = now
        yield


async def make_queue(queues, sid, *, now, startup="Never", timed=False, cycle=True):
    qid = queues.add(
        QueueConfig,
        payload={
            "Info": {
                "StartUpMode": startup,
                "TimeEnabled": timed,
                "CycleEnabled": cycle,
            },
            "Cycle": {"IntervalMinutes": 60, "LastRunAt": now - timedelta(hours=1)},
        },
    )
    await queues.commit()
    queues[qid].QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queues[qid].QueueItem.commit()
    if timed:
        queues[qid].TimeSet.add(
            TimeSet,
            payload={
                "Info": {
                    "Time": now.replace(second=0, microsecond=0),
                    "Days": [now.strftime("%A")],
                }
            },
        )
        await queues[qid].TimeSet.commit()
    return qid, queues[qid]


@pytest.mark.asyncio
async def test_timer_dispatches_each_reason_independently_and_records_on_acceptance(
    scheduler,
):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone().replace(second=10, microsecond=0)
    qid, queue = await make_queue(queues, sid, now=now, startup="Always", timed=True)
    timer = _MainTimer()
    with (
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        await timer.timed_start(startup=True)
        await timer.timed_start()
    assert start.await_count == 3
    assert [call.kwargs["trigger"] for call in start.await_args_list] == [
        TaskTriggerReason.STARTUP,
        TaskTriggerReason.TIMED,
        TaskTriggerReason.CYCLE,
    ]
    for call in start.await_args_list:
        mode, tasks = call.args
        assert mode is TaskMode.AUTO_PROXY
        assert tasks == {0: {"uid": str(qid)}}
    assert queue.Data.LastStartTime == queue.Cycle.LastRunAt == now
    assert queue.Data.LastStartupTime.date() == now.date()
    assert queue.Cycle.NextRunAt == now.replace(second=0, microsecond=0) + timedelta(
        hours=1
    )


@pytest.mark.asyncio
async def test_cycle_submits_another_task_while_previous_run_is_active(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now)
    entered, release = asyncio.Event(), asyncio.Event()

    class Running(Builtin):
        async def main_task(self):
            entered.set()
            await release.wait()
            await super().main_task()

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {type(scheduler[1][sid]): lambda script: Running(script)},
    )
    timer = _MainTimer()
    with (
        patch("app.core.timer.TaskManager", manager),
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
    ):
        await timer.timed_start()
        await asyncio.wait_for(entered.wait(), 3)
    later = now + timedelta(hours=1)
    with (
        patch("app.core.timer.TaskManager", manager),
        patch("app.core.timer._local_now", return_value=later),
        creation_time(later),
    ):
        await timer.timed_start()
    runs = list(manager.task_handler.values())
    try:
        assert len(runs) == 2
        assert queue.Cycle.LastRunAt == later
        assert all(len(run.task_info.script_list) == 1 for run in runs)
    finally:
        release.set()
        await asyncio.wait_for(
            asyncio.gather(*(run.accomplish.wait() for run in runs)), 5
        )
    assert queue.Cycle.LastRunAt == later
    assert queue.Cycle.NextRunAt == later.replace(second=0, microsecond=0) + timedelta(
        hours=1
    )


@pytest.mark.asyncio
async def test_rejected_creation_does_not_advance_any_clock(scheduler):
    _, _, queues, sid = scheduler
    now = datetime.now().astimezone().replace(second=5, microsecond=0)
    _, queue = await make_queue(queues, sid, now=now, startup="Always", timed=True)
    previous = queue.model_dump(context={"audience": "persist"})
    timer = _MainTimer()
    with (
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
        patch(
            "app.core.timer.TaskManager.start",
            AsyncMock(side_effect=RuntimeError("rejected")),
        ),
    ):
        await timer.timed_start(startup=True)
    assert queue.model_dump(context={"audience": "persist"}) == previous
    assert not timer._timed_fired


@pytest.mark.asyncio
async def test_daily_startup_uses_local_date_and_is_independent_of_cycle(scheduler):
    manager, _, queues, sid = scheduler
    # UTC 日期尚未跨天，本机日期已是第二天。
    now = datetime(2026, 11, 2, 0, 5, tzinfo=timezone(timedelta(hours=9)))
    _, queue = await make_queue(queues, sid, now=now, startup="DailyFirst", cycle=False)
    timer = _MainTimer()
    with (
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        await timer.timed_start(startup=True)
        await timer.timed_start(startup=True)
    start.assert_awaited_once()
    tomorrow = now + timedelta(days=1)
    with (
        patch("app.core.timer._local_now", return_value=tomorrow),
        creation_time(tomorrow),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        await timer.timed_start(startup=True)
    start.assert_awaited_once()
    assert (
        queue.Data.LastStartupTime.astimezone(tomorrow.tzinfo).date() == tomorrow.date()
    )


@pytest.mark.asyncio
async def test_startup_async_task_runs_once_per_timer_instance(scheduler):
    timer = _MainTimer()
    with (
        patch.object(timer, "timed_start", AsyncMock()) as startup,
        patch.object(timer, "second_task", AsyncMock()),
        patch.object(timer, "hour_task", AsyncMock()),
        patch.object(timer, "calendar_task", AsyncMock()),
    ):
        await timer.start()
        await timer.startup_task
        await timer.stop()
        await timer.start()
        await timer.stop()
    startup.assert_awaited_once_with(startup=True)


@pytest.mark.asyncio
async def test_virtual_next_time_reset_trigger_and_disabled_group(scheduler):
    _, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    _, queue = await make_queue(queues, sid, now=now)
    payload = (
        ConfigPayload[QueueConfig]
        .model_validate(queue.model_dump())
        .model_dump(mode="json")
    )
    assert "ResetTimer" not in payload["Cycle"]
    assert "NextRunAt" not in queue.model_dump(context={"audience": "persist"})["Cycle"]
    contract = ConfigInput[QueueConfig].model_validate({"Cycle": {"ResetTimer": True}})
    previous = queue.Cycle.LastRunAt
    await queue.update(
        QueueConfig.model_validate(contract.model_dump(exclude_unset=True))
    )
    for _ in range(10):
        await asyncio.sleep(0)
        if queue.Cycle.LastRunAt != previous:
            break
    assert queue.Cycle.LastRunAt > previous
    assert queue.Cycle.NextRunAt == queue.Cycle.LastRunAt.replace(
        second=0, microsecond=0
    ) + timedelta(hours=1)
    await queue.update(QueueConfig.model_validate({"Info": {"CycleEnabled": False}}))
    assert queue._ui_visibility("Cycle") == UiVisibility.DISABLE
    before = queue.Cycle.LastRunAt
    await queue.update(
        QueueConfig.model_validate(
            {"Cycle": {"IntervalMinutes": 2, "ResetTimer": True}}
        )
    )
    await asyncio.sleep(0)
    assert queue.Cycle.IntervalMinutes == 60 and queue.Cycle.LastRunAt == before


@pytest.mark.asyncio
async def test_disabled_time_set_rejects_structure_changes_and_preserves_settings(
    scheduler,
):
    _, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now, timed=True, cycle=False)
    item = next(iter(queue.TimeSet.values()))
    await queue.update(QueueConfig.model_validate({"Info": {"TimeEnabled": False}}))
    assert item._ui_visibility("Info") == UiVisibility.DISABLE
    before = item.Info.Days
    await item.update(TimeSet.model_validate({"Info": {"Days": []}}))
    assert item.Info.Days == before
    with pytest.raises(ConfigAggregateError):
        await Config.add_time_set(str(qid))
    with pytest.raises(ConfigAggregateError):
        await Config.del_time_set(str(qid), str(item.uid))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "update", "delete", "order"])
async def test_disabled_time_writes_return_conflict_without_changing_configuration(
    scheduler, operation
):
    import httpx
    from fastapi import FastAPI

    from app.api.queue import router

    _, _, queues, sid = scheduler
    qid, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), timed=True, cycle=False
    )
    queue.TimeSet.add(TimeSet)
    await queue.TimeSet.commit()
    item = next(iter(queue.TimeSet.values()))
    queue.Info.TimeEnabled = False
    await queue.commit()
    before = queue.model_dump(context={"audience": "persist"})
    body: dict[str, object] = {"queueId": str(qid)}
    if operation in ("update", "delete"):
        body["timeSetId"] = str(item.uid)
    if operation == "update":
        body["data"] = {"Info": {"Days": []}}
    if operation == "order":
        body["indexList"] = list(reversed([str(uid) for uid in queue.TimeSet.keys()]))
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/api/queue/time/{operation}", json=body)
        assert response.status_code == 200 and response.json()["code"] == 409
        assert queue.model_dump(context={"audience": "persist"}) == before
        queue.Info.TimeEnabled = True
        await queue.commit()
        accepted = await client.post(f"/api/queue/time/{operation}", json=body)
        assert accepted.status_code == 200 and accepted.json()["code"] == 200


@pytest.mark.asyncio
async def test_l2_skips_queue_item_outside_its_weekday_for_cycle_trigger(scheduler):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now)
    item = next(iter(queue.QueueItem.values()))
    item.Schedule.Days = []
    await item.commit()
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": str(qid),
            }
        },
        trigger=TaskTriggerReason.CYCLE,
    )
    run = manager.task_handler[uid]
    before = queue.Cycle.LastRunAt
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.script_list[0].status == "跳过"
    assert queue.Cycle.LastRunAt == before


@pytest.mark.asyncio
async def test_reset_during_creation_is_not_overwritten_by_timer(scheduler):
    _, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    _, queue = await make_queue(queues, sid, now=now)
    reset_time = now + timedelta(seconds=20)

    async def start(*args, **kwargs):
        queue.Cycle.LastRunAt = reset_time
        await queue.commit()
        return uuid4()

    with (
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
        patch("app.core.timer.TaskManager.start", side_effect=start),
    ):
        await _MainTimer().timed_start()
    assert queue.Cycle.LastRunAt == reset_time


@pytest.mark.asyncio
async def test_existing_queue_api_accepts_reset_and_exposes_only_computed_next(
    scheduler,
):
    import httpx
    from fastapi import FastAPI

    from app.api.queue import router

    _, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        disabled = await client.post("/api/queue/time/add", json={"queueId": str(qid)})
        assert disabled.json()["code"] == 409
        before = queue.Cycle.LastRunAt
        reset = await client.post(
            "/api/queue/update",
            json={"queueId": str(qid), "data": {"Cycle": {"ResetTimer": True}}},
        )
        assert reset.json()["code"] == 200
        for _ in range(10):
            await asyncio.sleep(0)
            if queue.Cycle.LastRunAt != before:
                break
        assert queue.Cycle.LastRunAt > before
        result = (
            await client.post("/api/queue/get", json={"queueId": str(qid)})
        ).json()
        cycle = result["data"][str(qid)]["Cycle"]
        assert "ResetTimer" not in cycle
        assert datetime.fromisoformat(
            cycle["NextRunAt"]
        ) == queue.Cycle.LastRunAt.replace(second=0, microsecond=0) + timedelta(hours=1)
        unchanged = queue.Cycle.LastRunAt
        await client.post(
            "/api/queue/update",
            json={
                "queueId": str(qid),
                "data": {
                    "Cycle": {
                        "NextRunAt": "2030-01-01T00:00:00Z",
                        "LastRunAt": "2030-01-01T00:00:00Z",
                    }
                },
            },
        )
        assert queue.Cycle.LastRunAt == unchanged


@pytest.mark.asyncio
async def test_new_cycle_has_no_fabricated_last_run_and_first_tick_is_due(scheduler):
    manager, _, queues, _ = scheduler
    qid = queues.add(QueueConfig, payload={"Info": {"CycleEnabled": True}})
    await queues.commit()
    queue = queues[qid]
    assert queue.Cycle.LastRunAt is None and queue.Cycle.NextRunAt is None
    now = datetime.now().astimezone()
    with (
        patch("app.core.timer._local_now", return_value=now),
        creation_time(now),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        await _MainTimer().timed_start()
    start.assert_awaited_once()
    assert queue.Cycle.LastRunAt == now
    assert queue.Cycle.NextRunAt == now.replace(second=0, microsecond=0) + timedelta(
        minutes=queue.Cycle.IntervalMinutes
    )


@pytest.mark.asyncio
async def test_cycle_uses_minute_boundary_instead_of_last_run_seconds(scheduler):
    manager, _, queues, sid = scheduler
    now = datetime(2026, 11, 5, 10, 0, 43, 123456, tzinfo=timezone(timedelta(hours=8)))
    _, queue = await make_queue(queues, sid, now=now)
    due_minute = now.replace(second=0, microsecond=0)
    assert queue.Cycle.NextRunAt == due_minute
    timer = _MainTimer()
    with (
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        for tick, expected in (
            (due_minute - timedelta(seconds=1), 0),
            (due_minute, 1),
            (due_minute + timedelta(seconds=59), 1),
        ):
            with (
                patch("app.core.timer._local_now", return_value=tick),
                creation_time(tick),
            ):
                await timer.timed_start()
            assert start.await_count == expected
    assert queue.Cycle.NextRunAt == due_minute + timedelta(hours=1)
