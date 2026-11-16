"""停止回归复用 5.8 的真实调度与运行记录。"""

import asyncio
from contextlib import suppress
from uuid import uuid4

from app.core.task_manager.manager import Task, TaskInfo
from app.models.task import ScriptItem, TaskExecuteBase, UserItem


async def add_script(info, script_id, user_id=None):
    script = ScriptItem(script_id=script_id, name="test", status="运行")
    if user_id is not None:
        script.user_list.append(UserItem(user_id=user_id, name="test", status="等待"))
    info.script_list = [*info.script_list, script]
    info.current_index = len(info.script_list) - 1
    if user_id is not None:
        script.current_index = 0
    return script


class StopTask(TaskExecuteBase):
    STOP_CHECK_TIMEOUTS = {"update": 30.0, "finalize": 1.0}

    def __init__(self):
        super().__init__()
        owner = self

        class Root(Task):
            async def _run_main_task(self):
                await self.spawn(owner)

        self.task_info = TaskInfo("AutoProxy", str(uuid4()), None, None, None)
        self.root = Root(self.task_info, [], manager_factories={})
        self.root.STOP_CHECK_TIMEOUTS = self.STOP_CHECK_TIMEOUTS

    def start(self):
        self.root.execute()

    async def stop(self):
        self.root.cancel()
        if self.root.task is not None:
            with suppress(asyncio.CancelledError):
                await self.root.task

    async def final_task(self):
        pass

    async def on_crash(self, error):
        raise error

    @property
    def _stop_scope(self):
        return self.root._stop_scope

    @property
    def _task(self):
        return self.root.task

    def request_stop(self):
        return asyncio.create_task(self.stop())
