import unittest
import uuid
from inspect import signature
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.task_manager import Task, TaskInfo, _TaskManager
from app.core.timer import _MainTimer


class TaskGameSignSourceTest(unittest.IsolatedAsyncioTestCase):
    def test_manual_task_is_the_default_trigger_source(self) -> None:
        parameter = signature(_TaskManager.add_task).parameters["trigger_source"]

        self.assertEqual(parameter.default, "manual_task")

    async def test_task_trigger_source_is_forwarded_to_sign_flow(self) -> None:
        expected_sources = {
            "scheduled_task": "task_scheduled",
            "manual_task": "task_manual",
            "startup_task": "task_startup",
        }

        for trigger_source, sign_source in expected_sources.items():
            with self.subTest(trigger_source=trigger_source):
                task_info = TaskInfo(
                    mode="AutoProxy",
                    task_id="task-id",
                    queue_id=None,
                    script_id=None,
                    user_id=None,
                    trigger_source=trigger_source,
                )
                task = Task(task_info, [])
                task.prepare = AsyncMock()

                with patch(
                    "app.core.timer.MainTimer.try_community_for_task",
                    new=AsyncMock(return_value=[]),
                ) as sign_for_task:
                    await task.main_task()

                sign_for_task.assert_awaited_once_with(source=sign_source)

    async def test_timed_queue_passes_scheduled_trigger_source(self) -> None:
        queue_id = uuid.uuid4()
        timer = _MainTimer()
        queue = MagicMock()
        queue.get.side_effect = lambda group, key: {
            ("Info", "TimeEnabled"): True,
            ("Data", "LastTimedStart"): "2000-01-01 00:00",
            ("Info", "Name"): "定时队列",
        }[(group, key)]
        queue.set = AsyncMock()
        time_set = MagicMock()
        time_set.get.side_effect = lambda group, key: {
            ("Info", "Enabled"): True,
            ("Info", "Days"): ["Saturday"],
            ("Info", "Time"): "15:00",
        }[(group, key)]
        queue.TimeSet.values.return_value = [time_set]

        with (
            patch("app.core.timer.Config") as config,
            patch("app.core.timer.TaskManager") as task_manager,
            patch("app.core.timer.datetime") as mocked_datetime,
        ):
            config.QueueConfig = {queue_id: queue}
            task_manager.add_task = AsyncMock()
            mocked_datetime.now.return_value.strftime.side_effect = lambda fmt: {
                "%Y-%m-%d %H:%M": "2026-08-08 15:00",
                "%A": "Saturday",
            }[fmt]

            await timer.timed_start()

        task_manager.add_task.assert_awaited_once_with(
            "AutoProxy",
            str(queue_id),
            new_task_info={
                "queueId": str(queue_id),
                "taskName": "队列 - 定时队列",
                "taskType": "定时代理",
            },
            trigger_source="scheduled_task",
        )

    async def test_startup_queue_passes_startup_trigger_source(self) -> None:
        queue_id = uuid.uuid4()
        manager = _TaskManager()
        queue = MagicMock()
        queue.set = AsyncMock()
        queue.get.side_effect = lambda group, key: {
            ("Info", "StartUpMode"): "Always",
            ("Info", "Name"): "启动队列",
        }[(group, key)]

        with (
            patch("app.core.task_manager.Config") as config,
            patch("app.core.task_manager.TaskManager") as task_manager,
            patch("app.core.task_manager.MainConnection") as main_connection,
            patch("app.core.task_manager.asyncio.sleep", new_callable=AsyncMock),
            patch("app.core.task_manager.datetime") as mocked_datetime,
        ):
            main_connection.is_connected = True
            config.QueueConfig = {queue_id: queue}
            task_manager.add_task = AsyncMock()
            mocked_datetime.now.return_value.strftime.return_value = "2026-08-27"

            await manager.start_startup_queue()

        task_manager.add_task.assert_awaited_once_with(
            "AutoProxy",
            str(queue_id),
            new_task_info={
                "queueId": str(queue_id),
                "taskName": "队列 - 启动队列",
                "taskType": "启动时代理",
            },
            trigger_source="startup_task",
        )
        queue.set.assert_awaited_once_with("Data", "LastStartupTime", "2026-08-27")

    async def test_startup_queue_runs_dailyfirst_queue_not_started_today(self) -> None:
        queue_id = uuid.uuid4()
        manager = _TaskManager()
        queue = MagicMock()
        queue.set = AsyncMock()
        queue.get.side_effect = lambda group, key: {
            ("Info", "StartUpMode"): "DailyFirst",
            ("Info", "Name"): "启动队列",
            ("Data", "LastStartupTime"): "2000-01-01",
        }[(group, key)]

        with (
            patch("app.core.task_manager.Config") as config,
            patch("app.core.task_manager.TaskManager") as task_manager,
            patch("app.core.task_manager.MainConnection") as main_connection,
            patch("app.core.task_manager.asyncio.sleep", new_callable=AsyncMock),
            patch("app.core.task_manager.datetime") as mocked_datetime,
        ):
            main_connection.is_connected = True
            config.QueueConfig = {queue_id: queue}
            task_manager.add_task = AsyncMock()
            mocked_datetime.now.return_value.strftime.return_value = "2026-08-27"

            await manager.start_startup_queue()

        task_manager.add_task.assert_awaited_once_with(
            "AutoProxy",
            str(queue_id),
            new_task_info={
                "queueId": str(queue_id),
                "taskName": "队列 - 启动队列",
                "taskType": "启动时代理",
            },
            trigger_source="startup_task",
        )
        queue.set.assert_awaited_once_with("Data", "LastStartupTime", "2026-08-27")

    async def test_startup_queue_skips_dailyfirst_queue_started_today(self) -> None:
        queue_id = uuid.uuid4()
        manager = _TaskManager()
        queue = MagicMock()
        queue.set = AsyncMock()
        queue.get.side_effect = lambda group, key: {
            ("Info", "StartUpMode"): "DailyFirst",
            ("Data", "LastStartupTime"): "2026-08-27",
        }[(group, key)]

        with (
            patch("app.core.task_manager.Config") as config,
            patch("app.core.task_manager.TaskManager") as task_manager,
            patch("app.core.task_manager.MainConnection") as main_connection,
            patch("app.core.task_manager.asyncio.sleep", new_callable=AsyncMock),
            patch("app.core.task_manager.datetime") as mocked_datetime,
        ):
            main_connection.is_connected = True
            config.QueueConfig = {queue_id: queue}
            task_manager.add_task = AsyncMock()
            mocked_datetime.now.return_value.strftime.return_value = "2026-08-27"

            await manager.start_startup_queue()

        task_manager.add_task.assert_not_awaited()
        queue.set.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
