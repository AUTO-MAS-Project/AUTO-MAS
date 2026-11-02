"""脚本级通知批次；持锁阶段只固定请求，完整收尾后交给宿主发送。"""

import asyncio

from app.core import Notify
from app.models.task import TaskExecuteBase, TaskItem


class NotificationTaskBase(TaskExecuteBase):
    task_info: TaskItem

    async def _execute_task(self, parent_tg: asyncio.TaskGroup):
        with Notify.task_notification_batch(task_id=self.task_info.task_id):
            await super()._execute_task(parent_tg)
