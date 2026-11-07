"""唤醒冷启动迟到时按原有宽限补跑，普通启动不补过往定时。"""

from datetime import datetime, timedelta

import pytest

from app.config import ConfigCollection
from app.models.config import GlobalConfig, QueueConfig
from app.models.config.queue import TimeSet
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launch_kind,delay,expected",
    [
        ("wake", 1, 1),
        ("wake", 11, 0),
        ("manual", 1, 0),
        ("resume", 1, 1),
        ("resume", 11, 0),
        ("manual_resume", 61, 0),
    ],
)
async def test_first_timed_check_after_cold_start(
    isolated_app_paths, monkeypatch, launch_kind, delay, expected
):
    from app.core import timer
    from app.core.timer import _MainTimer

    planned = datetime(2026, 11, 2, 0, 3).astimezone()
    now = planned + timedelta(minutes=delay)
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
    monkeypatch.setenv(
        "AUTO_MAS_SCHEDULED_WAKEUP", "1" if launch_kind == "wake" else "0"
    )
    monkeypatch.delenv("AUTO_MAS_SYSTEM_RESUME", raising=False)
    if launch_kind in {"resume", "manual_resume"}:
        # 定时恢复发生在周日，计划属于周一；后端准备时间不改变恢复来源。
        resumed_at = planned - timedelta(minutes=5) if launch_kind == "resume" else now
        monkeypatch.setenv("AUTO_MAS_SYSTEM_RESUME", resumed_at.isoformat())
    handler = _MainTimer()
    monkeypatch.setattr(timer, "_local_now", lambda: now)
    dispatched = []

    async def receive_task(mode, tasks, **kwargs):
        dispatched.append((mode, tasks[0]["uid"], kwargs["trigger"].value))
        queue.Data.LastTimedStart = now
        await queue.commit()

    # 调度器的结果是向任务管理器派发；不在这个边界启动脚本或游戏。
    monkeypatch.setattr(timer.TaskManager, "start", receive_task)
    main_timer = handler
    await main_timer.timed_start()
    await main_timer.timed_start()
    await timer._MainTimer().timed_start()
    assert dispatched == [("AutoProxy", str(uid), "timed")] * expected
    if expected:
        assert queue.Data.LastTimedStart == now


@pytest.mark.asyncio
async def test_cold_wakeup_does_not_replay_slots_before_last_dispatch(
    isolated_app_paths, monkeypatch
):
    from app.core import timer

    last_run = datetime(2026, 11, 2, 8, 0).astimezone()
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    uid = queues.add(
        QueueConfig,
        payload={"Info": {"TimeEnabled": True}, "Data": {"LastTimedStart": last_run}},
    )
    await queues.commit()
    queue = queues[uid]
    for minute in (-5, 0, 10):
        queue.TimeSet.add(
            TimeSet,
            payload={
                "Info": {
                    "Time": last_run + timedelta(minutes=minute),
                    "Days": ["Monday"],
                }
            },
        )
    await queue.TimeSet.commit()
    monkeypatch.setattr(isolated_app_paths, "QueueConfig", queues)
    monkeypatch.setenv("AUTO_MAS_SCHEDULED_WAKEUP", "1")
    now = last_run + timedelta(minutes=5)
    monkeypatch.setattr(timer, "_local_now", lambda: now)
    dispatched = []

    async def receive_task(mode, tasks, **kwargs):
        dispatched.append((mode, tasks[0]["uid"], kwargs["trigger"].value))
        queue.Data.LastTimedStart = now
        await queue.commit()

    monkeypatch.setattr(timer.TaskManager, "start", receive_task)
    main_timer = timer._MainTimer()
    await main_timer.timed_start()
    assert dispatched == []
    assert queue.Data.LastTimedStart == last_run
    now = last_run + timedelta(minutes=10)
    await main_timer.timed_start()
    assert dispatched == [("AutoProxy", str(uid), "timed")]
    assert queue.Data.LastTimedStart == now
