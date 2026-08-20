import asyncio
import unittest

from app.services.endfield_activity import EndfieldActivityService
from app.services.reverse1999_activity import Reverse1999ActivityService
from app.services.starrail_activity import SraActivityService


class SraActivityOverviewTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = SraActivityService(game="test", display_name="测试")
        self.service._data = {}
        self.service._etag = ""
        self.service._last_error = ""
        self.service._next_check = 0.0
        self.service._refresh_task = None

    async def test_cold_cache_returns_fetching_message_without_waiting(self) -> None:
        async def slow_refresh() -> None:
            try:
                await asyncio.sleep(0.3)
            finally:
                self.service._refresh_task = None

        self.service._refresh = slow_refresh  # type: ignore[method-assign]

        # 冷缓存 + 后台刷新进行中：get_overview 必须立即返回"正在获取"，不得等待刷新完成
        overview = await asyncio.wait_for(self.service.get_overview(), timeout=0.1)

        self.assertFalse(overview["Available"])
        self.assertIn("正在获取", overview["Message"])
        self.assertEqual(overview["activities"], [])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

    async def test_invalid_activity_list_is_normalized(self) -> None:
        self.service._data = {"version": "1.0", "activities": None}
        self.service._next_check = float("inf")

        overview = await self.service.get_overview()

        self.assertEqual(overview["version"], "1.0")
        self.assertEqual(overview["activities"], [])

    async def test_data_arrives_after_background_refresh_completes(self) -> None:
        async def quick_refresh() -> None:
            try:
                self.service._data = {"Version": "1.0", "Activity": []}
                self.service._next_check = float("inf")
            finally:
                self.service._refresh_task = None

        self.service._refresh = quick_refresh  # type: ignore[method-assign]

        first = await self.service.get_overview()
        self.assertFalse(first["Available"])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        second = await self.service.get_overview()
        self.assertTrue(second["Available"])
        self.assertEqual(second["Version"], "1.0")

    async def test_unavailable_after_refresh_failure(self) -> None:
        async def failing_refresh() -> None:
            try:
                raise RuntimeError("network down")
            except RuntimeError as error:
                self.service._last_error = f"RuntimeError: {str(error)}"
                self.service._next_check = float("inf")
            finally:
                self.service._refresh_task = None

        self.service._refresh = failing_refresh  # type: ignore[method-assign]

        await self.service.get_overview()
        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        overview = await self.service.get_overview()
        self.assertFalse(overview["Available"])
        self.assertIn("暂不可用", overview["Message"])


class Reverse1999ActivityOverviewTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = Reverse1999ActivityService()
        self.service._data = {}
        self.service._etag = ""
        self.service._last_error = ""
        self.service._next_check = 0.0
        self.service._refresh_task = None

    async def test_cold_cache_returns_fetching_message_without_waiting(self) -> None:
        async def slow_refresh() -> None:
            await asyncio.sleep(0.3)

        self.service._refresh = slow_refresh  # type: ignore[method-assign]

        overview = await asyncio.wait_for(self.service.get_overview(), timeout=0.1)

        self.assertFalse(overview["Available"])
        self.assertIn("正在获取", overview["Message"])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

    async def test_data_arrives_after_background_refresh_completes(self) -> None:
        async def quick_refresh() -> None:
            self.service._data = {
                "1.0": {
                    "start_time": 1717200000000,
                    "end_time": 4102444800000,
                    "version_name": "测试版本",
                    "activity": {},
                }
            }

        self.service._refresh = quick_refresh  # type: ignore[method-assign]

        first = await self.service.get_overview()
        self.assertFalse(first["Available"])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        second = await self.service.get_overview()
        self.assertTrue(second["Available"])
        self.assertEqual(second["Version"], "1.0")

    async def test_unavailable_after_refresh_failure(self) -> None:
        async def failing_refresh() -> None:
            raise RuntimeError("network down")

        self.service._refresh = failing_refresh  # type: ignore[method-assign]

        await self.service.get_overview()
        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        overview = await self.service.get_overview()
        self.assertFalse(overview["Available"])
        self.assertIn("暂不可用", overview["Message"])


class EndfieldActivityOverviewTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = EndfieldActivityService()
        self.service._version_id = ""
        self.service._source_updated_at = ""
        self.service._activities = []
        self.service._pools = []
        self.service._last_error = ""
        self.service._next_manifest_check = 0.0
        self.service._refresh_task = None

    async def test_cold_cache_returns_fetching_message_without_waiting(self) -> None:
        async def slow_refresh() -> None:
            await asyncio.sleep(0.3)

        self.service._refresh = slow_refresh  # type: ignore[method-assign]

        overview = await asyncio.wait_for(self.service.get_overview(), timeout=0.1)

        self.assertFalse(overview["Available"])
        self.assertIn("正在获取", overview["Message"])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

    async def test_data_arrives_after_background_refresh_completes(self) -> None:
        async def quick_refresh() -> None:
            self.service._version_id = "test-version"

        self.service._refresh = quick_refresh  # type: ignore[method-assign]

        first = await self.service.get_overview()
        self.assertFalse(first["Available"])

        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        second = await self.service.get_overview()
        self.assertTrue(second["Available"])
        self.assertEqual(second["Version"], "test-version")

    async def test_unavailable_after_refresh_failure(self) -> None:
        async def failing_refresh() -> None:
            raise RuntimeError("network down")

        self.service._refresh = failing_refresh  # type: ignore[method-assign]

        await self.service.get_overview()
        task = self.service._refresh_task
        self.assertIsNotNone(task)
        await asyncio.gather(task, return_exceptions=True)

        overview = await self.service.get_overview()
        self.assertFalse(overview["Available"])
        self.assertIn("暂不可用", overview["Message"])
