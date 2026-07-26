from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock, patch

_CONFIG_SERVICE_MODULE: ModuleType
_CONFIG_IMPORT_TEMP: tempfile.TemporaryDirectory[str]


def setUpModule() -> None:
    """Import app.core only while cwd points at an isolated test profile."""
    global _CONFIG_SERVICE_MODULE, _CONFIG_IMPORT_TEMP
    # Bind the process-global log sink before entering the disposable profile.
    # Loguru keeps its Windows file handle open for the process lifetime, so
    # importing it inside TemporaryDirectory would make isolated test cleanup
    # fail with WinError 32 even though configuration stayed isolated.
    importlib.import_module("app.utils")
    _CONFIG_IMPORT_TEMP = tempfile.TemporaryDirectory()
    previous_cwd = Path.cwd()
    try:
        os.chdir(_CONFIG_IMPORT_TEMP.name)
        _CONFIG_SERVICE_MODULE = importlib.import_module("app.core.config_service")
    finally:
        os.chdir(previous_cwd)


def tearDownModule() -> None:
    _CONFIG_IMPORT_TEMP.cleanup()


def _new_config_service():
    return _CONFIG_SERVICE_MODULE.ConfigService()


class AuthoritativeGateTest(unittest.IsolatedAsyncioTestCase):
    def test_authoritative_mode_is_ready_without_legacy_runtime(self) -> None:
        service = _new_config_service()
        with patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"):
            service.assert_startup_mode_ready()

    def test_shadow_mode_remains_available(self) -> None:
        service = _new_config_service()
        with patch("app.core.config_service.CONFIG_V2_MODE", "shadow"):
            service.assert_startup_mode_ready()

    async def test_initialize_registers_only_native_process_hooks(self) -> None:
        service = _new_config_service()
        configure_outbox = Mock()
        configure_observer = Mock()
        register_codecs = Mock()
        unregister_codecs = Mock()

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
            patch(
                "app.core.config_service.configure_outbox_hooks",
                configure_outbox,
            ),
            patch(
                "app.core.config_service.configure_config_save_observer",
                configure_observer,
            ),
            patch.object(service, "_register_legacy_codecs", register_codecs),
            patch.object(
                service,
                "_unregister_legacy_codecs",
                unregister_codecs,
            ),
            patch(
                "app.core.config_service.shutdown_runtime",
                AsyncMock(),
            ),
        ):
            await service.initialize()
            await service.shutdown()

        self.assertEqual(configure_outbox.call_count, 2)
        configure_observer.assert_not_called()
        register_codecs.assert_not_called()
        unregister_codecs.assert_called_once_with()

    async def test_legacy_backed_authoritative_load_and_save_are_blocked(self) -> None:
        service = _new_config_service()
        adapter_write = Mock()
        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
            patch(
                "app.core.config_service.legacy_adapter.shadow_write",
                adapter_write,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "initialized by NativeConfigFacade",
            ):
                await service._authoritative_load()
            with self.assertRaisesRegex(
                RuntimeError,
                "rejects legacy JSON-first saves",
            ):
                await service.save_config(Path("Config.json"), {"secret": "not-used"})

        adapter_write.assert_not_called()

    def test_snapshot_failure_prevents_mode_gate_and_startup_progress(self) -> None:
        from main import prepare_configuration_startup

        mode_gate = Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "app.configuration.compat.ensure_legacy_original_snapshot",
                    side_effect=OSError("snapshot failed"),
                ),
                patch(
                    "app.configuration.assert_config_v2_startup_mode_ready",
                    mode_gate,
                ),
            ):
                with self.assertRaisesRegex(OSError, "snapshot failed"):
                    prepare_configuration_startup(Path(temp_dir) / "config")

        mode_gate.assert_not_called()

    def test_main_propagates_startup_gate_failure(self) -> None:
        from main import main

        with (
            patch("main.is_admin", return_value=True),
            patch(
                "main.prepare_configuration_startup",
                side_effect=OSError("snapshot failed"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "snapshot failed"):
                main()

    def test_main_orders_snapshot_before_config_import_and_plugins(self) -> None:
        source = (Path(__file__).parents[2] / "main.py").read_text(encoding="utf-8")
        snapshot_call = source.index(
            'prepare_configuration_startup(Path.cwd() / "config")'
        )
        plugin_package_import = source.index(
            "from app.plugins.uv_backend import ensure_uv",
            snapshot_call,
        )
        core_security_import = source.index(
            "from app.core.http_security import configure_local_http_security",
            snapshot_call,
        )
        config_import = source.index("from app.core import Config", snapshot_call)
        legacy_init = source.index("await Config.init_config()", config_import)
        plugin_start = source.index("await PluginManager.start", legacy_init)

        self.assertLess(snapshot_call, plugin_package_import)
        self.assertLess(snapshot_call, core_security_import)
        self.assertLess(snapshot_call, config_import)
        self.assertLess(config_import, legacy_init)
        self.assertLess(legacy_init, plugin_start)


if __name__ == "__main__":
    unittest.main()
