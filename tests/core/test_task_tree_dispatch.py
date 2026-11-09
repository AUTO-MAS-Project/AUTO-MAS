"""任务创建、信息树身份与内建/插件分流的隔离回归。"""

import asyncio
from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.task_manager import _TaskManager
from app.models.config import (
    GeneralConfig,
    GeneralUserConfig,
    QueueConfig,
    QueueItem,
    ScriptConfigType,
)
from app.models.task import TaskMode, TaskTriggerReason
from app.task.legacy import TaskExecuteBase
from app.task.mode_worker import AutoProxyWorker, ScriptViewWorker
from app.task.user_expander import UserExpander


class Builtin(TaskExecuteBase):
    def __init__(self, script):
        super().__init__()
        self.script_info = script
        self.task_info = script.task_info

    async def main_task(self):
        for user in self.script_info.users.values():
            await user.set_state(status="完成")
        await self.script_info.set_state(status="完成")

    async def final_task(self):
        pass

    async def on_crash(self, exc):
        raise exc


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_prefetch_follows_new_dispatch_and_waits_for_cancel_cleanup(
    scheduler, monkeypatch, cancel
):
    from app.core import script_update_queue
    from app.models.task import TaskScriptItem

    manager, scripts, _, sid = scheduler
    next_id = scripts.add(GeneralConfig, payload={"Info": {"Name": "next"}})
    await scripts.commit()
    scripts[next_id].UserData.add(
        GeneralUserConfig,
        payload={"Info": {"Name": "next-user", "Status": True, "RemainedDay": -1}},
    )
    await scripts[next_id].UserData.commit()
    downloaded, cleanup_started, release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    consumed = []
    main_cancelled = asyncio.Event()
    monkeypatch.setattr(script_update_queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(script_update_queue, "PREFETCH_POLL_SECONDS", 0.001)

    class PrefetchBuiltin(Builtin):
        prepared = False

        async def prefetch_script_update(self):
            from app.utils.common.process.scope import current_process_scope

            assert current_process_scope.get() is not None
            assert scripts[next_id].is_locked
            self.prepared = True
            downloaded.set()
            if cancel:
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup_started.set()
                    await release.wait()

        async def discard_prefetched_update(self):
            self.prepared = False

        async def main_task(self):
            assert isinstance(self.script_info, TaskScriptItem)
            await self.script_info.set_state(status="运行")
            if self.script_info.info.script_id == str(sid):
                script_update_queue.report_script_task_completed()
                await downloaded.wait()
                if cancel:
                    try:
                        await asyncio.Event().wait()
                    finally:
                        main_cancelled.set()
            else:
                assert self.prepared
                consumed.append(self.script_info.info.script_id)
            await super().main_task()

    manager.manager_factories = {GeneralConfig: PrefetchBuiltin}
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {0: {"uid": "-", "children": {0: {"uid": str(sid)}, 1: {"uid": str(next_id)}}}},
    )
    run = manager.task_handler[uid]
    if cancel:
        await asyncio.wait_for(downloaded.wait(), 3)
        stop = asyncio.create_task(run.stop())
        await asyncio.wait_for(cleanup_started.wait(), 3)
        assert not stop.done() and scripts[next_id].is_locked
        assert not main_cancelled.is_set()
        release.set()
        await asyncio.wait_for(stop, 3)
        assert not consumed and run.task_info.status == "cancelled"
    else:
        await asyncio.wait_for(run.accomplish.wait(), 4)
        assert run.error is None and run.task_info.status == "success"
        assert consumed == [str(next_id)]
    assert run.task_info.current.prefetch is None
    assert not scripts[next_id].is_locked


@pytest.mark.asyncio
async def test_unconfirmed_prefetch_stop_survives_account_lifecycle(
    scheduler, monkeypatch
):
    """账号 TaskBase.run 会记录并吞掉异常，外层仍必须阻断下一托管。"""
    from app.core import script_update_queue
    from app.task.lifecycle import TaskBase
    from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

    manager, scripts, _, sid = scheduler
    next_id = scripts.add(GeneralConfig, payload={"Info": {"Name": "next"}})
    await scripts.commit()
    scripts[next_id].UserData.add(
        GeneralUserConfig,
        payload={"Info": {"Name": "next-user", "Status": True, "RemainedDay": -1}},
    )
    await scripts[next_id].UserData.commit()
    started = asyncio.Event()
    next_started = asyncio.Event()
    swallowed = []
    monkeypatch.setattr(script_update_queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(script_update_queue, "PREFETCH_POLL_SECONDS", 0.001)

    class RetryBuiltin(Builtin):
        async def prefetch_script_update(self):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                raise FluxdownCancelUnconfirmed("daemon may still write")

        async def discard_prefetched_update(self):
            pass

        async def main_task(self):
            await self.script_info.set_state(status="运行")
            if self.script_info.script_id == str(sid):
                script_update_queue.report_script_task_completed()
                await asyncio.wait_for(started.wait(), 2)

                class Account(TaskBase):
                    async def main_task(account):
                        await script_update_queue.report_script_task_retrying()

                    async def on_crash(account, error):
                        swallowed.append(error)
                        await self.script_info.user_list[0].set_state(status="异常")

                # 真实账号生命周期捕获并记录失败，不会重新抛给 L2。
                await Account().run()
                await self.script_info.set_state(status="异常")
            else:
                next_started.set()
                await super().main_task()

    manager.manager_factories = {GeneralConfig: RetryBuiltin}
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {0: {"uid": "-", "children": {0: {"uid": str(sid)}, 1: {"uid": str(next_id)}}}},
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 5)
    assert swallowed and isinstance(swallowed[0], FluxdownCancelUnconfirmed)
    assert isinstance(run.error, FluxdownCancelUnconfirmed)
    assert run.task_info.status == "error"
    assert not next_started.is_set()
    assert run.history.closed
    assert not scripts[next_id].is_locked


@pytest_asyncio.fixture
async def scheduler():
    scripts = ConfigCollection[ScriptConfigType].build([GeneralConfig])
    queues = ConfigCollection[QueueConfig].build([QueueConfig])
    await scripts.activate()
    await queues.activate()
    sid = scripts.add(GeneralConfig, payload={"Info": {"Name": "script"}})
    await scripts.commit()
    for name in ("first", "second"):
        scripts[sid].UserData.add(
            GeneralUserConfig,
            payload={"Info": {"Name": name, "Status": True, "RemainedDay": -1}},
        )
    await scripts[sid].UserData.commit()
    manager = _TaskManager()
    manager.bind_manager_factories({GeneralConfig: lambda script: Builtin(script)})
    notify = MagicMock()
    notify.task_notification_batch.side_effect = lambda **kwargs: nullcontext()
    background = BackgroundTaskRegistry()
    from app.core.power import _PowerManager

    power = _PowerManager()
    with (
        patch("app.core.task_manager.TaskManager", manager),
        patch("app.core.Power", power),
        patch("app.core.BackgroundTaskManager", background),
        patch.object(Config, "ScriptConfig", scripts),
        patch.object(Config, "QueueConfig", queues),
        patch.dict(config_manager._collections, {"ScriptConfig": scripts}),
        patch("app.task.script_expander.Notify", notify),
        patch("app.core.ws.Publisher.send", AsyncMock(return_value=True)),
        patch("app.core.desktop_guard.ensure_desktop_available", AsyncMock()),
        patch("app.core.timer.MainTimer.schedule_community_for_task"),
    ):
        yield manager, scripts, queues, sid
        for run in list(manager._running.values()):
            await asyncio.wait_for(run.stop(), 3)
        await power.cancel_power_task()
        assert await background.shutdown(timeout=3)


@pytest.mark.asyncio
async def test_internal_creation_accepts_mode_and_tree(scheduler):
    manager, scripts, _, sid = scheduler
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "children": {0: {"uid": str(sid), "params": {"instance_idx": 2}}},
            }
        },
    )
    run = manager.task_handler[uid]
    from app.models.task import TaskItem

    assert type(run.task_info) is TaskItem
    assert run.task_info.info.name == "script"
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success", (
        run.error,
        [(s.status, s.log) for s in run.task_info.script_list],
    )
    assert not manager.task_handler
    tree = manager.get_task(uid)
    assert "queues" not in tree
    script = next(iter(tree["scripts"]["data"].values()))
    assert script["info"]["script_id"] == str(sid)
    assert script["info"]["params"] == {"instance_idx": 2}
    assert next(iter(tree["scripts"]["data"])) != str(sid)
    assert len(script["users"]["data"]) == len(scripts[sid].UserData)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "error"])
async def test_completion_and_query_use_latest_virtual_result(
    scheduler, monkeypatch, outcome
):
    from datetime import datetime

    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.task import LogRecord

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()
    completed = []

    class ResultBuiltin(Builtin):
        async def main_task(self):
            await super().main_task()
            if outcome == "error":
                raise RuntimeError("synthetic failure")

        async def on_crash(self, error):
            await self.script_info.set_state(status="异常")

        async def final_task(self):
            entered.set()
            await release.wait()
            await self.script_info.user_list[0].add_log_record(
                datetime.now().astimezone(),
                LogRecord(status="收尾结果", content=["完整收尾日志\n"]),
            )

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {GeneralConfig: lambda script: ResultBuiltin(script)},
    )

    async def send(**message):
        if message["type"] == protocol.TASK_COMPLETED:
            completed.append(message["data"])
        return True

    monkeypatch.setattr(Publisher, "send", send)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    try:
        await asyncio.wait_for(entered.wait(), 3)
        before = manager.get_task(uid)["info"]["result"]
        assert before == run.task_info.info.result
        assert "收尾结果" not in before
    finally:
        release.set()
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert len(completed) == 1
    data = completed[0]
    assert data.outcome == outcome
    assert "收尾结果" in data.result
    assert data.result == data.task.info.result == run.task_info.info.result
    assert data.result == manager.get_task(uid)["info"]["result"]
    serialized = data.task.model_dump()
    stored = manager.get_task(uid)
    script_key = str(run.task_info.script_list[0].uid)
    user_key = str(run.task_info.script_list[0].user_list[0].uid)
    published_records = serialized["scripts"]["data"][script_key]["users"]["data"][
        user_key
    ]["logs"]["data"]
    queried_records = stored["scripts"]["data"][script_key]["users"]["data"][user_key][
        "logs"
    ]["data"]
    assert all("content" not in record["info"] for record in published_records.values())
    assert [record["info"]["content"] for record in queried_records.values()] == [
        ["完整收尾日志\n"]
    ]


@pytest.mark.asyncio
async def test_stop_waits_for_legacy_callback_before_terminal_tree(
    scheduler, monkeypatch
):
    from app.core import Publisher
    from app.core.ws import protocol

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()
    completed = []

    class CallbackBuiltin(Builtin):
        async def main_task(self):
            user = self.script_info.user_list[0]

            async def publish():
                entered.set()
                await release.wait()
                await user.set_state(status="完成")

            self.callbacks.submit(publish())

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {GeneralConfig: lambda script: CallbackBuiltin(script)},
    )

    async def send(**message):
        if message["type"] == protocol.TASK_COMPLETED:
            completed.append(message["data"])
        return True

    monkeypatch.setattr(Publisher, "send", send)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(entered.wait(), 3)
    stopping = asyncio.create_task(manager.stop(uid))
    try:
        await asyncio.sleep(0)
        assert not completed and not stopping.done()
    finally:
        release.set()
    await asyncio.wait_for(stopping, 3)
    assert len(completed) == 1
    assert completed[0].outcome == "cancelled"
    assert completed[0].result == completed[0].task.info.result
    assert completed[0].result == manager.get_task(uid)["info"]["result"]
    assert run.task_info.script_list[0].user_list[0].status == "完成"
    assert manager.get_task_status(str(uid)).status == "cancelled"
    assert run.history.closed


@pytest.mark.asyncio
async def test_maintenance_uses_shared_lifecycle_without_normal_panel(
    scheduler, monkeypatch
):
    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.config import BetterGIConfig

    manager, scripts, _, _ = scheduler
    scripts.add_type(BetterGIConfig)
    await scripts.commit()
    target = scripts.add(BetterGIConfig)
    await scripts.commit()
    entered = asyncio.Event()

    class Maintenance(Builtin):
        async def main_task(self):
            assert self.execution_mode == "Update"
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {BetterGIConfig: lambda script: Maintenance(script)},
    )
    plugin = MagicMock(side_effect=AssertionError("维护操作不属于插件任务模式"))
    monkeypatch.setattr(manager, "plugin_expander", plugin)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    uid = await manager.start_maintenance(str(target))
    await asyncio.wait_for(entered.wait(), 3)
    assert manager.get_task(str(uid)) is not None
    assert not manager.task_info and not manager.task_handler
    assert manager.get_runtime_snapshot().tasks == []
    assert all(
        call.kwargs["type"] != protocol.TASK_CREATED for call in sent.await_args_list
    )
    with patch("app.core.Power.cancel_power_task", AsyncMock()):
        await manager.stop("ALL")
    assert not manager._running
    assert manager.get_task_status(str(uid)).status == "cancelled"
    plugin.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_lock_uses_configuration_without_runtime_projection(scheduler):
    from app.core.notify.lifecycle import NotificationTaskBase

    _, scripts, _, sid = scheduler
    owner = MagicMock()
    owner.script_info.set_state = AsyncMock(
        side_effect=RuntimeError("projection failed")
    )
    ticket = await NotificationTaskBase.lock_script_config(owner, scripts[sid])
    try:
        assert scripts[sid].is_locked
        assert all(user.is_locked for user in scripts[sid].UserData.values())
        owner.script_info.set_state.assert_not_awaited()
    finally:
        await scripts[sid].unlock(ticket)
    assert not scripts[sid].is_locked
    assert not any(user.is_locked for user in scripts[sid].UserData.values())


@pytest.mark.asyncio
async def test_creation_notice_precedes_execution_and_completion(scheduler):
    from app.core.ws import protocol

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()
    messages = []

    async def send(**message):
        if message["type"] == protocol.TASK_CREATED:
            entered.set()
            await release.wait()
        messages.append(message)
        return True

    with patch("app.core.ws.Publisher.send", side_effect=send):
        creating = asyncio.create_task(
            manager.start(
                TaskMode.AUTO_PROXY,
                {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        run = next(iter(manager.task_handler.values()))
        try:
            assert run.task_info.status == "pending"
            assert not messages
        finally:
            release.set()
        await asyncio.wait_for(creating, 3)
        await asyncio.wait_for(run.accomplish.wait(), 3)
    assert messages[0]["type"] == protocol.TASK_CREATED
    assert messages[0]["data"].taskName == run.task_info.info.name == "script"
    assert any(message["type"] == protocol.TASK_COMPLETED for message in messages)


@pytest.mark.asyncio
async def test_runtime_cleanup_failure_ends_registered_task(scheduler, monkeypatch):
    from app.task.history_core import TaskHistorySession

    manager, _, _, sid = scheduler
    monkeypatch.setattr(
        TaskHistorySession,
        "close",
        AsyncMock(side_effect=RuntimeError("cleanup failed")),
    )
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "error"
    assert not manager.task_handler
    assert manager.get_task_status(str(uid)).status == "error"


@pytest.mark.asyncio
async def test_repeated_queue_items_keep_independent_run_identity(scheduler):
    manager, _, queues, sid = scheduler
    qid = queues.add(QueueConfig, payload={"Info": {"Name": "queue"}})
    await queues.commit()
    for _ in range(2):
        queues[qid].QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queues[qid].QueueItem.commit()
    uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success", (
        run.error,
        [(s.status, s.log) for s in run.task_info.script_list],
    )
    scripts = run.task_info.script_list
    assert len(scripts) == 2 and scripts[0].uid != scripts[1].uid
    assert all(script.parent.parent is run.task_info for script in scripts)
    assert all(
        not {"queue_id", "queue_item_id", "queue_params"}
        & script.info.model_dump().keys()
        for script in scripts
    )


@pytest.mark.asyncio
async def test_single_queue_dispatches_items_in_order(scheduler, monkeypatch):
    manager, _, queues, sid = scheduler
    qid = queues.add(QueueConfig)
    await queues.commit()
    children = {}
    for position in range(3):
        item_id = queues[qid].QueueItem.add(
            QueueItem, payload={"Info": {"ScriptId": str(sid)}}
        )
        children[position] = {"uid": str(item_id), "params": {"position": position}}
    await queues[qid].QueueItem.commit()
    calls = []

    class ObservedBuiltin(Builtin):
        async def main_task(self):
            calls.append(self.context.params["position"])
            await super().main_task()

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {GeneralConfig: lambda script: ObservedBuiltin(script)},
    )
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": str(qid), "children": children}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert calls == [0, 1, 2]
    assert run.task_info.status == "success"
    assert len({script.uid for script in run.task_info.scripts.values()}) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("second_kind", ["queue", "direct"])
async def test_multiple_roots_are_rejected_before_registration_or_clock_changes(
    scheduler, monkeypatch, second_kind
):
    from app.core import Publisher

    manager, _, queues, sid = scheduler
    qids = [queues.add(QueueConfig) for _ in range(2)]
    await queues.commit()
    previous = [queues[qid].model_dump(context={"audience": "persist"}) for qid in qids]
    second = (
        {"uid": str(qids[1])}
        if second_kind == "queue"
        else {"uid": "-", "children": {0: {"uid": str(sid)}}}
    )
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    with pytest.raises(ValueError):
        await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qids[0])}, 1: second})
    assert not manager.task_handler
    assert [
        queues[qid].model_dump(context={"audience": "persist"}) for qid in qids
    ] == previous
    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_queue_limit_distinction_survives_without_queue_identifiers(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    qid = queues.add(QueueConfig)
    await queues.commit()
    queues[qid].QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queues[qid].QueueItem.commit()
    observed = []

    class ObservedBuiltin(Builtin):
        async def main_task(self):
            observed.append(self.task_info.is_queue_task)
            assert self.script_info.parent.parent is self.task_info
            await super().main_task()

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {GeneralConfig: lambda script: ObservedBuiltin(script)},
    )
    for tasks in (
        {0: {"uid": str(qid)}},
        {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
    ):
        uid = await manager.start(TaskMode.AUTO_PROXY, tasks)
        run = manager.task_handler[uid]
        await asyncio.wait_for(run.accomplish.wait(), 4)
        assert run.task_info.status == "success"
    assert observed == [True, False]


@pytest.mark.asyncio
async def test_empty_queue_records_acceptance_without_runtime_queue(scheduler):
    manager, _, queues, _ = scheduler
    qid = queues.add(QueueConfig)
    await queues.commit()
    previous = queues[qid].Data.LastTimedStart
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}}, trigger=TaskTriggerReason.TIMED
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert queues[qid].Data.LastTimedStart != previous
    assert not run.task_info.scripts
    assert run.task_info.status == "success"


@pytest.mark.asyncio
async def test_plugin_four_levels_receive_node_parameters(scheduler):
    manager, _, _, sid = scheduler

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            assert self.context.params == {"leaf": True}
            assert self.expander.context.params == {"script": True}
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    user = next(iter(scheduler[1][sid].UserData.keys()))
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "params": {"queue": True},
                "children": {
                    0: {
                        "uid": str(sid),
                        "params": {"script": True},
                        "children": {0: {"uid": str(user), "params": {"leaf": True}}},
                    }
                },
            }
        },
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success", (
        run.error,
        [(s.status, s.log) for s in run.task_info.script_list],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [TaskMode.SCRIPT_CONFIG, TaskMode.SCRIPT_VIEW])
async def test_configuration_session_has_explicit_single_target(scheduler, mode):
    manager, scripts, _, sid = scheduler
    uid = await manager.start(
        mode,
        {
            0: {
                "uid": str(sid),
                "params": {"instance_idx": 2},
                "children": {0: {"uid": "default"}},
            }
        },
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.mode is mode
    assert run.task_info.view_only is (mode is TaskMode.SCRIPT_VIEW)
    assert run.task_info.script_list[0].info.params == {"instance_idx": 2}
    assert all(str(user) != "default" for user in scripts[sid].UserData.keys())
    for tasks in (
        {},
        {0: {"uid": str(sid)}},
        {
            0: {
                "uid": str(sid),
                "children": {0: {"uid": "default"}, 1: {"uid": "default"}},
            }
        },
    ):
        with pytest.raises(ValueError):
            await manager.start(mode, tasks)
    assert not manager.task_handler


@pytest.mark.asyncio
async def test_selection_is_an_ordered_subsequence_and_parameters_are_copied(scheduler):
    manager, scripts, _, sid = scheduler
    first, second = list(scripts[sid].UserData.keys())
    tree = {
        0: {
            "uid": "-",
            "children": {
                0: {
                    "uid": str(sid),
                    "params": {"nested": [None, {"value": True}]},
                    "children": {0: {"uid": str(first)}},
                }
            },
        }
    }
    original = deepcopy(tree)
    uid = await manager.start(TaskMode.AUTO_PROXY, tree)
    run = manager.task_handler[uid]
    tree[0]["children"][0]["params"]["nested"][1]["value"] = False
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert (
        run.task_info.script_list[0].info.params == original[0]["children"][0]["params"]
    )
    for children in (
        {0: {"uid": str(second)}, 1: {"uid": str(first)}},
        {0: {"uid": str(first)}, 1: {"uid": str(first)}},
    ):
        with pytest.raises(ValueError):
            await manager.start(
                TaskMode.AUTO_PROXY,
                {
                    0: {
                        "uid": "-",
                        "children": {0: {"uid": str(sid), "children": children}},
                    }
                },
            )
    assert not manager.task_handler


@pytest.mark.asyncio
async def test_deleting_queue_after_creation_keeps_frozen_execution_list(scheduler):
    manager, _, queues, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait_desktop():
        entered.set()
        await release.wait()

    qid = queues.add(QueueConfig, payload={"Info": {"Name": "queue"}})
    await queues.commit()
    queues[qid].QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queues[qid].QueueItem.commit()
    with patch("app.core.desktop_guard.ensure_desktop_available", wait_desktop):
        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
        run = manager.task_handler[uid]
        await asyncio.wait_for(entered.wait(), 3)
        queues.remove(qid)
        await queues.commit()
        release.set()
        await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "success"
    assert run.task_info.script_list[0].script_id == str(sid)
    assert qid not in queues
    assert run.task_info.info.name == "queue"


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
async def test_plugin_uses_current_configuration_and_protects_only_current_user(
    scheduler, remove
):
    manager, scripts, _, sid = scheduler
    first, second = list(scripts[sid].UserData.keys())
    entered, release = asyncio.Event(), asyncio.Event()
    observed = []

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            observed.append(self.user_config.Info.Name)
            if self.user_info.info.user_id == str(first):
                entered.set()
                await release.wait()
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(entered.wait(), 3)
    entry = scripts[sid]
    try:
        with pytest.raises(ConfigAggregateError):
            await entry.update(
                type(entry).model_validate({"Info": {"Name": "blocked"}}),
                check_visibility=False,
            )
        with pytest.raises(ConfigAggregateError):
            await entry.UserData[first].update(
                GeneralUserConfig.model_validate({"Info": {"Name": "blocked"}}),
                check_visibility=False,
            )
        if remove:
            entry.UserData.remove(second)
            await entry.UserData.commit()
        else:
            await entry.UserData[second].update(
                GeneralUserConfig.model_validate({"Info": {"Name": "changed"}}),
                check_visibility=False,
            )
    finally:
        release.set()
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert not entry.is_locked
    assert not entry.UserData[first].is_locked
    if remove:
        assert observed == ["first"]
        assert run.task_info.script_list[0].user_list[1].status == "异常"
    else:
        assert observed == ["first", "changed"]
        assert entry.UserData[second].Info.Name == "changed"
        assert run.task_info.status == "success"


@pytest.mark.asyncio
async def test_waiting_for_deleted_script_terminates_and_keeps_failure_node(scheduler):
    manager, scripts, _, sid = scheduler
    old = scripts[sid]
    ticket = await old.lock_x(cascade=False)

    class Expander(UserExpander):
        def build_worker(self, user, config):
            raise AssertionError("deleted script must not dispatch a user")

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    # 首次解析遇到外部票据后进入等待；删除必须先归还外部票据。
    for _ in range(50):
        if "等待托管配置" in run.task_info.script_list[0].log:
            break
        await asyncio.sleep(0.01)
    assert "等待托管配置" in run.task_info.script_list[0].log
    assert run.task_info.script_list[0].status == "等待"
    await old.unlock(ticket)
    scripts.remove(sid)
    await scripts.commit()
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "error"
    assert run.task_info.script_list[0].status == "异常"
    assert not manager.task_handler


@pytest.mark.asyncio
async def test_http_start_and_query_share_native_tree(scheduler):
    import httpx
    from fastapi import FastAPI

    import app.api.dispatch as routes

    manager, _, _, sid = scheduler
    app = FastAPI()
    app.include_router(routes.router)
    with patch.object(routes, "TaskManager", manager):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/dispatch/start",
                json={
                    "mode": "ScriptView",
                    "tasks": {
                        "0": {
                            "uid": str(sid),
                            "params": {"instance_idx": 2},
                            "children": {
                                "0": {"uid": "default", "params": {"value": None}}
                            },
                        }
                    },
                },
            )
            assert response.status_code == 200 and response.json()["code"] == 200
            task_id = response.json()["taskId"]
            result = await client.post("/api/dispatch/get", json={"taskId": task_id})
            assert result.json()["data"][task_id]["info"]["mode"] == "ScriptView"
            rejected = await client.post(
                "/api/dispatch/start",
                json={"mode": "ScriptConfig", "taskId": str(sid), "viewOnly": True},
            )
            assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_view_worker_holds_only_script_for_default_target(scheduler):
    manager, scripts, _, sid = scheduler
    count = len(scripts[sid].UserData)

    class Worker(ScriptViewWorker):
        async def main_logic(self):
            assert self.user_config is None
            assert self.expander.script_config.is_locked
            assert self.task_info.instance_idx == 2
            assert self.context.params == {"nullable": None}
            assert not any(user.is_locked for user in scripts[sid].UserData.values())
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    uid = await manager.start(
        TaskMode.SCRIPT_VIEW,
        {
            0: {
                "uid": str(sid),
                "params": {"instance_idx": 2},
                "children": {0: {"uid": "default", "params": {"nullable": None}}},
            }
        },
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "success"
    assert len(scripts[sid].UserData) == count
    assert not scripts[sid].is_locked


@pytest.mark.asyncio
async def test_user_commit_failure_releases_locks_and_continues(scheduler, monkeypatch):
    manager, scripts, _, sid = scheduler
    first = next(iter(scripts[sid].UserData.values()))
    commit = type(first).commit

    async def failing_commit(entry):
        if entry is first:
            raise RuntimeError("synthetic commit failure")
        await commit(entry)

    monkeypatch.setattr(type(first), "commit", failing_commit)
    seen = []

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            seen.append(self.user_info.info.user_id)
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert len(seen) == 2
    assert run.task_info.status == "error"
    assert not scripts[sid].is_locked and not first.is_locked


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_children", [False, True])
async def test_late_invalid_selection_publishes_no_partial_tree(
    scheduler, monkeypatch, invalid_children
):
    from app.core import Publisher

    manager, scripts, _, sid = scheduler
    first, second = scripts[sid].UserData.keys()
    invalid = (
        {"uid": str(second), "children": {0: {"uid": str(uuid4())}}}
        if invalid_children
        else {"uid": str(uuid4())}
    )
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    with pytest.raises(ValueError):
        await manager.start(
            TaskMode.AUTO_PROXY,
            {
                0: {
                    "uid": "-",
                    "children": {
                        0: {
                            "uid": str(sid),
                            "children": {0: {"uid": str(first)}, 1: invalid},
                        }
                    },
                }
            },
        )
    sent.assert_not_awaited()
    assert not manager._running and not manager._recent
    assert manager._creating == 0 and manager._idle.is_set()

    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert manager.get_task_status(str(uid)).status == "success"


@pytest.mark.asyncio
async def test_stop_all_blocks_new_requests_and_waits_for_inflight_creation(scheduler):
    from app.models.task import TaskItem

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()
    activate = TaskItem.activate

    async def delayed_activate(info, **kwargs):
        entered.set()
        await release.wait()
        await activate(info, **kwargs)

    with (
        patch.object(TaskItem, "activate", delayed_activate),
        patch("app.core.Power.cancel_power_task", AsyncMock()),
    ):
        creating = asyncio.create_task(
            manager.start(
                TaskMode.AUTO_PROXY,
                {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        stopping = asyncio.create_task(manager.stop("ALL"))
        await asyncio.sleep(0)
        try:
            with pytest.raises(RuntimeError):
                await manager.start(TaskMode.AUTO_PROXY, {})
            assert not stopping.done()
        finally:
            release.set()
        await asyncio.wait_for(creating, 3)
        await asyncio.wait_for(stopping, 3)
    assert not manager.task_handler
