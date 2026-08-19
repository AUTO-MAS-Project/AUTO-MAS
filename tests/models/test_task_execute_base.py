import asyncio
import unittest

from app.models.task import TaskExecuteBase


class _BlockingFinalTask(TaskExecuteBase):
    wait_for_finalizer_on_cancel = True

    def __init__(self) -> None:
        super().__init__()
        self.final_started = asyncio.Event()
        self.final_release = asyncio.Event()
        self.final_completed = asyncio.Event()
        self.final_cancelled = False

    async def main_task(self) -> None:
        return

    async def final_task(self) -> None:
        self.final_started.set()
        try:
            await self.final_release.wait()
        except asyncio.CancelledError:
            self.final_cancelled = True
            raise
        self.final_completed.set()

    async def on_crash(self, e: Exception) -> None:
        raise AssertionError(f"unexpected task error: {e}")


class _BlockingMainTask(TaskExecuteBase):
    wait_for_finalizer_on_cancel = True

    def __init__(self) -> None:
        super().__init__()
        self.main_started = asyncio.Event()
        self.final_completed = asyncio.Event()

    async def main_task(self) -> None:
        self.main_started.set()
        await asyncio.Event().wait()

    async def final_task(self) -> None:
        self.final_completed.set()

    async def on_crash(self, e: Exception) -> None:
        raise AssertionError(f"unexpected task error: {e}")


class _DefaultBlockingFinalTask(_BlockingFinalTask):
    wait_for_finalizer_on_cancel = False


class TaskExecuteBaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_task_cancellation_does_not_wait_for_finalizer(self) -> None:
        task = _DefaultBlockingFinalTask()

        async with asyncio.TaskGroup() as task_group:
            runner = task_group.create_task(task._execute_task(task_group))
            await task.final_started.wait()
            runner.cancel()
            await task.accomplish.wait()

            self.assertTrue(runner.done())
            self.assertFalse(task.final_completed.is_set())
            task.final_release.set()
            await task.final_completed.wait()

        self.assertTrue(runner.cancelled())

    async def test_cancel_during_main_remains_cancelled_after_finalizer(self) -> None:
        task = _BlockingMainTask()

        async with asyncio.TaskGroup() as task_group:
            runner = task_group.create_task(task._execute_task(task_group))
            await task.main_started.wait()
            runner.cancel()

        self.assertTrue(runner.cancelled())
        self.assertTrue(task.final_completed.is_set())
        self.assertTrue(task.accomplish.is_set())

    async def test_cancel_during_final_waits_for_finalizer(self) -> None:
        task = _BlockingFinalTask()

        async with asyncio.TaskGroup() as task_group:
            runner = task_group.create_task(task._execute_task(task_group))
            await task.final_started.wait()

            runner.cancel()
            await asyncio.sleep(0)
            runner.cancel()
            await asyncio.sleep(0)

            try:
                self.assertFalse(runner.done())
                self.assertFalse(task.accomplish.is_set())
            finally:
                task.final_release.set()

        self.assertTrue(runner.cancelled())
        self.assertTrue(task.final_completed.is_set())
        self.assertFalse(task.final_cancelled)
        self.assertTrue(task.accomplish.is_set())


if __name__ == "__main__":
    unittest.main()
