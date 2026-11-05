"""相邻定时之间保持调度可用；测试始终隔离系统电源与前端关闭边界。"""

import asyncio
from datetime import datetime, timedelta

import pytest
from uvicorn import Config as ServerConfig
from uvicorn import Server

from app.config import ConfigCollection
from app.models.config import GlobalConfig, QueueConfig
from app.models.config.queue import TimeSet
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,second",
    [("Sleep", 0), ("Hibernate", 0), ("KillSelf", 0), ("Sleep", 30), ("Shutdown", 0)],
)
async def test_finished_queue_preserves_next_woken_schedule(
    isolated_app_paths, monkeypatch, operation, second
):
    from app.core import Publisher, TaskManager, timer
    from app.core.ws import protocol
    from app.services.common import system
    from app.services.windows.power import WindowsPowerController

    planned = datetime(2026, 11, 2, 8, 6, second).astimezone()
    # 系统唤醒按分钟注册，导入的定时即使带秒也已在 08:01:00 唤醒。
    now = planned.replace(second=0) - timedelta(minutes=5) + timedelta(seconds=10)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(system, "datetime", Clock)
    setting = await activate_config(
        GlobalConfig.model_validate({"Start": {"IfScheduledWakeUp": True}})
    )
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    uid = queues.add(QueueConfig, payload={"Info": {"TimeEnabled": True}})
    await queues.commit()
    queue = queues[uid]
    queue.TimeSet.add(TimeSet, payload={"Info": {"Time": planned, "Days": ["Monday"]}})
    await queue.TimeSet.commit()
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "QueueConfig", queues)
    monkeypatch.setattr(TaskManager, "task_handler", {})
    server = Server(ServerConfig("app.api:app"))
    monkeypatch.setattr(isolated_app_paths, "server", server)
    native_operations = []
    events = []

    async def execute(action):
        native_operations.append(action)

    async def send(**kwargs):
        events.append(kwargs["type"])
        return kwargs["type"] != protocol.FRONTEND_CLOSE_REQUESTED

    # CI 的 Linux 宿主也验证 Windows 调度契约，只替换真正的系统电源调用。
    monkeypatch.setattr(system, "power", WindowsPowerController())
    monkeypatch.setattr(system.power, "execute", execute)
    monkeypatch.setattr(Publisher, "send", send)
    handler = system._SystemHandler()
    if operation == "Shutdown":
        wake_at = planned - timedelta(minutes=5)
        now = wake_at - timedelta(seconds=1)

        async def close_avd():
            nonlocal now
            now = max(now, wake_at + timedelta(seconds=10))

        handler.avd_instance_closer = close_avd
        monkeypatch.setattr(
            system.psutil, "process_iter", lambda *args, **kwargs: iter(())
        )
    # 冻结在前一队列的倒计时结束时刻，测试不等待真实的一分钟。
    handler.countdown = 0
    monkeypatch.setattr(isolated_app_paths, "power_sign", operation)
    monkeypatch.setattr(isolated_app_paths, "power_delay", 0)
    await handler.start_power_task()
    await handler.power_task
    assert native_operations == []
    assert not server.should_exit
    assert protocol.POWER_COUNTDOWN_CANCELLED in events

    # 用户直接选择睡眠、休眠或退出时保留意图，不复用自动完成后的避让。
    await handler.set_power(operation, from_frontend=True)
    expected_native = [] if operation == "KillSelf" else [operation]
    assert native_operations == expected_native
    assert server.should_exit == (operation == "KillSelf")
    server.should_exit = False

    dispatched = []

    async def receive_task(mode, queue_id, **kwargs):
        dispatched.append((queue_id, kwargs["trigger_source"]))

    monkeypatch.setattr(timer.TaskManager, "add_task", receive_task)
    monkeypatch.setattr(timer, "_local_now", lambda: now)
    main_timer = timer._MainTimer()
    await main_timer.timed_start()
    now = planned
    await main_timer.timed_start()
    assert dispatched == [(str(uid), "scheduled_task")]
    # 定时已派发后再结束队列，原有自动电源操作仍能执行。
    isolated_app_paths.power_sign = operation
    await handler.start_power_task()
    await handler.power_task
    assert native_operations == expected_native * 2
    assert server.should_exit == (operation == "KillSelf")


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [True, False])
async def test_exit_hands_next_wakeup_to_the_frontend(
    isolated_app_paths, monkeypatch, automatic
):
    from app.core import Publisher, TaskManager
    from app.core.ws import protocol
    from app.services.common import system

    planned = datetime(2026, 11, 2, 8, 6, 30).astimezone()
    wake_at = planned.replace(second=0) - timedelta(minutes=5)
    checked_at = wake_at - timedelta(seconds=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                checked_at.astimezone(tz)
                if tz is not None
                else checked_at.replace(tzinfo=None)
            )

    monkeypatch.setattr(system, "datetime", Clock)
    setting = await activate_config(
        GlobalConfig.model_validate({"Start": {"IfScheduledWakeUp": True}})
    )
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    uid = queues.add(QueueConfig, payload={"Info": {"TimeEnabled": True}})
    await queues.commit()
    queues[uid].TimeSet.add(
        TimeSet, payload={"Info": {"Time": planned, "Days": ["Monday"]}}
    )
    await queues[uid].TimeSet.commit()
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "QueueConfig", queues)
    monkeypatch.setattr(
        isolated_app_paths, "server", Server(ServerConfig("app.api:app"))
    )
    monkeypatch.setattr(TaskManager, "task_handler", {})
    requests = []

    async def send(**kwargs):
        if kwargs["type"] == protocol.FRONTEND_CLOSE_REQUESTED:
            requests.append(kwargs.get("data"))
        return False

    monkeypatch.setattr(Publisher, "send", send)
    await system._SystemHandler().set_power("KillSelf", automatic=automatic)
    assert len(requests) == 1
    assert requests[0] is not None
    data = requests[0].model_dump(mode="json")
    assert data["automatic"] == automatic
    if automatic:
        assert datetime.fromisoformat(data["nextWakeAt"]) == wake_at
    else:
        assert data["nextWakeAt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_latest", [False, True])
async def test_finished_queue_hands_over_a_retiring_power_task(
    isolated_app_paths, monkeypatch, cancel_latest
):
    from app.core import Publisher, TaskManager
    from app.core.ws import protocol
    from app.services.common import system
    from app.services.windows.power import WindowsPowerController

    setting = await activate_config(
        GlobalConfig.model_validate({"Start": {"IfScheduledWakeUp": True}})
    )
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "QueueConfig", queues)
    # 旧操作检查时，后一个队列尚在完成收尾；只观察真实调度器的任务集合边界。
    active = {"finishing_queue": object()}
    monkeypatch.setattr(TaskManager, "task_handler", active)
    monkeypatch.setattr(system, "power", WindowsPowerController())
    cancellation_started = asyncio.Event()
    release_cancellation = asyncio.Event()
    latest_ready = asyncio.Event()
    release_latest = asyncio.Event()
    operations = []

    async def send(**kwargs):
        if kwargs["type"] == protocol.POWER_COUNTDOWN_CANCELLED:
            cancellation_started.set()
            await release_cancellation.wait()
        return True

    async def execute(action):
        operations.append(action)

    async def before_latest():
        latest_ready.set()
        await release_latest.wait()
        return True

    monkeypatch.setattr(Publisher, "send", send)
    monkeypatch.setattr(system.power, "execute", execute)
    handler = system._SystemHandler()
    handler.countdown = 0
    monkeypatch.setattr(isolated_app_paths, "power_sign", "Sleep")
    monkeypatch.setattr(isolated_app_paths, "power_delay", 0)
    await handler.start_power_task()
    await asyncio.wait_for(cancellation_started.wait(), timeout=1)

    # B 写入完成后意图、移出任务集合，再从同一个服务入口请求电源操作。
    isolated_app_paths.power_sign = "Hibernate"
    active.clear()
    handoff = asyncio.create_task(handler.start_power_task(before_power=before_latest))
    try:
        await asyncio.sleep(0)
        release_cancellation.set()
        await asyncio.wait_for(handoff, timeout=1)
        if cancel_latest:
            await asyncio.wait_for(latest_ready.wait(), timeout=1)
            await handler.cancel_power_task()
        else:
            release_latest.set()
            await asyncio.wait_for(handler.power_task, timeout=1)
        assert operations == ([] if cancel_latest else ["Hibernate"])
        assert isolated_app_paths.power_sign == "NoAction"
    finally:
        release_cancellation.set()
        release_latest.set()
        if not handoff.done():
            handoff.cancel()
        if handler.power_task is not None and not handler.power_task.done():
            handler.power_task.cancel()
        await asyncio.gather(handoff, handler.power_task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "select"])
async def test_user_choice_during_power_handoff(
    isolated_app_paths, monkeypatch, action
):
    from app.api import dispatch
    from app.core import Publisher
    from app.core.ws import protocol
    from app.services.common import system
    from app.services.windows.power import WindowsPowerController

    setting = await activate_config(GlobalConfig())
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "power_sign", "Sleep")
    monkeypatch.setattr(isolated_app_paths, "power_delay", 0)
    monkeypatch.setattr(system, "power", WindowsPowerController())
    started = asyncio.Event()
    cancellation_started = asyncio.Event()
    release_cancellation = asyncio.Event()
    operations = []

    async def send(**kwargs):
        if kwargs["type"] == protocol.POWER_COUNTDOWN_UPDATED:
            started.set()
            await asyncio.Event().wait()
        elif kwargs["type"] == protocol.POWER_COUNTDOWN_CANCELLED:
            cancellation_started.set()
            await release_cancellation.wait()
        return True

    async def execute(operation):
        operations.append(operation)

    monkeypatch.setattr(Publisher, "send", send)
    monkeypatch.setattr(system.power, "execute", execute)
    handler = system._SystemHandler()
    monkeypatch.setattr(dispatch, "System", handler)
    await handler.start_power_task()
    await asyncio.wait_for(started.wait(), timeout=1)
    isolated_app_paths.power_sign = "Hibernate"
    handoff = asyncio.create_task(handler.start_power_task())
    await asyncio.wait_for(cancellation_started.wait(), timeout=1)
    # 经真实 API 入口取消或改选。相同操作的改选也必须留给下次队列完成。
    request = asyncio.create_task(
        dispatch.cancel_power_task()
        if action == "cancel"
        else dispatch.set_power(dispatch.PowerIn(signal="Hibernate"))
    )
    try:
        await asyncio.sleep(0)
        release_cancellation.set()
        await asyncio.wait_for(handoff, timeout=1)
        result = await asyncio.wait_for(request, timeout=1)
        assert result.status == "success"
        assert operations == []
        assert isolated_app_paths.power_sign == (
            "NoAction" if action == "cancel" else "Hibernate"
        )
        assert not handler.get_power_countdown_snapshot().active
    finally:
        release_cancellation.set()
        if handler.power_task is not None and not handler.power_task.done():
            handler.power_task.cancel()
        for pending in (handoff, request):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(
            handoff, request, handler.power_task, return_exceptions=True
        )
