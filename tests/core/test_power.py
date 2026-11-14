"""电源信号优先级、结束事件以及独立退出收尾的公共行为。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from app import core
from app.core.lifecycle import _ShutdownCoordinator
from app.core.power import _PowerManager
from app.core.ws import protocol
from app.models.task import TaskMode, TaskTriggerReason
from app.utils.contracts.power import PowerSignal
from tests.core.test_maintenance_cycle_review import make_queue
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.parametrize(
    ("wire", "signal"),
    [
        ("NoAction", PowerSignal.NO_ACTION),
        ("Shutdown", PowerSignal.SHUTDOWN),
        ("ShutdownForce", PowerSignal.SHUTDOWN_FORCE),
        ("Reboot", PowerSignal.REBOOT),
        ("Hibernate", PowerSignal.HIBERNATE),
        ("Sleep", PowerSignal.SLEEP),
        ("KillSelf", PowerSignal.KILL_SELF),
        ("RestartSelf", PowerSignal.RESTART_SELF),
        ("Logoff", PowerSignal.LOGOFF),
    ],
)
def test_power_contract_uses_enum_and_keeps_wire_values(wire, signal):
    from app.api.dispatch import PowerIn, PowerOut
    from app.models.config import QueueConfig
    from app.models.schema import WSPowerCountdownData, WSPowerSignData
    from app.models.task import TaskItem

    request = PowerIn.model_validate({"signal": wire})
    assert request.signal is signal
    assert request.model_dump(mode="json") == {"signal": wire}
    assert PowerOut(signal=signal).model_dump(mode="json")["signal"] == wire
    assert (
        QueueConfig.InfoFields.model_validate({"AfterAccomplish": wire}).AfterAccomplish
        is signal
    )
    assert (
        TaskItem.Execution.model_validate({"after_accomplish": wire}).after_accomplish
        is signal
    )
    assert WSPowerSignData(signal=signal).model_dump(mode="json") == {"signal": wire}
    assert WSPowerCountdownData(operation=signal, remaining=1).model_dump(
        mode="json"
    ) == {
        "operation": wire,
        "remaining": 1,
    }


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
@pytest.mark.parametrize("delay", [None, 300, 0])
async def test_power_uses_one_countdown_with_a_sixty_second_default(
    controller, monkeypatch, delay
):
    from app.core import power as power_module

    sleeps = AsyncMock()
    execute = AsyncMock()
    monkeypatch.setattr(power_module.asyncio, "sleep", sleeps)
    monkeypatch.setattr(controller, "set_power", execute)
    if delay is None:
        await controller.set_signal(PowerSignal.SLEEP, overwrite=True)
    else:
        await controller.set_signal(PowerSignal.SLEEP, overwrite=True, delay=delay)
    expected = 60 if delay is None else delay
    assert controller.delay == expected
    await controller.start_power_task()
    await controller.power_task
    remaining = [
        call.kwargs["data"].remaining
        for call in core.Publisher.send.await_args_list
        if call.kwargs["type"] == protocol.POWER_COUNTDOWN_UPDATED
    ]
    assert remaining == list(range(expected, 0, -1))
    assert [call.args for call in sleeps.await_args_list] == [(1,)] * expected
    execute.assert_awaited_once_with(PowerSignal.SLEEP)


@pytest.mark.asyncio
async def test_signal_overwrite_applies_only_before_a_power_task_exists(controller):
    assert await controller.set_signal(PowerSignal.SLEEP, overwrite=False, delay=15)
    assert not await controller.set_signal(PowerSignal.SHUTDOWN, overwrite=False)
    assert (controller.signal, controller.delay) == (PowerSignal.SLEEP, 15)
    assert await controller.set_signal(PowerSignal.HIBERNATE, overwrite=True)
    assert (controller.signal, controller.delay) == (PowerSignal.HIBERNATE, 60)
    assert await controller.start_power_task()
    task = controller.power_task
    assert not await controller.set_signal(PowerSignal.REBOOT, overwrite=True)
    assert not await controller.start_power_task()
    assert controller.power_task is task
    await controller.cancel_power_task()
    assert controller.power_task is None
    assert await controller.set_signal(PowerSignal.NO_ACTION, overwrite=True)


@pytest.mark.asyncio
async def test_api_reports_rejected_overwrite_without_cancelling_countdown(
    controller, monkeypatch
):
    from app.api import dispatch

    monkeypatch.setattr(dispatch, "Power", controller)
    assert (
        await dispatch.set_power(dispatch.PowerIn(signal=PowerSignal.SLEEP))
    ).code == 200
    await controller.start_power_task()
    task = controller.power_task
    response = await dispatch.set_power(dispatch.PowerIn(signal=PowerSignal.SHUTDOWN))
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
    queue.Info.AfterAccomplish = PowerSignal.SHUTDOWN
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
    assert seen == [("completed", PowerSignal.SHUTDOWN), ("power", True)]


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
    await controller.set_signal(PowerSignal.SLEEP, overwrite=True)
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
        # 电源协程已完成，宿主独立收尾不等待自身。
        await controller.cancel_power_task()
        assert await registry.shutdown(timeout=2)

    async def execute(action):
        assert isinstance(action, PowerSignal)
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
        SimpleNamespace(supported_actions={PowerSignal.SHUTDOWN}, execute=execute),
    )
    monkeypatch.setattr(core.Config, "server", SimpleNamespace(should_exit=False))
    await controller.set_signal(PowerSignal.SHUTDOWN, overwrite=True, delay=0)
    await controller.start_power_task()
    await asyncio.wait_for(controller.power_task, 2)
    await asyncio.wait_for(owner._exit_task, 2)
    assert events == [PowerSignal.SHUTDOWN, "teardown", "background cleaned"]
    assert core.Config.server.should_exit
    assert handle.done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("signal", "exits"),
    [
        (PowerSignal.SHUTDOWN, True),
        (PowerSignal.SHUTDOWN_FORCE, True),
        (PowerSignal.REBOOT, True),
        (PowerSignal.LOGOFF, True),
        (PowerSignal.KILL_SELF, True),
        (PowerSignal.RESTART_SELF, True),
        (PowerSignal.SLEEP, False),
        (PowerSignal.HIBERNATE, False),
    ],
)
async def test_only_session_ending_actions_request_application_exit(
    controller, monkeypatch, signal, exits
):
    from app.core import power as power_module

    request_exit = Mock()
    execute = AsyncMock()
    monkeypatch.setattr(
        core, "ShutdownCoordinator", SimpleNamespace(request_exit=request_exit)
    )
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
        SimpleNamespace(supported_actions=frozenset(PowerSignal), execute=execute),
    )
    await controller.set_power(signal)
    if signal in {PowerSignal.KILL_SELF, PowerSignal.RESTART_SELF}:
        execute.assert_not_awaited()
    else:
        execute.assert_awaited_once_with(signal)
    if exits:
        request_exit.assert_called_once_with(restart=signal == PowerSignal.RESTART_SELF)
    else:
        request_exit.assert_not_called()


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
    await controller.set_signal(PowerSignal.SLEEP, overwrite=True, delay=60)
    await controller.start_power_task()
    await controller.cancel_power_task()
    assert not handle.done()
    release.set()
    assert await registry.shutdown(timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [*TaskTriggerReason, "config", "maintenance"])
async def test_countdown_ends_new_requests_before_registration_or_clock_updates(
    scheduler, kind
):
    manager, _, queues, sid = scheduler
    _, queue = await make_queue(
        queues, sid, now=datetime.now().astimezone(), startup="Always", timed=True
    )
    before = queue.model_dump(context={"audience": "persist"})
    await core.Power.set_signal(PowerSignal.SLEEP, overwrite=True)
    await core.Power.start_power_task()
    power_task = core.Power.power_task
    with pytest.raises(RuntimeError):
        if kind == "maintenance":
            await manager.start_maintenance(str(sid))
        elif kind == "config":
            await manager.start(TaskMode.SCRIPT_CONFIG, {0: {"uid": str(sid)}})
        else:
            await manager.start(
                TaskMode.AUTO_PROXY, {0: {"uid": str(queue.uid)}}, trigger=kind
            )
    assert not manager._running and not manager._recent
    assert queue.model_dump(context={"audience": "persist"}) == before
    assert core.Power.power_task is power_task and not power_task.cancelling()
    assert all(
        call.kwargs["type"] != protocol.TASK_CREATED
        for call in core.Publisher.send.await_args_list
    )
    await core.Power.cancel_power_task()
    assert core.Power.power_task is None
    uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(queue.uid)}})
    await manager.task_handler[uid].accomplish.wait()


@pytest.mark.asyncio
async def test_creation_api_reports_busy_during_countdown(scheduler, monkeypatch):
    from app.api import dispatch

    manager, _, _, sid = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    await core.Power.set_signal(PowerSignal.SLEEP, overwrite=True)
    await core.Power.start_power_task()
    response = await dispatch.add_task(
        dispatch.TaskCreateIn.model_validate(
            {
                "mode": "AutoProxy",
                "tasks": {"0": {"uid": "-", "children": {"0": {"uid": str(sid)}}}},
            }
        )
    )
    assert response.code == 409 and response.taskId == ""
    assert not manager._running


@pytest.mark.asyncio
async def test_repeated_cancellation_clears_the_handle_and_publishes_once(controller):
    await controller.set_signal(PowerSignal.SLEEP, overwrite=True)
    await controller.start_power_task()
    task = controller.power_task
    await asyncio.gather(controller.cancel_power_task(), controller.cancel_power_task())
    assert task.done() and controller.power_task is None
    assert (
        sum(
            call.kwargs["type"] == protocol.POWER_COUNTDOWN_CANCELLED
            for call in core.Publisher.send.await_args_list
        )
        == 1
    )


@pytest.mark.asyncio
async def test_failed_power_task_clears_the_only_handle(controller, monkeypatch):
    monkeypatch.setattr(
        controller, "set_power", AsyncMock(side_effect=OSError("denied"))
    )
    await controller.set_signal(PowerSignal.SLEEP, overwrite=True, delay=0)
    await controller.start_power_task()
    task = controller.power_task
    with pytest.raises(OSError):
        await task
    assert controller.power_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize("wakeup_enabled", [False, True])
@pytest.mark.parametrize("signal", [PowerSignal.SLEEP, PowerSignal.HIBERNATE])
async def test_started_power_does_not_yield_to_pending_schedules(
    scheduler, monkeypatch, wakeup_enabled, signal
):
    from app.core import power as power_module
    from app.core.timer import _MainTimer
    from app.models.config import GlobalConfig
    from tests.config_support import activate_config

    _, _, queues, sid = scheduler
    now = datetime.now().astimezone()
    await make_queue(queues, sid, now=now, timed=True, cycle=False)
    setting = await activate_config(
        GlobalConfig.model_validate(
            {
                "Start": {"IfScheduledWakeUp": wakeup_enabled},
            }
        )
    )
    monkeypatch.setattr(core.Config, "setting", setting)
    assert _MainTimer().has_pending_wakeup_schedule(now) is wakeup_enabled
    execute = AsyncMock()
    owner = _ShutdownCoordinator()
    owner.set_teardown(AsyncMock())
    monkeypatch.setattr(core, "ShutdownCoordinator", owner)
    monkeypatch.setattr(core.Config, "server", SimpleNamespace(should_exit=False))
    monkeypatch.setattr(core, "EmulatorManager", SimpleNamespace())
    monkeypatch.setattr(
        power_module,
        "power",
        SimpleNamespace(
            supported_actions={signal},
            execute=execute,
        ),
    )
    await core.Power.set_signal(signal, overwrite=True, delay=0)
    await core.Power.start_power_task()
    task = core.Power.power_task
    await task
    assert owner._exit_task is None
    assert not core.Config.server.should_exit
    execute.assert_awaited_once_with(signal)
    assert core.Power.power_task is None
    assert not core.Power.get_power_countdown_snapshot().active
