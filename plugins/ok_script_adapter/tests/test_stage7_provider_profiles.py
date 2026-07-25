from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.plugins import ScriptAdapterPlugin
from ok_script_adapter import providers as providers_module
from ok_script_adapter.common.provider import OkScriptProvider
from ok_script_adapter.plugin import Plugin


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PLUGIN_ROOT / "src" / "ok_script_adapter"


class ProviderProfileRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        providers_module.clear_ok_script_provider_cache()

    def tearDown(self) -> None:
        providers_module.clear_ok_script_provider_cache()

    @staticmethod
    def _spec(resource_name: str):
        return next(
            item
            for item in providers_module.OK_SCRIPT_PROVIDER_PROFILES
            if item.resource_name == resource_name
        )

    @staticmethod
    def _provider(resource_name: str) -> OkScriptProvider:
        return OkScriptProvider(
            resource_name=resource_name,
            display_name=resource_name,
            exe_name="ok-script.exe",
            config_dir="configs",
            log_file="logs/ok-script.log",
            pythonw_path="pythonw.exe",
            track_process_name="pythonw.exe",
            game_process_name="Game.exe",
            running_status="running",
            fatal_patterns=(),
            success_patterns=(),
            max_task_index=0,
            task_options=(),
            config_schema_module="",
            config_info_loader="",
        )

    @staticmethod
    def _module_for(
        profile: providers_module.ProviderProfileSpec,
        provider: OkScriptProvider,
        *,
        abi_version: int | None = None,
    ) -> SimpleNamespace:
        attributes = {
            "OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION": (
                profile.abi_version if abi_version is None else abi_version
            ),
            profile.provider_attribute: provider,
        }
        return SimpleNamespace(**attributes)

    def test_status_query_is_lazy_and_matching_lookup_loads_one_profile(self) -> None:
        profile = self._spec("ok-ww")
        provider = self._provider(profile.resource_name)
        module = self._module_for(profile, provider)

        with patch.object(
            providers_module.importlib,
            "import_module",
            return_value=module,
        ) as import_module:
            statuses = providers_module.list_ok_script_provider_profile_statuses()

            self.assertEqual(
                [status.state for status in statuses],
                ["pending", "pending", "pending"],
            )
            import_module.assert_not_called()

            self.assertIs(
                providers_module.get_ok_script_provider(profile.resource_name),
                provider,
            )
            import_module.assert_called_once_with(profile.module_name)

        self.assertTrue(
            providers_module.get_ok_script_provider_profile_status(
                profile.resource_name
            ).available
        )
        self.assertEqual(
            providers_module.get_ok_script_provider_profile_status("ok-ef").state,
            "pending",
        )

    def test_import_failure_disables_only_the_failing_profile(self) -> None:
        failing_profile = self._spec("ok-ef")
        working_profile = self._spec("ok-ww")
        working_provider = self._provider(working_profile.resource_name)
        working_module = self._module_for(working_profile, working_provider)

        def import_module(module_name: str) -> SimpleNamespace:
            if module_name == failing_profile.module_name:
                raise ImportError("broken profile")
            self.assertEqual(module_name, working_profile.module_name)
            return working_module

        with patch.object(
            providers_module.importlib,
            "import_module",
            side_effect=import_module,
        ) as import_profile:
            self.assertIsNone(
                providers_module.get_ok_script_provider(failing_profile.resource_name)
            )
            self.assertIs(
                providers_module.get_ok_script_provider(working_profile.resource_name),
                working_provider,
            )
            self.assertIsNone(
                providers_module.get_ok_script_provider(failing_profile.resource_name)
            )

        self.assertEqual(import_profile.call_count, 2)
        failure_status = providers_module.get_ok_script_provider_profile_status(
            failing_profile.resource_name
        )
        self.assertEqual(failure_status.state, "disabled")
        self.assertIn("ImportError", failure_status.detail)
        self.assertTrue(
            providers_module.get_ok_script_provider_profile_status(
                working_profile.resource_name
            ).available
        )

    def test_abi_mismatch_disables_only_the_matching_profile(self) -> None:
        profile = self._spec("ok-nte")
        provider = self._provider(profile.resource_name)
        incompatible_module = self._module_for(
            profile,
            provider,
            abi_version=profile.abi_version + 1,
        )

        with patch.object(
            providers_module.importlib,
            "import_module",
            return_value=incompatible_module,
        ):
            self.assertIsNone(
                providers_module.get_ok_script_provider(profile.resource_name)
            )

        status = providers_module.get_ok_script_provider_profile_status(
            profile.resource_name
        )
        self.assertEqual(status.state, "disabled")
        self.assertIn("ABI mismatch", status.detail)

    def test_cache_clear_allows_a_failed_profile_to_recover(self) -> None:
        profile = self._spec("ok-ef")
        provider = self._provider(profile.resource_name)
        module = self._module_for(profile, provider)
        attempts = 0

        def import_module(module_name: str) -> SimpleNamespace:
            nonlocal attempts
            self.assertEqual(module_name, profile.module_name)
            attempts += 1
            if attempts == 1:
                raise ImportError("transient failure")
            return module

        with patch.object(
            providers_module.importlib,
            "import_module",
            side_effect=import_module,
        ):
            self.assertIsNone(
                providers_module.get_ok_script_provider(profile.resource_name)
            )
            self.assertIsNone(
                providers_module.get_ok_script_provider(profile.resource_name)
            )
            self.assertEqual(attempts, 1)

            providers_module.clear_ok_script_provider_cache(profile.resource_name)
            self.assertEqual(
                providers_module.get_ok_script_provider_profile_status(
                    profile.resource_name
                ).state,
                "pending",
            )
            self.assertIs(
                providers_module.get_ok_script_provider(profile.resource_name),
                provider,
            )

        self.assertEqual(attempts, 2)


class ProviderProfileLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_stop_clears_cache_when_parent_stop_fails(self) -> None:
        providers_module.clear_ok_script_provider_cache()
        self.addCleanup(providers_module.clear_ok_script_provider_cache)
        profile = next(
            item
            for item in providers_module.OK_SCRIPT_PROVIDER_PROFILES
            if item.resource_name == "ok-ww"
        )
        provider = ProviderProfileRegistryTest._provider(profile.resource_name)
        module = ProviderProfileRegistryTest._module_for(profile, provider)

        with patch.object(
            providers_module.importlib,
            "import_module",
            return_value=module,
        ):
            providers_module.get_ok_script_provider(profile.resource_name)

        parent_stop = AsyncMock(side_effect=RuntimeError("parent stop failed"))
        plugin = object.__new__(Plugin)
        with patch.object(
            ScriptAdapterPlugin,
            "on_stop",
            new=parent_stop,
        ):
            with self.assertRaisesRegex(RuntimeError, "parent stop failed"):
                await Plugin.on_stop(plugin, "reload")

        self.assertEqual(parent_stop.await_count, 1)
        self.assertEqual(parent_stop.await_args.args[-1], "reload")
        self.assertEqual(
            providers_module.get_ok_script_provider_profile_status(
                profile.resource_name
            ).state,
            "pending",
        )


class ProviderProfilePackageContractTest(unittest.TestCase):
    def test_single_distribution_and_wheel_resources_remain_declared(self) -> None:
        pyproject = (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        provider_registry = (PACKAGE_ROOT / "providers" / "__init__.py").read_text(
            encoding="utf-8"
        )
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(
            pyproject.count('ok_script_adapter = "ok_script_adapter.plugin:Plugin"'),
            1,
        )
        self.assertIn('[project.entry-points."auto_mas.plugins"]', pyproject)
        self.assertIn(
            'ok_script_adapter = ["frontend/*.json", "frontend/*.js", "frontend/*.css"]',
            pyproject,
        )
        for resource_name in ("manifest.json", "index.js", "index.css"):
            self.assertTrue(
                (PACKAGE_ROOT / "frontend" / resource_name).is_file(),
                resource_name,
            )

        self.assertIn("OK_SCRIPT_PROVIDER_PROFILES", provider_registry)
        self.assertIn("importlib.import_module", provider_registry)
        self.assertNotIn("from .okef import", provider_registry)
        self.assertNotIn("from .okww import", provider_registry)
        self.assertNotIn("from .oknte import", provider_registry)
        self.assertIn("single distribution", readme)
        self.assertIn("not supported yet", " ".join(readme.split()))

        for profile_file in ("okef.py", "okww.py", "oknte.py"):
            source = (PACKAGE_ROOT / "providers" / profile_file).read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION = 1",
                source,
            )


if __name__ == "__main__":
    unittest.main()
