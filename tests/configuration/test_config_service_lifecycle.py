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
