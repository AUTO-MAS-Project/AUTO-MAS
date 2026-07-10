import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.plugins.event_bus import EventBus
from app.plugins.loader import PluginLoader, PluginRecord
from app.plugins.service_registry import ServiceRegistry


class PluginLoaderLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_unload_all_does_not_reload_soft_dependency_consumers(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            service = ServiceRegistry()
            loader = PluginLoader(
                events=EventBus(),
                plugins_dir=Path(temporary_dir),
                service=service,
            )
            loader.records = {
                "provider": PluginRecord(
                    instance_id="provider",
                    plugin_name="provider",
                    path=None,
                    status="active",
                    provides={"example.service"},
                ),
                "consumer": PluginRecord(
                    instance_id="consumer",
                    plugin_name="consumer",
                    path=None,
                    status="active",
                    wants={"example.service"},
                ),
            }
            service.bind("consumer", wants={"example.service"})
            service.set("example.service", object(), "provider")

            with (
                patch.object(loader, "load_instance", new_callable=AsyncMock) as load_instance,
                patch("app.plugins.loader.plugin_server.unregister_owner", new_callable=AsyncMock),
            ):
                await loader.unload_all()
                await asyncio.sleep(0)

            load_instance.assert_not_awaited()
            self.assertFalse(loader._pulse)
            self.assertTrue(loader._task is None or loader._task.done())
            self.assertEqual(
                {record.status for record in loader.records.values()},
                {"unloaded"},
            )


if __name__ == "__main__":
    unittest.main()
