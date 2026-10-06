import unittest
import uuid

from app.api.dispatch import DispatchIn, stop_task
from app.core import TaskDispatcher


class StopTaskTest(unittest.IsolatedAsyncioTestCase):
    async def test_stopping_missing_task_is_idempotent(self):
        """任务已结束时中止仍视为成功。

        WebSocket 断线时前端拿不到 task.completed，用户会再点一次停止；
        此时任务早已从在跑登记表移除，若抛错前端只能看到 500。
        """

        task_id = uuid.uuid4()
        # 在跑登记表是 TaskDispatcher 私有的，这里只断言「不在其中」这一前置
        self.assertNotIn(task_id, TaskDispatcher._running)

        response = await stop_task(DispatchIn(taskId=str(task_id)))

        self.assertEqual(response.code, 200)
        self.assertEqual(response.status, "success")
        self.assertNotIn(task_id, TaskDispatcher._running)

    async def test_invalid_task_id_still_reports_error(self):
        """非法任务 ID 仍应报错，幂等只覆盖“任务已结束”。"""

        response = await stop_task(DispatchIn(taskId="not-a-uuid"))

        self.assertEqual(response.code, 500)


if __name__ == "__main__":
    unittest.main()
