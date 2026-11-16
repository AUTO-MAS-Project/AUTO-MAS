"""任务创建、信息树身份与内建/插件分流的隔离回归。"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.models.config import (
    GeneralConfig,
    QueueConfig,
    QueueItem,
)
from app.models.task import TaskMode
from tests.support.scheduler import Builtin
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_repeated_queue_items_run_in_order_with_independent_identity(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    qid = queues.add(QueueConfig, payload={"Info": {"Name": "queue"}})
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
    assert run.task_info.status == "success", (
        run.error,
        [(s.status, s.log) for s in run.task_info.script_list],
    )
    scripts = run.task_info.script_list
    assert calls == [0, 1, 2]
    assert len(scripts) == 3 and len({script.uid for script in scripts}) == 3


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
