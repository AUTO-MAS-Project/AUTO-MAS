from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.plugins.manager import _LocalPluginProject, _PluginManager


class BundledRuntimeEditablePolicyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app_root = Path(self.temporary_directory.name)
        self.plugins_dir = self.app_root / "plugins"
        self.plugins_dir.mkdir(parents=True)
        self.manager = object.__new__(_PluginManager)
        self.manager.plugins_dir = self.plugins_dir
        self.locked_project = _LocalPluginProject(
            project_dir=self.plugins_dir / "official_source",
            distribution_name="official.locked-plugin",
            entry_point_names={"locked_plugin"},
        )
        self.local_project = _LocalPluginProject(
            project_dir=self.plugins_dir / "local_project",
            distribution_name="user-local-plugin",
            entry_point_names={"local_plugin"},
        )
        self.previous_owner_token = os.environ.get("AUTO_MAS_BACKEND_OWNER_TOKEN")
        self.previous_dev = os.environ.get("AUTO_MAS_DEV")
        os.environ["AUTO_MAS_BACKEND_OWNER_TOKEN"] = "managed-production-backend"
        os.environ.pop("AUTO_MAS_DEV", None)
        self._write_bundled_lock()

    def tearDown(self) -> None:
        if self.previous_owner_token is None:
            os.environ.pop("AUTO_MAS_BACKEND_OWNER_TOKEN", None)
        else:
            os.environ["AUTO_MAS_BACKEND_OWNER_TOKEN"] = self.previous_owner_token
        if self.previous_dev is None:
            os.environ.pop("AUTO_MAS_DEV", None)
        else:
            os.environ["AUTO_MAS_DEV"] = self.previous_dev
        self.temporary_directory.cleanup()

    def _write_bundled_lock(self) -> None:
        marker_path = self.app_root / "res" / "integration-snapshot.json"
        marker_path.parent.mkdir(parents=True)
        marker_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "deployment_mode": "bundled-snapshot",
                    "wheelhouse_contract": {"plugin_distribution_count": 23},
                }
            ),
            encoding="utf-8",
        )
        lock_entries = [
            {
                "distribution": "official.locked-plugin",
                "version": "1.2.3",
                "scope": "plugin",
            }
        ]
        lock_entries.extend(
            {
                "distribution": f"locked-helper-{index}",
                "version": "1.0.0",
                "scope": "plugin",
            }
            for index in range(22)
        )
        lock_bytes = json.dumps(
            {
                "schema_version": 1,
                "install_contract": {"protected_host_distributions": ["host-runtime"]},
                "host_runtime": [
                    {
                        "distribution": "host-runtime",
                        "version": "4.5.6",
                        "scope": "host_runtime",
                    }
                ],
                "plugins": lock_entries,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        wheels_dir = self.plugins_dir / "wheels"
        wheels_dir.mkdir(parents=True)
        (wheels_dir / "runtime-lock.json").write_bytes(lock_bytes)
        (wheels_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "artifact_scope": "complete-windows-x64-runtime-wheelhouse",
                    "runtime_lock": {
                        "filename": "runtime-lock.json",
                        "size_bytes": len(lock_bytes),
                        "sha256": hashlib.sha256(lock_bytes).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _locked_entry_point(*, editable: bool = False) -> SimpleNamespace:
        return SimpleNamespace(
            distribution="official-locked_plugin",
            version="1.2.3",
            editable_project_path=Path("editable") if editable else None,
        )

    def test_loads_verified_plugin_distribution_set_from_runtime_lock(self) -> None:
        bundled_lock = self.manager._load_bundled_plugin_lock()

        self.assertIsNotNone(bundled_lock)
        assert bundled_lock is not None
        self.assertEqual(bundled_lock.versions["official_locked_plugin"], "1.2.3")
        self.assertEqual(len(bundled_lock.versions), 23)
        self.assertEqual(bundled_lock.protected_host_distributions, {"host_runtime"})

    async def test_skips_locked_source_but_keeps_user_local_editable_install(self) -> None:
        install = AsyncMock()
        with (
            patch.object(
                self.manager,
                "_collect_local_plugin_projects",
                return_value=[self.locked_project, self.local_project],
            ),
            patch.object(self.manager, "_should_install_local_project", return_value=(True, "test")),
            patch.object(self.manager, "_install_local_project_editable", install),
            patch(
                "app.plugins.manager.get_installed_plugin_entry_points",
                return_value={"locked_plugin": [self._locked_entry_point()]},
            ),
        ):
            await self.manager._ensure_local_projects_installed()

        install.assert_awaited_once_with(self.local_project, "test")

    async def test_explicit_development_mode_keeps_editable_behavior(self) -> None:
        os.environ["AUTO_MAS_DEV"] = "1"
        install = AsyncMock()
        with (
            patch.object(
                self.manager,
                "_collect_local_plugin_projects",
                return_value=[self.locked_project, self.local_project],
            ),
            patch.object(self.manager, "_should_install_local_project", return_value=(True, "dev")),
            patch.object(self.manager, "_install_local_project_editable", install),
            patch("app.plugins.manager.get_installed_plugin_entry_points", return_value={}),
        ):
            await self.manager._ensure_local_projects_installed()

        self.assertEqual(install.await_count, 2)

    def test_rejects_manifest_runtime_lock_hash_mismatch(self) -> None:
        runtime_lock_path = self.plugins_dir / "wheels" / "runtime-lock.json"
        runtime_lock_path.write_bytes(runtime_lock_path.read_bytes() + b" ")

        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.manager._load_bundled_plugin_lock()

    def test_rejects_existing_editable_override_of_locked_project(self) -> None:
        bundled_lock = self.manager._load_bundled_plugin_lock()
        assert bundled_lock is not None
        with (
            patch(
                "app.plugins.manager.get_installed_plugin_entry_points",
                return_value={"locked_plugin": [self._locked_entry_point(editable=True)]},
            ),
            self.assertRaisesRegex(RuntimeError, "editable/版本漂移"),
        ):
            self.manager._assert_locked_projects_unchanged(
                [self.locked_project], bundled_lock
            )

    def test_rejects_protected_host_distribution_in_plugin_target(self) -> None:
        bundled_lock = self.manager._load_bundled_plugin_lock()
        assert bundled_lock is not None
        dist_info = self.plugins_dir / "pypi" / "site-packages" / "host_runtime-4.5.6.dist-info"
        dist_info.mkdir(parents=True)
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: host-runtime\nVersion: 4.5.6\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "覆盖了受保护宿主依赖"):
            self.manager._assert_protected_host_not_shadowed(bundled_lock)


if __name__ == "__main__":
    unittest.main()
