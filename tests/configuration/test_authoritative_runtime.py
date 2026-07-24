"""Config v2 authoritative bootstrap, restart and durable transaction tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.configuration.authoritative as authoritative_module
import app.configuration.persistence.generation_store as generation_store_module
from app.configuration import config_manager
from app.configuration.authoritative import (
    AUTHORITATIVE_STORE_DIRECTORY_NAME,
    AuthoritativeConfigurationRuntime,
    RollbackExportError,
)
from app.configuration.persistence import (
    GenerationIntegrityError,
    GenerationPathLengthError,
)
from app.configuration.production import (
    PRODUCTION_ROOT_FILES,
    legacy_production_roots_to_wire,
)


class AuthoritativeConfigurationRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_path_budget_fails_before_r6_snapshot_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            with (
                patch.object(
                    authoritative_module,
                    "ensure_legacy_original_snapshot",
                ) as snapshot,
                patch.object(
                    generation_store_module,
                    "_uses_windows_legacy_path_limit",
                    return_value=True,
                ),
                patch.object(
                    generation_store_module,
                    "WINDOWS_SAFE_PATH_LIMIT",
                    1,
                ),
                self.assertRaises(GenerationPathLengthError),
            ):
                await runtime.initialize()

            snapshot.assert_not_called()
            self.assertFalse(config_dir.exists())
            self.assertFalse(runtime._owns_hook)
            self.assertIsNone(runtime._roots)

    async def test_first_start_migrates_then_restart_ignores_mutable_legacy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            legacy_path = config_dir / "Config.json"
            legacy_path.write_text(
                json.dumps({"Function": {"IfSilence": True}}),
                encoding="utf-8",
            )

            first = AuthoritativeConfigurationRuntime(config_dir)
            try:
                state = await first.initialize()
                self.assertEqual(state.initialized_from, "legacy-original")
                self.assertTrue(first.roots.config.Function.IfSilence)
                self.assertEqual(state.revision, 1)
                self.assertIn(
                    state.source_snapshot_generation,
                    str(first.store_directory),
                )
            finally:
                first.close()

            legacy_path.write_text(
                json.dumps({"Function": {"IfSilence": False}}),
                encoding="utf-8",
            )
            second = AuthoritativeConfigurationRuntime(config_dir)
            try:
                state = await second.initialize()
                self.assertEqual(state.initialized_from, "current-generation")
                self.assertTrue(second.roots.config.Function.IfSilence)
                self.assertEqual(state.revision, 1)
            finally:
                second.close()

    async def test_live_transaction_is_durable_before_commit_and_restarts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            try:
                initial = await runtime.initialize()
                async with config_manager.transaction():
                    runtime.roots.config.Function.IfSilence = True
                    await runtime.roots.config.commit()
                self.assertTrue(runtime.roots.config.Function.IfSilence)
                self.assertEqual(initial.revision, 1)
                self.assertEqual(runtime.state.revision, 2)
            finally:
                runtime.close()

            restarted = AuthoritativeConfigurationRuntime(config_dir)
            try:
                state = await restarted.initialize()
                self.assertEqual(state.revision, 2)
                self.assertTrue(restarted.roots.config.Function.IfSilence)
            finally:
                restarted.close()

    async def test_corrupt_current_fails_closed_without_legacy_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            try:
                await runtime.initialize()
                current_path = runtime.store_directory / "CURRENT"
            finally:
                runtime.close()

            current_path.write_text("{broken", encoding="utf-8")
            (config_dir / "Config.json").write_text(
                json.dumps({"Function": {"IfSilence": True}}),
                encoding="utf-8",
            )
            restarted = AuthoritativeConfigurationRuntime(config_dir)
            with self.assertRaises(GenerationIntegrityError):
                await restarted.initialize()
            self.assertFalse(restarted._owns_hook)
            self.assertIsNone(restarted._roots)

    async def test_store_path_is_bound_to_immutable_snapshot_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            try:
                state = await runtime.initialize()
                self.assertEqual(
                    runtime.store_directory.parent.name,
                    AUTHORITATIVE_STORE_DIRECTORY_NAME,
                )
                self.assertEqual(
                    runtime.store_directory.name,
                    state.source_snapshot_generation,
                )
            finally:
                runtime.close()

    async def test_r6_rollback_bundle_is_complete_and_never_overwritten(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            export_parent = Path(temp_dir) / "rollback-output"
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            try:
                await runtime.initialize()
                async with config_manager.transaction():
                    runtime.roots.config.Function.IfSilence = True
                    await runtime.roots.config.commit()

                bundle = runtime.export_r6_rollback_bundle(export_parent)
                self.assertTrue(bundle.is_dir())
                self.assertEqual(
                    {path.name for path in bundle.iterdir()},
                    {*PRODUCTION_ROOT_FILES.values(), "manifest.json"},
                )
                exported = {
                    file_name: json.loads(
                        (bundle / file_name).read_text(encoding="utf-8")
                    )
                    for file_name in PRODUCTION_ROOT_FILES.values()
                }
                legacy_production_roots_to_wire(exported)
                self.assertTrue(
                    exported["Config.json"]["Function"]["IfSilence"]
                )

                before = {
                    path.name: path.read_bytes()
                    for path in bundle.iterdir()
                }
                with self.assertRaises(RollbackExportError):
                    runtime.export_r6_rollback_bundle(export_parent)
                self.assertEqual(
                    {
                        path.name: path.read_bytes()
                        for path in bundle.iterdir()
                    },
                    before,
                )
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
