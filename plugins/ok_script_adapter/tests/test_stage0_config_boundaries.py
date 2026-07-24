from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ok_script_adapter import plugin as plugin_module
from ok_script_adapter.adapter.autoproxy import OkScriptAutoProxyTask
from ok_script_adapter.common.provider import ok_script_mas_config_dir
from ok_script_adapter.plugin import Plugin
from ok_script_adapter.shell.manifest import inspect_ok_project
from ok_script_adapter.shell.runtime import OkConfigStore, OkShellRuntimeError

from project_fixtures import PROJECT_FIXTURE_SPECS, build_project_fixture


class _FakePluginScriptConfig:
    def __init__(self, type_key: str, user_ids: set[uuid.UUID]) -> None:
        self.type_key = type_key
        self.UserData = {user_id: object() for user_id in user_ids}

    def get(self, group: str, name: str) -> str:
        if (group, name) == ("Meta", "PluginTypeKey"):
            return self.type_key
        raise KeyError((group, name))


class ProjectFixtureCoverageTest(unittest.TestCase):
    def test_source_and_installed_fixtures_cover_five_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            resources: set[str] = set()
            layouts: dict[str, set[str]] = {}

            for spec in PROJECT_FIXTURE_SPECS:
                fixture = build_project_fixture(base_dir, spec)
                manifest = inspect_ok_project(fixture.root)
                resources.add(manifest.resource_name)
                layouts.setdefault(manifest.resource_name, set()).add(spec.layout)
                self.assertTrue(fixture.config_source.is_file())

                if spec.config_location == "src/config.py":
                    self.assertEqual(len(manifest.tasks), len(spec.tasks))

            self.assertEqual(
                resources,
                {"ok-ef", "ok-ww", "ok-nte", "ok-gf2", "ok-dna"},
            )
            for resource_name in resources:
                self.assertEqual(layouts[resource_name], {"source", "installed"})


class ConfigPathBoundaryTest(unittest.TestCase):
    def test_mas_config_dir_requires_uuids_and_stays_under_data(self) -> None:
        script_uid = uuid.uuid4()
        user_uid = uuid.uuid4()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with patch(
                "ok_script_adapter.common.provider.Path.cwd",
                return_value=root,
            ):
                target = ok_script_mas_config_dir(str(script_uid), str(user_uid))

        self.assertEqual(
            target,
            (root / "data" / str(script_uid) / str(user_uid) / "ConfigFile").resolve(),
        )

    def test_mas_config_dir_rejects_invalid_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "script_id"):
            ok_script_mas_config_dir("../other-script", str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, "user_id"):
            ok_script_mas_config_dir(str(uuid.uuid4()), "../other-user")

    def test_config_store_rejects_parent_segments_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = OkConfigStore(Path(tmp_dir) / "configs")
            for name in ("../escape.json", "nested/../escape.json", "./escape.json"):
                with self.subTest(name=name):
                    with self.assertRaises(OkShellRuntimeError):
                        store.write(name, {})
            self.assertEqual(store.validate_name("nested/task.json"), "nested/task.json")


class ConfigOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script_uid = uuid.uuid4()
        self.user_uid = uuid.uuid4()

    def _resolve(self, storage_config: object, user_id: uuid.UUID | None = None):
        app_config = SimpleNamespace(ScriptConfig={self.script_uid: storage_config})
        with (
            patch.object(plugin_module, "PluginScriptConfig", _FakePluginScriptConfig),
            patch.object(plugin_module, "app_config", app_config),
        ):
            return plugin_module._resolve_config_access(
                str(self.script_uid),
                str(user_id or self.user_uid),
            )

    def test_accepts_owned_ok_script_user(self) -> None:
        storage = _FakePluginScriptConfig("OkScript", {self.user_uid})
        access = self._resolve(storage)
        self.assertEqual(access.script_uid, self.script_uid)
        self.assertEqual(access.user_uid, self.user_uid)

    def test_rejects_other_user(self) -> None:
        storage = _FakePluginScriptConfig("OkScript", {self.user_uid})
        with self.assertRaisesRegex(ValueError, "不属于"):
            self._resolve(storage, uuid.uuid4())

    def test_rejects_wrong_script_type(self) -> None:
        storage = _FakePluginScriptConfig("Okww", {self.user_uid})
        with self.assertRaisesRegex(ValueError, "不是 ok-script"):
            self._resolve(storage)

    def test_rejects_non_plugin_storage(self) -> None:
        with self.assertRaisesRegex(ValueError, "不是 ok-script"):
            self._resolve(object())


class ConfigStateTest(unittest.TestCase):
    def test_all_config_source_states_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing = SimpleNamespace(config_dir=root / "missing", tasks=())
            state, diagnostics = plugin_module._config_source_status(
                manifest=missing,
                provider=None,
                source_files=(),
                user_files=(),
                copied_files=(),
            )
            self.assertEqual(state, "source_missing")
            self.assertIn(
                "CONFIG_SOURCE_MISSING",
                {item["code"] for item in diagnostics},
            )

            empty_dir = root / "empty"
            empty_dir.mkdir()
            empty = SimpleNamespace(config_dir=empty_dir, tasks=())
            state, _ = plugin_module._config_source_status(
                manifest=empty,
                provider=None,
                source_files=(),
                user_files=(),
                copied_files=(),
            )
            self.assertEqual(state, "unsupported")

            state, _ = plugin_module._config_source_status(
                manifest=missing,
                provider=object(),
                source_files=(),
                user_files=(),
                copied_files=(),
            )
            self.assertEqual(state, "schema_only")

            state, _ = plugin_module._config_source_status(
                manifest=missing,
                provider=None,
                source_files=(),
                user_files=("DailyTask.json",),
                copied_files=(),
            )
            self.assertEqual(state, "ready")


class ConfigApiBoundaryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.script_uid = uuid.uuid4()
        self.user_uid = uuid.uuid4()
        self.plugin = object.__new__(Plugin)

    def _access(self, config_dir: Path) -> plugin_module._ConfigAccess:
        return plugin_module._ConfigAccess(
            script_uid=self.script_uid,
            user_uid=self.user_uid,
            storage_config=object(),
            config_dir=config_dir,
        )

    def _request(self, configs: object | None = None) -> SimpleNamespace:
        payload: dict[str, object] = {
            "script_id": str(self.script_uid),
            "user_id": str(self.user_uid),
        }
        if configs is not None:
            payload["configs"] = configs
        return SimpleNamespace(json=payload, query={})

    async def test_gf2_without_working_configs_returns_schema_only(self) -> None:
        spec = next(
            item
            for item in PROJECT_FIXTURE_SPECS
            if item.name == "okgf2-installed"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fixture = build_project_fixture(root, spec)
            config_dir = root / "mas-data" / "ConfigFile"
            with (
                patch.object(
                    plugin_module,
                    "_resolve_config_access",
                    return_value=self._access(config_dir),
                ),
                patch.object(
                    plugin_module,
                    "_script_form_config",
                    new=AsyncMock(
                        return_value={"Info": {"RootPath": str(fixture.root)}}
                    ),
                ),
            ):
                response = await self.plugin._list_configs(self._request())

        self.assertEqual(response["code"], 200)
        self.assertEqual(response["configState"], "schema_only")
        self.assertEqual(response["data"], [])
        self.assertFalse(response["provider"]["runtimeVerified"])
        diagnostic_codes = {item["code"] for item in response["diagnostics"]}
        self.assertIn("CONFIG_SOURCE_MISSING", diagnostic_codes)
        self.assertIn("CONFIG_SCHEMA_ONLY", diagnostic_codes)
        self.assertIn("PROVIDER_UNREGISTERED", diagnostic_codes)

    async def test_unknown_provider_keeps_nested_json(self) -> None:
        spec = next(
            item for item in PROJECT_FIXTURE_SPECS if item.name == "okdna-source"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fixture = build_project_fixture(root, spec)
            config_dir = root / "mas-data" / "ConfigFile"
            nested_file = config_dir / "accounts" / "DailyTask.json"
            nested_file.parent.mkdir(parents=True)
            nested_file.write_text('{"enabled": true}', encoding="utf-8")
            with (
                patch.object(
                    plugin_module,
                    "_resolve_config_access",
                    return_value=self._access(config_dir),
                ),
                patch.object(
                    plugin_module,
                    "_script_form_config",
                    new=AsyncMock(
                        return_value={"Info": {"RootPath": str(fixture.root)}}
                    ),
                ),
            ):
                response = await self.plugin._list_configs(self._request())

        by_name = {item["filename"]: item for item in response["data"]}
        self.assertIn("accounts/DailyTask.json", by_name)
        self.assertEqual(by_name["accounts/DailyTask.json"]["directory"], "accounts")
        self.assertEqual(response["configState"], "ready")

    async def test_runtime_lock_rejects_http_update_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "ConfigFile"
            access = self._access(config_dir)
            runtime = object.__new__(OkScriptAutoProxyTask)
            runtime.mas_config_dir = config_dir
            runtime.user_config_lock = None
            runtime.user_config_lock_acquired = False
            runtime.script_info = SimpleNamespace(log="")
            await runtime._acquire_user_config_lock()

            try:
                with patch.object(
                    plugin_module,
                    "_resolve_config_access",
                    return_value=access,
                ):
                    busy_response = await self.plugin._batch_update_configs(
                        self._request({"nested/task.json": {"enabled": True}})
                    )
                self.assertEqual(busy_response["code"], 409)
                self.assertEqual(
                    busy_response["diagnostics"][0]["code"],
                    "CONFIG_BUSY",
                )
                self.assertFalse((config_dir / "nested" / "task.json").exists())
            finally:
                runtime._release_user_config_lock()

            with patch.object(
                plugin_module,
                "_resolve_config_access",
                return_value=access,
            ):
                response = await self.plugin._batch_update_configs(
                    self._request({"nested/task.json": {"enabled": True}})
                )

            stored = OkConfigStore(config_dir).read("nested/task.json")

        self.assertEqual(response["code"], 200)
        self.assertEqual(stored, {"enabled": True})

    async def test_batch_update_rejects_path_traversal_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "ConfigFile"
            with patch.object(
                plugin_module,
                "_resolve_config_access",
                return_value=self._access(config_dir),
            ):
                response = await self.plugin._batch_update_configs(
                    self._request(
                        {
                            "valid.json": {"enabled": True},
                            "../escape.json": {"enabled": False},
                        }
                    )
                )

            self.assertFalse((config_dir / "valid.json").exists())
            self.assertFalse((root / "escape.json").exists())

        self.assertEqual(response["code"], 400)
        self.assertIn("..", response["message"])


if __name__ == "__main__":
    unittest.main()
