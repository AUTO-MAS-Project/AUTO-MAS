"""电源信号优先级、结束事件以及独立退出收尾的公共行为。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app import core
from app.core.lifecycle import _ShutdownCoordinator
from app.core.power import _PowerManager
from app.core.ws import protocol
from app.models.task import TaskMode
from tests.core.test_maintenance_cycle_review import make_queue
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest_asyncio.fixture
async def controller(monkeypatch):
    instance = _PowerManager()
    monkeypatch.setattr(core, "Power", instance)
    monkeypatch.setattr(core.Publisher, "send", AsyncMock(return_value=False))
    yield instance
    if instance.power_task is not None and not instance.power_task.done():
        instance.power_task.cancel()
        await asyncio.gather(instance.power_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_signal_overwrite_applies_only_before_a_power_task_exists(controller):
    assert await controller.set_signal("Sleep", overwrite=False, delay=15)
    assert not await controller.set_signal("Shutdown", overwrite=False)
    assert (controller.signal, controller.delay) == ("Sleep", 15)
    assert await controller.set_signal("Hibernate", overwrite=True)
    assert (controller.signal, controller.delay) == ("Hibernate", 0)
    assert await controller.start_power_task()
    task = controller.power_task
    assert not await controller.set_signal("Reboot", overwrite=True)
    assert not await controller.start_power_task()
    assert controller.power_task is task
    assert await controller.cancel_power_task()
    assert await controller.set_signal("NoAction", overwrite=True)


@pytest.mark.asyncio
async def test_api_reports_rejected_overwrite_without_cancelling_countdown(
    controller, monkeypatch
):
    from app.api import dispatch

    monkeypatch.setattr(dispatch, "Power", controller)
    assert (await dispatch.set_power(dispatch.PowerIn(signal="Sleep"))).code == 200
    await controller.start_power_task()
    task = controller.power_task
    response = await dispatch.set_power(dispatch.PowerIn(signal="Shutdown"))
    assert response.code == 409
    assert controller.power_task is task and not task.cancelling()
    assert (await dispatch.cancel_power_task()).code == 200
    assert task.done()


@pytest.mark.asyncio
async def test_queue_signal_precedes_completion_and_power_sees_unregistered_task(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    controller = core.Power
    qid, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), cycle=False
    )
    queue.Info.AfterAccomplish = "Shutdown"
    await queue.commit()
    seen = []

    async def send(**kwargs):
        if kwargs["type"] == protocol.TASK_COMPLETED:
            seen.append(("completed", controller.signal))
        return True

    async def start():
        seen.append(("power", manager.idle))
        return True

    monkeypatch.setattr(core.Publisher, "send", send)
    monkeypatch.setattr(controller, "start_power_task", start)
    uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 2)
    assert seen == [("completed", "Shutdown"), ("power", True)]


@pytest.mark.asyncio
async def test_busy_scheduler_skips_power_until_the_last_task_ends(
    scheduler, monkeypatch
):
    manager, _, _, sid = scheduler
    controller = core.Power
    entered, release = asyncio.Event(), asyncio.Event()
    from tests.core.test_task_tree_dispatch import Builtin

    class Waiting(Builtin):
        async def main_task(self):
            entered.set()
            await release.wait()

    manager.manager_factories = {type(scheduler[1][sid]): Waiting}
    await controller.set_signal("Sleep", overwrite=True)
    start = AsyncMock(return_value=True)
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


@pytest.mark.asyncio
async def test_native_action_precedes_independent_exit_and_background_cleanup(
    controller, monkeypatch
):
    from app.core import power as power_module
    from app.core.background_tasks import BackgroundTaskRegistry

    owner = _ShutdownCoordinator()
    registry = BackgroundTaskRegistry()
    group = registry.register_group("maintenance", max_running=1, max_retained=1)
    entered = asyncio.Event()
    events = []

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("background cleaned")

    handle = group.spawn(work)
    await entered.wait()

    async def teardown():
        events.append("teardown")
        # 宿主收尾仍会撤销电源；已交接的操作不会取消发起者或等待自身。
        assert not await controller.cancel_power_task()
        assert await registry.shutdown(timeout=2)

    async def execute(action):
        events.append(action)
        assert not handle.done()

    owner.set_teardown(teardown)
    monkeypatch.setattr(core, "ShutdownCoordinator", owner)
    monkeypatch.setattr(
        core,
        "EmulatorManager",
        SimpleNamespace(
            close_running_avd_instances=AsyncMock(), kill_emulator_processes=AsyncMock()
        ),
    )
    monkeypatch.setattr(
        power_module,
        "power",
        SimpleNamespace(supported_actions={"Shutdown"}, execute=execute),
    )
    monkeypatch.setattr(core.Config, "server", SimpleNamespace(should_exit=False))
    controller.countdown = 0
    await controller.set_signal("Shutdown", overwrite=True)
    await controller.start_power_task()
    await asyncio.wait_for(controller.power_task, 2)
    await asyncio.wait_for(owner._exit_task, 2)
    assert events == ["Shutdown", "teardown", "background cleaned"]
    assert core.Config.server.should_exit
    assert handle.done()


@pytest.mark.asyncio
async def test_cancelling_countdown_leaves_background_work_running(controller):
    from app.core.background_tasks import BackgroundTaskRegistry

    registry = BackgroundTaskRegistry()
    group = registry.register_group("working", max_running=1, max_retained=1)
    entered, release = asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        await release.wait()

    handle = group.spawn(work)
    await entered.wait()
    await controller.set_signal("Sleep", overwrite=True, delay=60)
    await controller.start_power_task()
    await controller.cancel_power_task()
    assert not handle.done()
    release.set()
    assert await registry.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_failed_native_action_does_not_request_exit(controller, monkeypatch):
    from app.core import power as power_module

    request = AsyncMock()
    monkeypatch.setattr(core.ShutdownCoordinator, "request_exit", request)
    monkeypatch.setattr(
        power_module,
        "power",
        SimpleNamespace(
            supported_actions={"Sleep"},
            execute=AsyncMock(side_effect=OSError("denied")),
        ),
    )
    with pytest.raises(OSError):
        await controller.set_power("Sleep")
    request.assert_not_called()
    assert not controller.active
