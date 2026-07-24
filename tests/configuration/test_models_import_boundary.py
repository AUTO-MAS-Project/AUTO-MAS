from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def run_isolated(
    source: str,
    *,
    authoritative: bool = False,
    cwd: Path = REPOSITORY_ROOT,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    if authoritative:
        environment["AUTO_MAS_CONFIG_V2_MODE"] = "authoritative"
    else:
        environment.pop("AUTO_MAS_CONFIG_V2_MODE", None)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


class TestModelsImportBoundary(TestCase):
    def test_schema_submodule_does_not_load_legacy_config(self) -> None:
        result = run_isolated(
            """
            import sys
            from app.models.schema import WSEnvelope

            assert WSEnvelope is not None
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """,
            authoritative=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_package_level_schema_symbol_remains_lazy(self) -> None:
        result = run_isolated(
            """
            import sys
            from app.models import WSEnvelope

            assert WSEnvelope is not None
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_package_level_config_symbol_still_resolves(self) -> None:
        result = run_isolated(
            """
            from app.models import ConfigBase

            assert isinstance(ConfigBase, type)
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_package_attribute_does_not_probe_legacy_modules(self) -> None:
        result = run_isolated(
            """
            import sys
            import app.models as models

            assert getattr(models, "not_a_real_model_symbol", None) is None
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """,
            authoritative=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_ws_bridge_does_not_import_legacy_config(self) -> None:
        result = run_isolated(
            """
            import asyncio
            import sys

            from app.core import Config
            from app.core.ws.bootstrap import init_ws_core, shutdown_ws_core

            assert type(Config).__module__ == "app.core.native_config"

            async def main():
                await init_ws_core()
                await Config.send_json({"type": "noop"})
                await Config.send_websocket_message(
                    id="PluginSystem",
                    type="Update",
                    data={"kind": "noop"},
                )
                await shutdown_ws_core()

            asyncio.run(main())
            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """,
            authoritative=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_emulator_manager_does_not_import_legacy_config(
        self,
    ) -> None:
        result = run_isolated(
            """
            import sys

            from app.core import EmulatorManager

            assert EmulatorManager is not None
            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """,
            authoritative=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_plugin_package_keeps_lightweight_exports_lazy(
        self,
    ) -> None:
        result = run_isolated(
            """
            import sys
            import app.plugins as plugins

            blocked = (
                "app.core.config",
                "app.models.ConfigBase",
                "app.models.config",
            )
            assert set(plugins.__all__) == set(plugins._LAZY_EXPORTS)
            assert not any(name in sys.modules for name in blocked)

            from app.plugins import (
                EventBus,
                PluginConfigStore,
                PluginEventFactory,
                PluginEventNames,
            )

            assert EventBus is not None
            assert PluginConfigStore is not None
            assert PluginEventFactory is not None
            assert PluginEventNames is not None
            assert not any(name in sys.modules for name in blocked)
            """,
            authoritative=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_plugin_manager_import_isolated_from_worktree(
        self,
    ) -> None:
        # PluginManager creates runtime paths from cwd.  Put the child process
        # in a disposable directory so this import boundary test neither
        # writes to the worktree nor keeps a Windows log handle open during
        # directory cleanup.
        with TemporaryDirectory(prefix="automas-plugin-manager-") as directory:
            result = run_isolated(
                """
                import sys

                from app.plugins import PluginManager

                assert PluginManager is not None
                assert "app.core.config" not in sys.modules
                assert "app.models.ConfigBase" not in sys.modules
                assert "app.models.config" not in sys.modules
                """,
                authoritative=True,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
