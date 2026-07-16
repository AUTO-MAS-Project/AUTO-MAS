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

    async def test_teardown_exception_propagates(self):
        coordinator = _ShutdownCoordinator()
        coordinator.set_teardown(AsyncMock(side_effect=RuntimeError("boom")))

        with self.assertRaises(RuntimeError):
            await coordinator.run_teardown()

    async def test_missing_teardown_is_safe(self):
        coordinator = _ShutdownCoordinator()
        await coordinator.run_teardown()  # 未注册也不应抛异常


if __name__ == "__main__":
    unittest.main()
