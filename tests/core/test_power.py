"""电源倒计时期间拒绝启动新任务，取消后恢复受理。"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app import core
from app.core.ws import protocol
from app.models.task import TaskMode, TaskTriggerReason
from app.utils.contracts.power import PowerSignal
from tests.support.queue import make_queue
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_last_task_starts_countdown_which_blocks_new_work_until_cancelled(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    controller = core.Power
    entered, release = asyncio.Event(), asyncio.Event()
    from tests.support.scheduler import Builtin

    class Waiting(Builtin):
        async def main_task(self):
            entered.set()
            await release.wait()

    manager.manager_factories = {type(scheduler[1][sid]): Waiting}
    from app.api import dispatch

    monkeypatch.setattr(dispatch, "Power", controller)
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    assert (
        await dispatch.set_power(dispatch.PowerIn(signal=PowerSignal.SLEEP))
    ).code == 200
    start = AsyncMock(wraps=controller.start_power_task)
    monkeypatch.setattr(controller, "start_power_task", start)
    request = {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    first = await manager.start(TaskMode.AUTO_PROXY, request)
    await entered.wait()
    second = await manager.start(TaskMode.AUTO_PROXY, request)
    assert not manager.idle
    assert start.await_count == 0
    runs = list(manager._running.values())
    release.set()
    await asyncio.wait_for(asyncio.gather(*(r.accomplish.wait() for r in runs)), 2)
    assert start.await_count == 1
    assert manager.get_task(first) and manager.get_task(second)
    task = controller.power_task
    assert task is not None
    response = await dispatch.set_power(dispatch.PowerIn(signal=PowerSignal.SHUTDOWN))
    assert response.code == 409
    assert controller.power_task is task and not task.cancelling()
    _, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), startup="Always", timed=True
    )
    before = queue.model_dump(context={"audience": "persist"})
    recent = dict(manager._recent)
    core.Publisher.send.reset_mock()
    with pytest.raises(RuntimeError):
        await manager.start(
            TaskMode.AUTO_PROXY,
            {0: {"uid": str(queue.uid)}},
            trigger=TaskTriggerReason.TIMED,
        )
    assert not manager._running and manager._recent == recent
    assert queue.model_dump(context={"audience": "persist"}) == before
    assert controller.power_task is task and not task.cancelling()
    response = await dispatch.add_task(
        dispatch.TaskCreateIn.model_validate({"mode": "AutoProxy", "tasks": request})
    )
    assert response.code == 409 and response.taskId == ""
    assert not manager._running
    assert all(
        call.kwargs["type"] != protocol.TASK_CREATED
        for call in core.Publisher.send.await_args_list
    )
    assert (await dispatch.cancel_power_task()).code == 200
    assert task.done()
    assert controller.power_task is None
    uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(queue.uid)}})
    await asyncio.wait_for(manager.task_handler[uid].accomplish.wait(), 2)
