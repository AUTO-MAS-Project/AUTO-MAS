"""相邻定时之间保持调度可用；测试始终隔离系统电源与前端关闭边界。"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from uvicorn import Config as ServerConfig
from uvicorn import Server

from app.config import ConfigCollection
from app.models.config import GlobalConfig, QueueConfig
from app.models.config.queue import TimeSet
from tests.config_support import activate_config


@pytest_asyncio.fixture(autouse=True)
async def exit_owner(monkeypatch):
    from app import core
    from app.core.lifecycle import _ShutdownCoordinator

    owner = _ShutdownCoordinator()
    owner.set_teardown(AsyncMock())
    monkeypatch.setattr(core, "ShutdownCoordinator", owner)
    monkeypatch.setattr(
        core,
        "EmulatorManager",
        SimpleNamespace(
            close_running_avd_instances=AsyncMock(), kill_emulator_processes=AsyncMock()
        ),
    )
    yield owner
    if owner._exit_task is not None:
        await owner._exit_task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,second",
    [("Sleep", 0), ("Hibernate", 0), ("KillSelf", 0), ("Sleep", 30), ("Shutdown", 0)],
)
async def test_finished_queue_preserves_next_woken_schedule(
    isolated_app_paths, monkeypatch, operation, second, exit_owner
):
    from app import core
    from app.core import Publisher, TaskManager, timer
    from app.core import power as system
    from app.core.ws import protocol
    from app.utils.windows.power import WindowsPowerController

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
    monkeypatch.setattr(TaskManager, "_running", {})
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
    handler = system._PowerManager()
    if operation == "Shutdown":
        wake_at = planned - timedelta(minutes=5)
        now = wake_at - timedelta(seconds=1)

        async def close_avd():
            nonlocal now
            now = max(now, wake_at + timedelta(seconds=10))

        monkeypatch.setattr(
            core.EmulatorManager, "close_running_avd_instances", close_avd
        )
        monkeypatch.setattr(
            core.EmulatorManager, "kill_emulator_processes", AsyncMock()
        )
    # 冻结在前一队列的倒计时结束时刻，测试不等待真实的一分钟。
    handler.countdown = 0
    monkeypatch.setattr(handler, "signal", operation)
    monkeypatch.setattr(handler, "delay", 0)
    await handler.start_power_task()
    await handler.power_task
    assert native_operations == []
    assert not server.should_exit
    assert protocol.POWER_COUNTDOWN_CANCELLED in events

    # 用户直接选择睡眠、休眠或退出时保留意图，不复用自动完成后的避让。
    await handler.set_power(operation, from_frontend=True)
    expected_native = [] if operation == "KillSelf" else [operation]
    assert native_operations == expected_native
    await exit_owner._exit_task
    assert server.should_exit
    server.should_exit = False
    handler = system._PowerManager()
    handler.countdown = 0

    dispatched = []

    async def receive_task(mode, tasks, **kwargs):
        dispatched.append((tasks[0]["uid"], kwargs["trigger"].value))
        queue.Data.LastStartTime = now
        queue.Data.LastTimedStart = now
        await queue.commit()

    monkeypatch.setattr(timer.TaskManager, "start", receive_task)
    monkeypatch.setattr(timer, "_local_now", lambda: now)
    main_timer = timer._MainTimer()
    await main_timer.timed_start()
    now = planned
    await main_timer.timed_start()
    assert dispatched == [(str(uid), "timed")]
    # 定时已派发后再结束队列，原有自动电源操作仍能执行。
    handler.signal = operation
    await handler.start_power_task()
    await handler.power_task
    assert native_operations == expected_native * 2
    await exit_owner._exit_task
    assert server.should_exit


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [True, False])
async def test_exit_hands_next_wakeup_to_the_frontend(
    isolated_app_paths, monkeypatch, automatic
):
    from app.core import Publisher, TaskManager
    from app.core import power as system
    from app.core.ws import protocol

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
    monkeypatch.setattr(TaskManager, "_running", {})
    requests = []

    async def send(**kwargs):
        if kwargs["type"] == protocol.FRONTEND_CLOSE_REQUESTED:
            requests.append(kwargs.get("data"))
        return False

    monkeypatch.setattr(Publisher, "send", send)
    handler = system._PowerManager()
    await handler.set_power("KillSelf", automatic=automatic)
    await asyncio.sleep(0)
    assert len(requests) == 1
    assert requests[0] is not None
    data = requests[0].model_dump(mode="json")
    assert data["automatic"] == automatic
    if automatic:
        assert datetime.fromisoformat(data["nextWakeAt"]) == wake_at
    else:
        assert data["nextWakeAt"] is None
