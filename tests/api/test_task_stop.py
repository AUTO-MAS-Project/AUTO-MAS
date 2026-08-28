import unittest
import uuid

from app.api.dispatch import stop_task
from app.core import TaskManager
from app.models.schema import DispatchIn


class StopTaskTest(unittest.IsolatedAsyncioTestCase):
    async def test_stopping_missing_task_is_idempotent(self):
        """任务已结束时中止仍视为成功。

        WebSocket 断线时前端拿不到 task.completed，用户会再点一次停止；
        此时任务早已从 task_handler 移除，若抛错前端只能看到 500。
        """

        task_id = uuid.uuid4()
        self.assertNotIn(task_id, TaskManager.task_handler)

        response = await stop_task(DispatchIn(taskId=str(task_id)))

        self.assertEqual(response.code, 200)
        self.assertEqual(response.status, "success")
        self.assertNotIn(task_id, TaskManager.task_handler)

    async def test_invalid_task_id_still_reports_error(self):
        """非法任务 ID 仍应报错，幂等只覆盖“任务已结束”。"""

        response = await stop_task(DispatchIn(taskId="not-a-uuid"))

        self.assertEqual(response.code, 500)


if __name__ == "__main__":
    unittest.main()
