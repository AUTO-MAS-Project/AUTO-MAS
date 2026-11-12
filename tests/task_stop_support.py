"""旧专项停止回归复用真实执行桥与运行树。"""

import asyncio

from blinker import Signal

from app.models.task import TaskItem, TaskMode, TaskScriptItem, TaskUserItem
from app.task.history_core import TaskHistorySession
from app.task.legacy import TaskExecuteBase


async def add_script(info, script_id, user_id=None):
    if info.activation_state.value == "inactive":
        await info.activate()
    uid = info.scripts.add(
        TaskScriptItem,
        payload={"info": {"script_id": script_id, "name": "test", "status": "运行"}},
    )
    await info.scripts.commit()
    script = info.scripts[uid]
    if user_id is not None:
        script.users.add(
            TaskUserItem,
            payload={"info": {"user_id": user_id, "name": "test", "status": "等待"}},
        )
        await script.users.commit()
        await script.set_current_index(0)
    await info.set_current_index(0)
    return script


class StopTask(TaskExecuteBase):
    STOP_CHECK_TIMEOUTS = {"update": 30.0, "finalize": 1.0}

    def __init__(self, info=None):
        super().__init__()
        self.execution.ended = Signal()
        self.task_info = info or TaskItem(info={"mode": TaskMode.AUTO_PROXY})
        self.history = TaskHistorySession(self.task_info)

    @property
    def _stop_scope(self):
        return self.execution._process_scope

    @property
    def _task(self):
        return self.execution._task

    def request_stop(self):
        return asyncio.create_task(self.stop())

    def start(self):
        self.execute()

    async def final_task(self):
        await self.history.close()

    async def on_crash(self, error):
        raise error
