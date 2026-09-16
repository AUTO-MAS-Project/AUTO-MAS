import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.task_manager import Task, TaskInfo, _TaskManager
from app.models.task import ScriptItem, UserItem


def _script_item(script_id: str) -> ScriptItem:
    return ScriptItem(
        script_id=script_id,
        status="等待",
        name=script_id,
        user_list=[UserItem(user_id="u", name="u", status="等待")],
    )


class QueueItemRunDaysTest(unittest.IsolatedAsyncioTestCase):
    async def test_items_not_scheduled_today_are_skipped(self) -> None:
        run_id = str(uuid.uuid4())
        skip_id = str(uuid.uuid4())
        task_info = TaskInfo(
            mode="AutoProxy",
            task_id="task-id",
            queue_id=str(uuid.uuid4()),
            script_id=None,
            user_id=None,
        )
        task_info.script_list = [_script_item(run_id), _script_item(skip_id)]

        with patch("app.core.task_manager.datetime") as mocked_datetime:
            mocked_datetime.now.return_value.strftime.return_value = "Saturday"
            task = Task(
                task_info,
                [],
                script_run_days=[["Saturday"], ["Monday", "Friday"]],
            )

        # 只验证周几闸门：放行的项走到占用检查，用占用失败让流程止步于此
        task.script_reservations.try_acquire = MagicMock(return_value=False)
        with (
            patch("app.core.task_manager.Config") as config,
            patch("app.core.task_manager.Publisher.send", new=AsyncMock()) as send,
        ):
            config.ScriptConfig = {
                uuid.UUID(run_id): MagicMock(),
                uuid.UUID(skip_id): MagicMock(),
            }
            await task._run_script_list(0)

        self.assertEqual(task_info.script_list[1].status, "跳过")
        self.assertEqual(task_info.script_list[0].status, "跳过")
        # 周几跳过不发通知；占用失败那条才发，且只发了一次
        send.assert_awaited_once()
        task.script_reservations.try_acquire.assert_called_once()

    def test_non_queue_task_never_skips(self) -> None:
        task_info = TaskInfo(
            mode="AutoProxy",
            task_id="task-id",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        task = Task(task_info, [])

        self.assertTrue(task._is_script_scheduled_today(0))
        self.assertTrue(task._is_script_scheduled_today(5))

    def test_queue_entries_carry_item_days(self) -> None:
        queue_id = uuid.uuid4()
        script_id = uuid.uuid4()
        item = MagicMock()
        item.get.side_effect = lambda group, key: {
            ("Info", "ScriptId"): str(script_id),
            ("Schedule", "Days"): ["Monday"],
        }[(group, key)]
        empty_item = MagicMock()
        empty_item.get.side_effect = lambda group, key: {
            ("Info", "ScriptId"): "-",
            ("Schedule", "Days"): ["Monday"],
        }[(group, key)]
        queue = MagicMock()
        queue.QueueItem.values.return_value = [item, empty_item]

        with patch("app.core.task_manager.Config") as config:
            config.QueueConfig = {queue_id: queue}
            entries = _TaskManager._queue_script_entries(queue_id)
            ids = _TaskManager._queue_script_ids(queue_id)

        self.assertEqual(entries, [(script_id, ["Monday"])])
        self.assertEqual(ids, [script_id])


if __name__ == "__main__":
    unittest.main()
