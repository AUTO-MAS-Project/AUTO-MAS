from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import app.api.core as core_api
from app.core.lifecycle import ShutdownCoordinator
from app.core.ws import protocol


class TestShutdownCoordinator(IsolatedAsyncioTestCase):
    async def test_concurrent_calls_run_teardown_once(self) -> None:
        coordinator = ShutdownCoordinator()
        teardown = AsyncMock()
        coordinator.set_teardown(teardown)

        await asyncio.gather(
            coordinator.run_teardown(),
            coordinator.run_teardown(),
            coordinator.run_teardown(),
        )
        await coordinator.run_teardown()

        teardown.assert_awaited_once()
        self.assertTrue(coordinator.completed)

    async def test_failure_remains_retryable(self) -> None:
        coordinator = ShutdownCoordinator()
        teardown = AsyncMock(side_effect=[RuntimeError("boom"), None])
        coordinator.set_teardown(teardown)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            await coordinator.run_teardown()
        self.assertFalse(coordinator.completed)

        await coordinator.run_teardown()
        await coordinator.run_teardown()

        self.assertEqual(teardown.await_count, 2)
        self.assertTrue(coordinator.completed)

    async def test_new_lifecycle_resets_completion(self) -> None:
        coordinator = ShutdownCoordinator()
        first = AsyncMock()
        second = AsyncMock()

        coordinator.set_teardown(first)
        await coordinator.run_teardown()
        coordinator.set_teardown(second)
        await coordinator.run_teardown()

        first.assert_awaited_once()
        second.assert_awaited_once()


class TestCoreClose(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        core_api._shutdown_task = None

    async def test_close_cleans_then_notifies_then_exits(self) -> None:
        server = MagicMock()
        server.should_exit = False
        events: list[str] = []

        async def teardown() -> None:
            events.append("teardown")

        async def send(**_kwargs: object) -> bool:
            events.append("ready")
            return True

        with (
            patch.object(
                core_api.shutdown_coordinator,
                "run_teardown",
                side_effect=teardown,
            ),
            patch.object(core_api.Publisher, "send", side_effect=send) as publisher_send,
            patch.object(core_api.Config, "server", server),
            patch.object(core_api, "is_backend_dev_mode", return_value=False),
        ):
            result = await core_api.close()
            self.assertIsNotNone(core_api._shutdown_task)
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        self.assertEqual(result.code, 200)
        self.assertEqual(events, ["teardown", "ready"])
        self.assertTrue(server.should_exit)
        publisher_send.assert_awaited_once_with(
            id=protocol.ID_MAIN,
            type=protocol.BACKEND_SHUTDOWN_READY,
        )

    async def test_teardown_failure_skips_ready_and_exit(self) -> None:
        server = MagicMock()
        server.should_exit = False

        with (
            patch.object(
                core_api.shutdown_coordinator,
                "run_teardown",
                new_callable=AsyncMock,
                side_effect=RuntimeError("teardown failed"),
            ),
            patch.object(core_api.Publisher, "send", new_callable=AsyncMock) as send,
            patch.object(core_api.Config, "server", server),
            patch.object(core_api, "is_backend_dev_mode", return_value=False),
        ):
            await core_api.close()
            self.assertIsNotNone(core_api._shutdown_task)
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        send.assert_not_awaited()
        self.assertFalse(server.should_exit)
    async def test_repeated_close_reuses_running_task(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_shutdown() -> None:
            started.set()
            await release.wait()

        with patch.object(core_api, "_shutdown_backend", side_effect=slow_shutdown):
            first = await core_api.close()
            await started.wait()
            second = await core_api.close()
            release.set()
            self.assertIsNotNone(core_api._shutdown_task)
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.message, "关闭流程已在进行中")

    async def test_dev_mode_only_stops_tasks(self) -> None:
        server = MagicMock()
        server.should_exit = False

        with (
            patch.object(
                core_api.shutdown_coordinator,
                "run_teardown",
                new_callable=AsyncMock,
            ) as teardown,
            patch.object(
                core_api.TaskManager,
                "stop_task",
                new_callable=AsyncMock,
            ) as stop_task,
            patch.object(
                core_api.System,
                "cancel_power_task",
                new_callable=AsyncMock,
            ),
            patch.object(core_api.Publisher, "send", new_callable=AsyncMock) as send,
            patch.object(core_api.Config, "server", server),
            patch.object(core_api, "is_backend_dev_mode", return_value=True),
        ):
            await core_api.close()
            self.assertIsNotNone(core_api._shutdown_task)
            await asyncio.wait_for(core_api._shutdown_task, timeout=1)

        teardown.assert_not_awaited()
        stop_task.assert_awaited_once_with("ALL")
        send.assert_awaited_once_with(
            id=protocol.ID_MAIN,
            type=protocol.BACKEND_SHUTDOWN_READY,
        )
        self.assertFalse(server.should_exit)
