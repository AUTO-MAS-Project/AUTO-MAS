"""Task scheduler fixtures shared by core and task regression tests."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core import Config
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.task_manager import _TaskManager
from app.models.config import (
    GeneralConfig,
    GeneralUserConfig,
    QueueConfig,
    ScriptConfigType,
)
from app.task.legacy import TaskExecuteBase


async def create_runtime_tree(*, script_id="script", user_id="user"):
    """建立不启动执行器的真实运行树，供预下载状态和路径发布回归共用。"""
    from app.models.task import TaskItem, TaskScriptItem, TaskUserItem

    root = TaskItem()
    await root.activate()
    sid = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": script_id, "name": "Script"}}
    )
    await root.scripts.commit()
    script = root.scripts[sid]
    uid = script.users.add(
        TaskUserItem, payload={"info": {"user_id": user_id, "name": "User"}}
    )
    await script.users.commit()
    await root.set_current_index(0)
    return root, script, script.users[uid]


class Builtin(TaskExecuteBase):
    def __init__(self, script):
        super().__init__()
        self.script_info = script
        self.task_info = script.task_info

    async def main_task(self):
        for user in self.script_info.users.values():
            await user.set_state(status="完成")
        await self.script_info.set_state(status="完成")

    async def final_task(self):
        pass

    async def on_crash(self, exc):
        raise exc


@pytest_asyncio.fixture
async def scheduler():
    scripts = ConfigCollection[ScriptConfigType].build([GeneralConfig])
    queues = ConfigCollection[QueueConfig].build([QueueConfig])
    await scripts.activate()
    await queues.activate()
    sid = scripts.add(GeneralConfig, payload={"Info": {"Name": "script"}})
    await scripts.commit()
    for name in ("first", "second"):
        scripts[sid].UserData.add(
            GeneralUserConfig,
            payload={"Info": {"Name": name, "Status": True, "RemainedDay": -1}},
        )
    await scripts[sid].UserData.commit()
    manager = _TaskManager()
    manager.bind_manager_factories({GeneralConfig: lambda script: Builtin(script)})
    notify = MagicMock()
    notify.task_notification_batch.side_effect = lambda **kwargs: nullcontext()
    background = BackgroundTaskRegistry()
    from app.core.power import _PowerManager

    power = _PowerManager()
    with (
        patch("app.core.task_manager.TaskManager", manager),
        patch("app.core.Power", power),
        patch("app.core.BackgroundTaskManager", background),
        patch("app.task.prefetch.BackgroundTaskManager", background),
        patch("app.task.history_core.BackgroundTaskManager", background),
        patch.object(Config, "ScriptConfig", scripts),
        patch.object(Config, "QueueConfig", queues),
        patch.dict(config_manager._collections, {"ScriptConfig": scripts}),
        patch("app.task.script_expander.Notify", notify),
        patch("app.core.ws.Publisher.send", AsyncMock(return_value=True)),
        patch("app.core.desktop_guard.ensure_desktop_available", AsyncMock()),
        patch("app.core.timer.MainTimer.schedule_community_for_task"),
    ):
        yield manager, scripts, queues, sid
        for run in list(manager._running.values()):
            await asyncio.wait_for(run.stop(), 3)
        await power.cancel_power_task()
        assert await background.shutdown(timeout=3)
