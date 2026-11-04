import asyncio
import unittest
from unittest.mock import AsyncMock

from app.core.lifecycle import _ShutdownCoordinator


class ShutdownCoordinatorTest(unittest.IsolatedAsyncioTestCase):
    async def test_teardown_runs_once_under_concurrent_calls(self):
        coordinator = _ShutdownCoordinator()
        teardown = AsyncMock()
        coordinator.set_teardown(teardown)

        # /close 与 lifespan 收尾可能并发调用，只应真正执行一次
        await asyncio.gather(
            coordinator.run_teardown(),
            coordinator.run_teardown(),
            coordinator.run_teardown(),
        )
        await coordinator.run_teardown()

        teardown.assert_awaited_once()

    async def test_teardown_retries_after_failure(self):
        coordinator = _ShutdownCoordinator()
        teardown = AsyncMock(side_effect=[RuntimeError("boom"), None])
        coordinator.set_teardown(teardown)

        # 首次失败后不置完成标志，允许重试；成功后才不再执行
        with self.assertRaises(RuntimeError):
            await coordinator.run_teardown()
        await coordinator.run_teardown()
        await coordinator.run_teardown()

        self.assertEqual(teardown.await_count, 2)


if __name__ == "__main__":
    unittest.main()
