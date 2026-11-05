"""以任务计划程序收到的定义验证自启和唤醒，不操作用户的系统任务。"""

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.services.windows.startup import WindowsStartupManager
from app.utils.common.process import runner

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


@pytest.fixture
def scheduler(monkeypatch):
    definitions: dict[str, ET.Element] = {}

    async def run_process(*args, **kwargs):
        name = args[args.index("/tn") + 1] if "/tn" in args else None
        if "/create" in args:
            xml = Path(args[args.index("/xml") + 1]).read_text(encoding="utf-16")
            definitions[name] = ET.fromstring(xml)
        elif "/delete" in args:
            definitions.pop(name, None)
        elif "/query" in args:
            if name:
                return subprocess.CompletedProcess(
                    args, 0 if name in definitions else 1, "", ""
                )
            rows = "\n".join(
                f'"\\{task_name}","N/A","Ready"' for task_name in definitions
            )
            return subprocess.CompletedProcess(args, 0, rows, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(runner.ProcessRunner, "run_process", run_process)
    return definitions


@pytest.mark.asyncio
async def test_login_task_preserves_install_path_and_normal_startup(
    isolated_app_paths, scheduler
):
    # Windows 支持路径中含 &；任务 XML 必须原样还原路径，不能损坏定义。
    isolated_app_paths.work_path /= "MAS & tools"
    await WindowsStartupManager().set_enabled(enabled=True)
    task = scheduler["AUTO-MAS_AutoStart"]
    assert task.find("t:Triggers/t:LogonTrigger", NS) is not None
    assert task.findtext("t:Settings/t:WakeToRun", namespaces=NS) == "false"
    assert task.findtext("t:Actions/t:Exec/t:Command", namespaces=NS) == str(
        isolated_app_paths.work_path / "AUTO-MAS.exe"
    )
    assert (
        task.findtext("t:Actions/t:Exec/t:Arguments", namespaces=NS) == "--auto-start"
    )


@pytest.mark.asyncio
async def test_queue_edits_and_cancellation_update_only_wakeup_tasks(
    isolated_app_paths, scheduler, monkeypatch
):
    from app.config import ConfigCollection
    from app.models.config import GlobalConfig, QueueConfig
    from app.models.config.queue import TimeSet
    from app.services.common import system
    from tests.config_support import activate_config

    config = isolated_app_paths
    setting = await activate_config(
        GlobalConfig.model_validate({"Start": {"IfScheduledWakeUp": True}})
    )
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    uid = queues.add(QueueConfig, payload={"Info": {"TimeEnabled": True}})
    await queues.commit()
    queue = queues[uid]
    slot_id = queue.TimeSet.add(
        TimeSet,
        payload={
            "Info": {
                "Days": ["Monday"],
                "Time": datetime(2000, 1, 3, 0, 3).astimezone().isoformat(),
            }
        },
    )
    await queue.TimeSet.commit()
    monkeypatch.setattr(config, "setting", setting)
    monkeypatch.setattr(config, "QueueConfig", queues)
    monkeypatch.setattr(system, "startup", WindowsStartupManager())
    monkeypatch.setenv("AUTO_MAS_ENV", "production")
    (config.work_path / "AUTO-MAS.exe").touch()
    handler = system._SystemHandler()
    await system.startup.set_enabled(enabled=True)

    await handler.sync_scheduled_wakeup()

    def wake_tasks():
        return [
            task for name, task in scheduler.items() if name != "AUTO-MAS_AutoStart"
        ]

    trigger = wake_tasks()[0].find("t:Triggers/t:CalendarTrigger", NS)
    assert trigger.findtext("t:StartBoundary", namespaces=NS).endswith("T23:58:00")
    assert trigger.find("t:ScheduleByWeek/t:DaysOfWeek/t:Sunday", NS) is not None

    # 系统已经注册成功，但读取子进程结果时恰好退出；下一次对账必须纠正部分完成的结果。
    original_time = queue.TimeSet[slot_id].Info.Time
    queue.TimeSet[slot_id].Info.Time = datetime(2000, 1, 3, 8, 0).astimezone()
    await queue.TimeSet[slot_id].commit()
    registered = asyncio.Event()
    process_call = runner.ProcessRunner.run_process

    async def commit_then_wait(*args, **kwargs):
        result = await process_call(*args, **kwargs)
        if "/create" in args:
            registered.set()
            await asyncio.Event().wait()
        return result

    with monkeypatch.context() as boundary:
        boundary.setattr(runner.ProcessRunner, "run_process", commit_then_wait)
        pending = asyncio.create_task(handler.sync_scheduled_wakeup())
        await asyncio.wait_for(registered.wait(), timeout=1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    queue.TimeSet[slot_id].Info.Time = original_time
    await queue.TimeSet[slot_id].commit()
    await handler.sync_scheduled_wakeup()
    trigger = wake_tasks()[0].find("t:Triggers/t:CalendarTrigger", NS)
    assert trigger.findtext("t:StartBoundary", namespaces=NS).endswith("T23:58:00")

    slot = queue.TimeSet[slot_id]
    slot.Info.Time = datetime(2000, 1, 3, 8, 0).astimezone()
    await slot.commit()
    await handler.sync_scheduled_wakeup()
    trigger = wake_tasks()[0].find("t:Triggers/t:CalendarTrigger", NS)
    assert trigger.findtext("t:StartBoundary", namespaces=NS).endswith("T07:55:00")
    assert trigger.find("t:ScheduleByWeek/t:DaysOfWeek/t:Monday", NS) is not None

    slot.Info.Enabled = False
    await slot.commit()
    await handler.sync_scheduled_wakeup()
    assert set(scheduler) == {"AUTO-MAS_AutoStart"}

    slot.Info.Enabled = True
    await slot.commit()
    await handler.sync_scheduled_wakeup()
    assert len(wake_tasks()) == 1
    queue.Info.CycleEnabled = True
    await queue.commit()
    await handler.sync_scheduled_wakeup()
    assert not wake_tasks()
    queue.Info.CycleEnabled = False
    await queue.commit()
    await handler.sync_scheduled_wakeup()
    setting.Start.IfScheduledWakeUp = False
    await setting.commit()
    await handler.sync_scheduled_wakeup()
    assert not wake_tasks()
    setting.Start.IfScheduledWakeUp = True
    await setting.commit()
    await handler.sync_scheduled_wakeup()
    assert len(wake_tasks()) == 1
    queues.remove(uid)
    await queues.commit()
    await handler.sync_scheduled_wakeup()
    assert set(scheduler) == {"AUTO-MAS_AutoStart"}


@pytest.mark.asyncio
async def test_many_timers_keep_every_trigger_and_cancel_without_touching_other_installs(
    tmp_path, scheduler
):
    manager = WindowsStartupManager()
    executable = tmp_path / "AUTO-MAS.exe"
    other = tmp_path / "other" / "AUTO-MAS.exe"
    await manager.sync_wakeup(executable=other, times=((2, 10, 0),))
    other_names = set(scheduler)
    times = (
        tuple((0, hour, 0) for hour in range(24))
        + tuple((0, hour, 30) for hour in range(24))
        + ((6, 23, 58),)
    )
    await manager.sync_wakeup(executable=executable, times=times)
    tasks = [task for name, task in scheduler.items() if name not in other_names]
    assert (
        sum(len(task.findall("t:Triggers/t:CalendarTrigger", NS)) for task in tasks)
        == 49
    )
    assert all(
        len(task.findall("t:Triggers/t:CalendarTrigger", NS)) <= 48 for task in tasks
    )
    await manager.sync_wakeup(executable=executable, times=((0, 7, 55),))
    assert len(scheduler) == len(other_names) + 1
    await manager.sync_wakeup(executable=executable, times=())
    assert set(scheduler) == other_names


@pytest.mark.asyncio
async def test_wakeup_launch_skips_startup_queue_wait(monkeypatch):
    from app.core import TaskManager

    # 连接建立后的普通启动会等十秒；唤醒启动应立即返回，留给原定时调度。
    monkeypatch.setenv("AUTO_MAS_SCHEDULED_WAKEUP", "1")
    await asyncio.wait_for(TaskManager.start_startup_queue(), timeout=0.5)


@pytest.mark.asyncio
async def test_disabled_wakeup_query_failure_is_quiet_and_cleanup_retries(
    isolated_app_paths, scheduler, monkeypatch
):
    from app.config import ConfigCollection
    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.config import GlobalConfig, QueueConfig
    from app.services.common import system
    from tests.config_support import activate_config

    setting = await activate_config(GlobalConfig())
    queues = await activate_config(ConfigCollection.build([QueueConfig]))
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "QueueConfig", queues)
    monkeypatch.setattr(system, "startup", WindowsStartupManager())
    monkeypatch.setenv("AUTO_MAS_ENV", "production")
    executable = isolated_app_paths.work_path / "AUTO-MAS.exe"
    executable.touch()
    # 上次退出前没能完成取消，关闭状态下的首次对账仍需移除遗留任务。
    await system.startup.sync_wakeup(executable=executable, times=((0, 7, 55),))
    assert scheduler
    events = []

    async def send(**kwargs):
        events.append(kwargs["type"])
        return True

    monkeypatch.setattr(Publisher, "send", send)
    process_call = runner.ProcessRunner.run_process

    async def query_denied(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Access denied")

    monkeypatch.setattr(runner.ProcessRunner, "run_process", query_denied)
    handler = system._SystemHandler()
    await handler.sync_scheduled_wakeup()
    assert protocol.SYSTEM_NOTICE not in events
    assert scheduler
    monkeypatch.setattr(runner.ProcessRunner, "run_process", process_call)
    await handler.sync_scheduled_wakeup(force=True)
    assert scheduler == {}
    # 启用后同样的查询失败必须仍然通知用户，不能把失败一概当成成功。
    setting.Start.IfScheduledWakeUp = True
    await setting.commit()
    monkeypatch.setattr(runner.ProcessRunner, "run_process", query_denied)
    with pytest.raises(RuntimeError, match="Access denied"):
        await system._SystemHandler().sync_scheduled_wakeup()
    assert events == [protocol.SYSTEM_NOTICE]
