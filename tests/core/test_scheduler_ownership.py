"""L1 统一记账及上层持锁覆盖下层恢复的回归。"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.config.errors import ConfigAggregateError
from app.core import Publisher
from app.core.timer import _MainTimer
from app.core.ws import protocol
from app.models.config import QueueConfig, TimeSet
from app.models.task import TaskMode, TaskTriggerReason
from app.task.mode_worker import AutoProxyWorker
from app.task.user_expander import UserExpander
from tests.core.test_maintenance_cycle_review import creation_time, make_queue
from tests.core.test_task_tree_dispatch import Builtin
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.asyncio
async def test_lock_query_reads_actual_configuration_and_missing_targets(scheduler):
    from app.api.scripts.management import ScriptLockIn, get_script_lock

    _, scripts, _, sid = scheduler
    config = scripts[sid]
    uid = next(iter(config.UserData.keys()))
    script_target = ScriptLockIn(scriptId=str(sid))
    user_target = ScriptLockIn(scriptId=str(sid), userId=str(uid))
    assert not (await get_script_lock(script_target)).locked
    ticket = await config.try_lock_x(cascade=False)
    assert ticket is not None
    try:
        assert (await get_script_lock(script_target)).locked
        assert not (await get_script_lock(user_target)).locked
    finally:
        await config.unlock(ticket)
    ticket = await config.UserData[uid].try_lock_x()
    assert ticket is not None
    try:
        assert (await get_script_lock(user_target)).locked
        assert not (await get_script_lock(script_target)).locked
    finally:
        await config.UserData[uid].unlock(ticket)
    config.UserData.remove(uid)
    await config.UserData.commit()
    assert (await get_script_lock(user_target)).code == 404


@pytest.mark.asyncio
async def test_manual_creation_preserves_trigger_clocks_and_ignores_forged_parameter_reason(
    scheduler,
):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now)
    previous_cycle, previous_startup = queue.Cycle.LastRunAt, queue.Data.LastStartupTime
    previous_timed = queue.Data.LastTimedStart
    with creation_time(now):
        uid = await manager.start(
            TaskMode.AUTO_PROXY,
            {
                0: {
                    "uid": str(qid),
                    "params": {
                        "trigger_source": "startup_task",
                        "trigger_kind": "cycle",
                    },
                }
            },
        )
    run = manager.task_handler[uid]
    assert queue.Cycle.LastRunAt == previous_cycle
    assert queue.Data.LastStartupTime == previous_startup
    assert queue.Data.LastTimedStart == previous_timed
    assert run.task_info.info.trigger is TaskTriggerReason.MANUAL
    assert "is_cycle" not in run.task_info.info.model_dump()
    assert "trigger_source" not in run.task_info.info.model_dump()
    await run.accomplish.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "category", "community_source"),
    [
        (TaskTriggerReason.MANUAL, "manual_task", "task_manual"),
        (TaskTriggerReason.STARTUP, "startup_task", "task_startup"),
        (TaskTriggerReason.TIMED, "scheduled_task", "task_scheduled"),
        (TaskTriggerReason.CYCLE, "scheduled_task", "task_scheduled"),
    ],
)
async def test_trigger_survives_queries_and_push_without_derived_fields(
    scheduler, reason, category, community_source
):
    from app.core.timer import MainTimer
    from app.services.common import telemetry

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(self):
        entered.set()
        await release.wait()

    with patch.object(Builtin, "main_task", execute):
        uid = await manager.start(
            TaskMode.AUTO_PROXY,
            {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
            trigger=reason,
        )
        run = manager.task_handler[uid]
        try:
            await asyncio.wait_for(entered.wait(), 3)
            created = next(
                call.kwargs["data"]
                for call in Publisher.send.call_args_list
                if call.kwargs["type"] == protocol.TASK_CREATED
            ).model_dump(mode="json")
            snapshot = manager.get_runtime_snapshot().tasks[0].model_dump(mode="json")
            status = manager.get_task_status(str(uid)).model_dump(mode="json")
            update = run.task_info.get_update()
            for payload in (created, snapshot, status, update["info"]):
                assert payload["trigger"] == reason.value
                assert "isCycle" not in payload
                assert "is_cycle" not in payload
                assert "trigger_source" not in payload
            assert snapshot["task"]["info"]["trigger"] == reason.value
            assert telemetry.task_trigger_category(reason) == category
            assert (
                MainTimer.schedule_community_for_task.call_args.kwargs["source"]
                == community_source
            )
        finally:
            release.set()
            await asyncio.wait_for(run.accomplish.wait(), 3)
        assert manager.get_task_status(str(uid)).trigger is reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [TaskTriggerReason.STARTUP, TaskTriggerReason.TIMED, TaskTriggerReason.CYCLE],
)
async def test_late_clock_commit_failure_rolls_back_all_clocks_and_publishes_no_task(
    scheduler, monkeypatch, reason
):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now)
    previous = queue.model_dump(context={"audience": "persist"})
    group, field = {
        TaskTriggerReason.STARTUP: ("Data", "LastStartupTime"),
        TaskTriggerReason.TIMED: ("Data", "LastTimedStart"),
        TaskTriggerReason.CYCLE: ("Cycle", "LastRunAt"),
    }[reason]

    def reject(sender, event):
        if sender is queue:
            raise ValueError("reject trigger clock")

    QueueConfig.connect(reject, group=group, field=field)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    try:
        with creation_time(now), pytest.raises(ConfigAggregateError):
            await manager.start(
                TaskMode.AUTO_PROXY,
                {0: {"uid": str(qid)}},
                trigger=reason,
            )
    finally:
        QueueConfig.disconnect(reject, group=group, field=field)
    assert queue.model_dump(context={"audience": "persist"}) == previous
    assert not manager.task_info
    assert not any(
        call.kwargs["type"] == protocol.TASK_CREATED for call in sent.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [TaskTriggerReason.STARTUP, TaskTriggerReason.TIMED, TaskTriggerReason.CYCLE],
)
async def test_l1_records_only_the_single_creation_reason(scheduler, reason):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now, startup="Always", timed=True)
    previous_startup, previous_cycle = queue.Data.LastStartupTime, queue.Cycle.LastRunAt
    previous_timed = queue.Data.LastTimedStart
    with creation_time(now):
        uid = await manager.start(
            TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}}, trigger=reason
        )
    run = manager.task_handler[uid]
    assert run.task_info.info.trigger is reason
    assert queue.Data.LastStartupTime == (
        now if reason is TaskTriggerReason.STARTUP else previous_startup
    )
    assert queue.Cycle.LastRunAt == (
        now if reason is TaskTriggerReason.CYCLE else previous_cycle
    )
    assert queue.Data.LastTimedStart == (
        now if reason is TaskTriggerReason.TIMED else previous_timed
    )
    await run.accomplish.wait()


@pytest.mark.asyncio
async def test_manual_run_does_not_consume_a_new_schedule_in_the_same_minute(scheduler):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone().replace(second=5, microsecond=0)
    qid, queue = await make_queue(queues, sid, now=now, timed=False, cycle=False)
    with creation_time(now):
        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
    await manager.task_handler[uid].accomplish.wait()
    queue.Info.TimeEnabled = True
    await queue.commit()
    queue.TimeSet.add(
        TimeSet,
        payload={"Info": {"Time": now, "Days": [now.strftime("%A")]}},
    )
    await queue.TimeSet.commit()
    later = now + timedelta(seconds=15)
    with (
        creation_time(later),
        patch("app.core.timer._local_now", return_value=later),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(wraps=manager.start)) as start,
    ):
        timer = _MainTimer()
        await timer.timed_start()
        await timer.timed_start()
        await _MainTimer().timed_start()
    assert [call.kwargs["trigger"] for call in start.await_args_list] == [
        TaskTriggerReason.TIMED
    ]
    assert queue.Data.LastTimedStart == later
    await asyncio.gather(*(run.accomplish.wait() for run in manager._running.values()))


@pytest.mark.asyncio
async def test_cycle_acceptance_does_not_consume_a_rejected_timed_trigger(scheduler):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone().replace(second=5, microsecond=0)
    _, queue = await make_queue(queues, sid, now=now, timed=True)
    create = manager.start
    reject_timed = True

    async def submit(mode, tasks, *, trigger):
        nonlocal reject_timed
        if trigger is TaskTriggerReason.TIMED and reject_timed:
            reject_timed = False
            raise RuntimeError("timed rejected")
        return await create(mode, tasks, trigger=trigger)

    with (
        creation_time(now),
        patch("app.core.timer._local_now", return_value=now),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(side_effect=submit)) as start,
    ):
        timer = _MainTimer()
        await timer.timed_start()
        await timer.timed_start()
    assert [call.kwargs["trigger"] for call in start.await_args_list] == [
        TaskTriggerReason.TIMED,
        TaskTriggerReason.CYCLE,
        TaskTriggerReason.TIMED,
    ]
    assert queue.Data.LastTimedStart == queue.Cycle.LastRunAt == now
    await asyncio.gather(*(run.accomplish.wait() for run in manager._running.values()))


@pytest.mark.asyncio
async def test_one_rejected_trigger_does_not_prevent_other_independent_submissions(
    scheduler,
):
    manager, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    qid, queue = await make_queue(queues, sid, now=now, startup="Always", timed=True)
    previous_startup = queue.Data.LastStartupTime
    create = manager.start

    async def submit(mode, tasks, *, trigger):
        if trigger is TaskTriggerReason.STARTUP:
            raise RuntimeError("startup rejected")
        return await create(mode, tasks, trigger=trigger)

    with (
        creation_time(now),
        patch("app.core.timer._local_now", return_value=now),
        patch("app.core.timer.TaskManager", manager),
        patch.object(manager, "start", AsyncMock(side_effect=submit)) as start,
    ):
        await _MainTimer().timed_start(startup=True)
    assert start.await_count == 3
    runs = list(manager.task_handler.values())
    assert [run.task_info.info.trigger for run in runs] == [
        TaskTriggerReason.TIMED,
        TaskTriggerReason.CYCLE,
    ]
    assert all(run.task_info.script_list[0].script_id == str(sid) for run in runs)
    assert queue.Data.LastStartupTime == previous_startup
    assert queue.Cycle.LastRunAt == now
    await asyncio.gather(*(run.accomplish.wait() for run in runs))


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_restore", [False, True])
async def test_parent_locks_cover_child_restoration_and_are_released_after_failure(
    scheduler, fail_restore
):
    manager, scripts, _, sid = scheduler
    config = scripts[sid]
    events = []

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            assert config.is_locked and self.user_config.is_locked
            await self.user_info.set_state(status="完成")

        async def finish(self):
            assert config.is_locked and self.user_config.is_locked
            events.append("user restore")

    class Expander(UserExpander):
        def build_worker(self, user, user_config):
            return Worker(self, user, user_config)

        async def finish(self):
            assert config.is_locked
            assert not any(user.is_locked for user in config.UserData.values())
            events.append("script restore")
            if fail_restore:
                raise RuntimeError("script restore failed")

    def build(script, locked_config):
        assert locked_config is config and config.is_locked
        return Expander(script, locked_config)

    manager.plugin_expander = build
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert events == ["user restore", "user restore", "script restore"]
    assert not config.is_locked and not any(
        user.is_locked for user in config.UserData.values()
    )
    assert run.task_info.status == ("error" if fail_restore else "success")


@pytest.mark.asyncio
async def test_cancel_during_user_lock_wait_releases_only_owned_script_lock(scheduler):
    manager, scripts, _, sid = scheduler
    config = scripts[sid]
    user = next(iter(config.UserData.values()))
    ticket = await user.lock_x()

    class Expander(UserExpander):
        def build_worker(self, user, config):
            raise AssertionError("locked user must not start")

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    try:
        for _ in range(100):
            if "等待用户配置" in run.task_info.script_list[0].log:
                break
            await asyncio.sleep(0.01)
        assert config.is_locked
        assert "等待用户配置" in run.task_info.script_list[0].log
        assert run.task_info.script_list[0].user_list[0].status == "等待"
        await asyncio.wait_for(manager.stop(uid), 3)
        assert not config.is_locked
        assert user.is_locked
        assert run.task_info.status == "cancelled"
    finally:
        await user.unlock(ticket)
        await manager.stop(uid)


@pytest.mark.asyncio
async def test_plugin_probe_releases_its_ticket_before_legacy_recursive_lock(scheduler):
    manager, scripts, _, sid = scheduler
    config = scripts[sid]
    seen = []

    def probe(script, entry):
        assert entry is config and entry.is_locked
        seen.append("probe")
        return None

    class Legacy(Builtin):
        async def main_task(self):
            ticket = await config.try_lock_x(cascade=True)
            assert ticket is not None
            try:
                seen.append("legacy")
                await super().main_task()
            finally:
                await config.unlock(ticket)

    manager.plugin_expander = probe
    manager.manager_factories = {type(config): Legacy}
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert seen == ["probe", "legacy"]
    assert run.task_info.status == "success"
    assert not config.is_locked and not any(
        user.is_locked for user in config.UserData.values()
    )
