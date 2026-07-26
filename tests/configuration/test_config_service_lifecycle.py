from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app.core.config_service import ConfigService


class TestConfigServiceLifecycle(IsolatedAsyncioTestCase):
    async def test_concurrent_initialize_is_coalesced_per_instance(self) -> None:
        service = ConfigService()
        migration_started = asyncio.Event()
        release_migration = asyncio.Event()

        async def blocking_migration() -> None:
            migration_started.set()
            await release_migration.wait()

        register = Mock()
        unregister = Mock()
        configure_hooks = Mock()
        configure_observer = Mock()
        shutdown_runtime = AsyncMock()

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "shadow"),
            patch.object(service, "_register_legacy_codecs", register),
            patch.object(service, "_unregister_legacy_codecs", unregister),
            patch.object(
                service,
                "_shadow_migrate_existing",
                side_effect=blocking_migration,
            ),
            patch(
                "app.core.config_service.configure_outbox_hooks",
                configure_hooks,
            ),
            patch(
                "app.core.config_service.configure_config_save_observer",
                configure_observer,
            ),
            patch(
                "app.core.config_service.shutdown_runtime",
                shutdown_runtime,
            ),
        ):
            first = asyncio.create_task(service.initialize())
            await migration_started.wait()
            second = asyncio.create_task(service.initialize())
            await asyncio.sleep(0)

            self.assertFalse(second.done())
            release_migration.set()
            await asyncio.gather(first, second)

            self.assertTrue(service._initialized)
            register.assert_called_once_with()
            self.assertEqual(configure_hooks.call_count, 1)
            self.assertEqual(configure_observer.call_count, 1)

            await service.shutdown()

        unregister.assert_called_once_with()
        shutdown_runtime.assert_awaited_once_with()
        self.assertFalse(service._initialized)

    async def test_second_instance_cannot_steal_or_clear_global_hooks(self) -> None:
        owner = ConfigService()
        contender = ConfigService()
        configure_hooks = Mock()
        configure_observer = Mock()
        shutdown_runtime = AsyncMock()

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "off"),
            patch(
                "app.core.config_service.configure_outbox_hooks",
                configure_hooks,
            ),
            patch(
                "app.core.config_service.configure_config_save_observer",
                configure_observer,
            ),
            patch(
                "app.core.config_service.shutdown_runtime",
                shutdown_runtime,
            ),
        ):
            await owner.initialize()
            self.assertEqual(configure_hooks.call_count, 1)
            self.assertEqual(configure_observer.call_count, 1)

            with self.assertRaisesRegex(RuntimeError, "another ConfigService"):
                await contender.initialize()

            await contender.shutdown()
            self.assertEqual(configure_hooks.call_count, 1)
            self.assertEqual(configure_observer.call_count, 1)
            shutdown_runtime.assert_not_awaited()

            await owner.shutdown()
            await contender.initialize()
            await contender.shutdown()

        self.assertEqual(configure_hooks.call_count, 4)
        self.assertEqual(configure_observer.call_count, 4)
        self.assertEqual(shutdown_runtime.await_count, 2)

    async def test_failed_initialize_releases_process_owner(self) -> None:
        failed = ConfigService()
        successor = ConfigService()
        configure_hooks = Mock()
        configure_observer = Mock()
        failed_unregister = Mock()
        successor_unregister = Mock()
        shutdown_runtime = AsyncMock()

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "shadow"),
            patch.object(failed, "_register_legacy_codecs", Mock()),
            patch.object(failed, "_unregister_legacy_codecs", failed_unregister),
            patch.object(
                failed,
                "_shadow_migrate_existing",
                AsyncMock(side_effect=OSError("migration failed")),
            ),
            patch.object(successor, "_register_legacy_codecs", Mock()),
            patch.object(
                successor,
                "_unregister_legacy_codecs",
                successor_unregister,
            ),
            patch.object(successor, "_shadow_migrate_existing", AsyncMock()),
            patch(
                "app.core.config_service.configure_outbox_hooks",
                configure_hooks,
            ),
            patch(
                "app.core.config_service.configure_config_save_observer",
                configure_observer,
            ),
            patch(
                "app.core.config_service.shutdown_runtime",
                shutdown_runtime,
            ),
        ):
            with self.assertRaisesRegex(OSError, "migration failed"):
                await failed.initialize()

            self.assertFalse(failed._initialized)
            self.assertEqual(failed._lifecycle_state, "idle")
            failed_unregister.assert_called_once_with()
            self.assertEqual(configure_hooks.call_count, 2)
            configure_observer.assert_not_called()

            await successor.initialize()
            await successor.shutdown()

        successor_unregister.assert_called_once_with()
        shutdown_runtime.assert_awaited_once_with()

    async def test_shutdown_and_reinitialize_are_serialized(self) -> None:
        service = ConfigService()
        shutdown_started = asyncio.Event()
        release_shutdown = asyncio.Event()

        async def blocking_shutdown() -> None:
            shutdown_started.set()
            await release_shutdown.wait()

        configure_hooks = Mock()
        configure_observer = Mock()
        shutdown_runtime = AsyncMock(side_effect=blocking_shutdown)

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "off"),
            patch(
                "app.core.config_service.configure_outbox_hooks",
                configure_hooks,
            ),
            patch(
                "app.core.config_service.configure_config_save_observer",
                configure_observer,
            ),
            patch(
                "app.core.config_service.shutdown_runtime",
                shutdown_runtime,
            ),
        ):
            await service.initialize()
            stopping = asyncio.create_task(service.shutdown())
            await shutdown_started.wait()
            restarting = asyncio.create_task(service.initialize())
            await asyncio.sleep(0)

            self.assertFalse(restarting.done())
            release_shutdown.set()
            await stopping
            await restarting

            self.assertTrue(service._initialized)
            self.assertEqual(service._lifecycle_state, "initialized")
            self.assertEqual(configure_hooks.call_count, 3)
            self.assertEqual(configure_observer.call_count, 3)

            await service.shutdown()

        self.assertFalse(service._initialized)
        self.assertEqual(shutdown_runtime.await_count, 2)

class TestMainTimerResilience(IsolatedAsyncioTestCase):
    """验证定时循环的单项故障隔离、守护重启与关闭回收。"""

    async def test_second_loop_continues_after_single_item_failure(self) -> None:
        from app.core.timer import _MainTimer

        timer = _MainTimer()
        timer.timed_start = AsyncMock(side_effect=[OSError("write failed"), None])
        timer._run_arknights_scheduled_task = AsyncMock()
        timer.check_game_sign = AsyncMock()
        sleep_calls = 0

        async def stop_after_two_iterations(_delay: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with patch("app.core.timer.asyncio.sleep", new=stop_after_two_iterations):
            with self.assertRaises(asyncio.CancelledError):
                await timer.second_task()

        self.assertEqual(timer.timed_start.await_count, 2)
        self.assertEqual(timer._run_arknights_scheduled_task.await_count, 2)
        self.assertEqual(timer.check_game_sign.await_count, 2)

    async def test_hour_loop_continues_after_single_upload_failure(self) -> None:
        from app.core.timer import _MainTimer

        timer = _MainTimer()
        timer._upload_version_statistics = AsyncMock(
            side_effect=[OSError("write failed"), None]
        )
        sleep_calls = 0

        async def stop_after_two_iterations(_delay: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with patch("app.core.timer.asyncio.sleep", new=stop_after_two_iterations):
            with self.assertRaises(asyncio.CancelledError):
                await timer.hour_task()

        self.assertEqual(timer._upload_version_statistics.await_count, 2)

    async def test_supervisor_restarts_unexpectedly_terminated_loop(self) -> None:
        from app.core.timer import _MainTimer

        timer = _MainTimer()
        restarted = asyncio.Event()
        attempts = 0

        async def loop_factory() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("unexpected stop")
            restarted.set()
            await asyncio.Event().wait()

        with patch("app.core.timer.TIMER_RESTART_DELAY", 0):
            task = asyncio.create_task(timer._supervise("测试定时器", loop_factory))
            await asyncio.wait_for(restarted.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(attempts, 2)

    async def test_stop_cancels_and_awaits_both_loops(self) -> None:
        from app.core.timer import _MainTimer

        timer = _MainTimer()
        timer.started = True
        second_cancelled = asyncio.Event()
        hour_cancelled = asyncio.Event()

        async def wait_until_cancelled(marker: asyncio.Event) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                marker.set()
                raise

        timer.second_timer = asyncio.create_task(wait_until_cancelled(second_cancelled))
        timer.hour_timer = asyncio.create_task(wait_until_cancelled(hour_cancelled))
        await asyncio.sleep(0)

        await timer.stop()

        self.assertTrue(second_cancelled.is_set())
        self.assertTrue(hour_cancelled.is_set())
        self.assertTrue(timer.second_timer.done())
        self.assertTrue(timer.hour_timer.done())
        self.assertFalse(timer.started)
