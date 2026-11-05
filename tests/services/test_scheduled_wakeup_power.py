"""相邻定时之间保持调度可用；测试始终隔离系统电源与前端关闭边界。"""

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
    "operation,second", [("Sleep", 0), ("Hibernate", 0), ("KillSelf", 0), ("Sleep", 30)]
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
