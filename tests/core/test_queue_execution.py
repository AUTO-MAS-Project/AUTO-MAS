"""队列附加动作沿 L1 快照执行，取消仍通过顶层调度入口传播。"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.task import TaskMode
from app.utils.contracts.power import PowerSignal
from tests.core.test_maintenance_cycle_review import make_queue
from tests.core.test_task_tree_dispatch import Builtin
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_power", [PowerSignal.NO_ACTION, PowerSignal.SLEEP])
async def test_queue_actions_use_accepted_snapshot_after_queue_is_deleted(
    scheduler, tmp_path, monkeypatch, existing_power
):
    from app.core import Power

    manager, _, queues, sid = scheduler
    qid, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), cycle=False
    )
    before, after = tmp_path / "before.cmd", tmp_path / "after.cmd"
    before.touch()
    after.touch()
    queue.Info.IfScriptBeforeTask = queue.Info.IfScriptAfterTask = True
    queue.Info.ScriptBeforeTask, queue.Info.ScriptAfterTask = before, after
    queue.Info.AfterAccomplish = PowerSignal.SHUTDOWN
    queue.Info.AfterAccomplishDelay = 2
    await queue.commit()
    monkeypatch.setattr(Power, "signal", existing_power)
    monkeypatch.setattr(Power, "delay", 0)
    events = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(path, label):
        events.append(path.name)
        if path == before:
            entered.set()
            await release.wait()
        return True

    async def run(self):
        events.append("script")
        await Builtin.main_task(self)

    # 模拟系统电源和脚本进程边界，实际走 L1 建树、L2 派发和 ended 收口。
    class Running(Builtin):
        main_task = run

    manager.manager_factories = {type(scheduler[1][sid]): Running}
    with (
        patch("app.task.script_expander.execute_script_task", new=execute, create=True),
        patch("app.core.Power.start_power_task", new=AsyncMock()) as power,
    ):
        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
        task = manager.task_handler[uid]
        try:
            await asyncio.wait_for(entered.wait(), 2)
            tree = manager.get_task(uid)
            assert tree["execution"]["script_before"] == str(before)
            assert task.task_info.get_update()["execution"] == tree["execution"]
            queue.Info.ScriptAfterTask = before
            queue.Info.AfterAccomplish = PowerSignal.REBOOT
            await queue.commit()
            queues.remove(qid)
            await queues.commit()
            release.set()
            await asyncio.wait_for(task.accomplish.wait(), 2)
            assert events == ["before.cmd", "script", "after.cmd"]
            assert Power.signal == (
                PowerSignal.SHUTDOWN
                if existing_power == PowerSignal.NO_ACTION
                else existing_power
            )
            assert Power.delay == (
                120 if existing_power == PowerSignal.NO_ACTION else 0
            )
            power.assert_awaited_once()
            assert task.task_info.status == "success"
            assert qid not in queues
        finally:
            release.set()
            await manager.stop(uid)
            Power.signal = PowerSignal.NO_ACTION


@pytest.mark.asyncio
async def test_extra_script_failure_warns_and_continues_normal_task(
    scheduler, tmp_path
):
    from app.core import Publisher
    from app.core.ws import protocol

    manager, _, queues, sid = scheduler
    qid, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), cycle=False
    )
    path = tmp_path / "failed.cmd"
    path.touch()
    queue.Info.IfScriptBeforeTask = queue.Info.IfScriptAfterTask = True
    queue.Info.ScriptBeforeTask = queue.Info.ScriptAfterTask = path
    await queue.commit()
    with patch(
        "app.task.script_expander.execute_script_task",
        new=AsyncMock(return_value=False),
    ) as execute:
        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
        task = manager.task_handler[uid]
        await asyncio.wait_for(task.accomplish.wait(), 2)
    assert execute.await_count == 2
    assert task.task_info.script_list[0].status == "完成"
    warnings = [
        call.kwargs["data"]
        for call in Publisher.send.await_args_list
        if call.kwargs["type"] == protocol.TASK_NOTICE
        and call.kwargs["data"].level == "warning"
    ]
    assert len(warnings) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["before", "after"])
async def test_stop_cancels_queue_script_without_scheduling_power(
    scheduler, tmp_path, monkeypatch, stage
):
    from app.core import Power

    manager, _, queues, sid = scheduler
    qid, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), cycle=False
    )
    script = tmp_path / "action.cmd"
    script.touch()
    queue.Info.IfScriptBeforeTask = stage == "before"
    queue.Info.IfScriptAfterTask = stage == "after"
    queue.Info.ScriptBeforeTask = queue.Info.ScriptAfterTask = script
    queue.Info.AfterAccomplish = PowerSignal.SHUTDOWN
    await queue.commit()
    monkeypatch.setattr(Power, "signal", PowerSignal.NO_ACTION)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def execute(path, label):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with (
        patch("app.task.script_expander.execute_script_task", new=execute, create=True),
        patch("app.core.Power.start_power_task", new=AsyncMock()) as power,
    ):
        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(manager.stop(uid), 2)
            assert cancelled.is_set()
            assert manager.get_task_status(str(uid)).status == "cancelled"
            assert Power.signal == PowerSignal.NO_ACTION
            power.assert_not_awaited()
        finally:
            await manager.stop(uid)
