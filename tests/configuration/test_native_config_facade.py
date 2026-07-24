"""Native host facade regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel

import app.configuration.persistence.generation_store as generation_store_module
from app.configuration import ConfigAggregateError, config_manager
from app.configuration.roots.script import PluginScript
from app.configuration.persistence import GenerationPathLengthError
from app.core.native_config import NativeConfigFacade
from app.core.script_types import ScriptTypeRegistry
from app.plugins.script_adapter import ScriptAdapterDefinition


class _PluginScriptInfo(BaseModel):
    Name: str = "Alpha plugin"


class _PluginScriptRun(BaseModel):
    Enabled: bool = True


class _PluginScriptForm(BaseModel):
    Info: _PluginScriptInfo = _PluginScriptInfo()
    Run: _PluginScriptRun = _PluginScriptRun()


class _PluginUserInfo(BaseModel):
    Name: str = "Alpha user"


class _PluginUserForm(BaseModel):
    Info: _PluginUserInfo = _PluginUserInfo()
    Account: str = ""


def _native_script_type_registry() -> ScriptTypeRegistry:
    """Build an authoritative-only registry without loading external plugins."""

    import app.configuration as configuration

    registry = ScriptTypeRegistry()
    with (
        patch.object(
            configuration,
            "CONFIG_V2_MODE",
            configuration.CONFIG_V2_MODE_AUTHORITATIVE,
        ),
        patch.object(registry, "_load_entry_point_providers"),
    ):
        registry.bootstrap()
    return registry


def _register_test_plugin(registry: ScriptTypeRegistry) -> None:
    import app.configuration as configuration

    with patch.object(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    ):
        provider = ScriptAdapterDefinition(
            type_key="AlphaPlugin",
            display_name="Alpha Plugin",
            hooks_factory=None,
            script_model=_PluginScriptForm,
            user_model=_PluginUserForm,
            manager_factory=lambda _item, _provider: object(),
        ).build_provider()
    registry.register(provider)


class NativeConfigFacadeTest(unittest.IsolatedAsyncioTestCase):
    async def test_authoritative_builtin_providers_use_native_config_entries(
        self,
    ) -> None:
        """The authoritative catalog must not compile built-ins to ConfigBase."""

        registry = _native_script_type_registry()
        src = registry.get("SRC")
        general = registry.get("General")

        self.assertEqual(src.script_config_class.__name__, "SrcScript")
        self.assertEqual(src.user_config_class.__name__, "SrcUser")
        self.assertEqual(general.script_config_class.__name__, "GeneralScript")
        self.assertEqual(general.user_config_class.__name__, "GeneralUser")
        self.assertEqual(src.metadata["config_runtime"], "v2-native")
        self.assertEqual(general.metadata["config_runtime"], "v2-native")

    async def test_native_script_provider_capability_and_descriptors(
        self,
    ) -> None:
        """Native records resolve their provider and external descriptor shape."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                src_id, _ = await facade.add_script("SRC")
                general_id, _ = await facade.add_script("General")
                registry = _native_script_type_registry()

                with patch(
                    "app.core.script_types.script_type_registry",
                    registry,
                ):
                    self.assertEqual(facade.get_script_type_key(src_id), "SRC")
                    self.assertEqual(
                        facade.get_script_type_key(general_id),
                        "General",
                    )
                    capability = await facade.get_script_record_capability(src_id)
                    self.assertTrue(capability.available)
                    self.assertEqual(
                        capability.supported_modes,
                        ("AutoProxy", "ManualReview", "ScriptConfig"),
                    )
                    descriptors = await facade.get_script_type_descriptors()

                by_type = {
                    descriptor.type_key: descriptor
                    for descriptor in descriptors
                }
                self.assertEqual(set(by_type), {"SRC", "General"})
                self.assertEqual(
                    by_type["General"].legacy_config_class_name,
                    "GeneralConfig",
                )
                self.assertEqual(
                    by_type["General"].legacy_user_config_class_name,
                    "GeneralUserConfig",
                )
                src_script_groups = {
                    group["key"]: group
                    for group in by_type["SRC"].script_schema["groups"]
                }
                self.assertEqual(
                    set(src_script_groups),
                    {"Info", "Emulator", "Run"},
                )
                self.assertNotIn("UserData", src_script_groups)
            finally:
                facade.close()

    async def test_missing_plugin_provider_is_readable_but_not_executable(
        self,
    ) -> None:
        """Persisted plugin records fail closed when their provider is absent."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                async with config_manager.transaction():
                    script_id = facade.roots.scripts.add(PluginScript)
                    await facade.roots.scripts.commit()
                plugin_script = facade.roots.scripts[script_id]
                await plugin_script.set_many(
                    {
                        "Meta": {"PluginTypeKey": "missing.alpha.provider"},
                        "PluginData": {"Config": '{"enabled": true}'},
                    }
                )
                registry = _native_script_type_registry()

                with patch(
                    "app.core.script_types.script_type_registry",
                    registry,
                ):
                    capability = await facade.get_script_record_capability(
                        script_id
                    )

                self.assertEqual(
                    facade.get_script_type_key(script_id),
                    "missing.alpha.provider",
                )
                self.assertFalse(capability.available)
                self.assertEqual(capability.supported_modes, ())
                self.assertIn(
                    "missing.alpha.provider",
                    capability.unavailable_reason or "",
                )
            finally:
                facade.close()

    async def test_native_plugin_crud_and_scripts2_records(self) -> None:
        """Provider-backed PluginScript/User records persist as Config v2."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                registry = _native_script_type_registry()
                _register_test_plugin(registry)
                with patch(
                    "app.core.script_types.script_type_registry",
                    registry,
                ):
                    script_id, script = await facade.add_script("AlphaPlugin")
                    self.assertIs(type(script), PluginScript)
                    records = await facade.get_script_records(str(script_id))
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0].type, "AlphaPlugin")
                    self.assertEqual(records[0].name, "Alpha plugin")
                    self.assertEqual(
                        records[0].config["Run"]["Enabled"],
                        True,
                    )
                    self.assertEqual(records[0].user_count, 0)

                    await facade.update_script(
                        str(script_id),
                        {
                            "Info": {"Name": "Updated plugin"},
                            "Run": {"Enabled": False},
                        },
                    )
                    user_id, _ = await facade.add_user(str(script_id))
                    await facade.update_user(
                        str(script_id),
                        str(user_id),
                        {
                            "Info": {"Name": "Updated user"},
                            "Account": "alpha-account",
                        },
                    )
                    records = await facade.get_script_records(str(script_id))
                    user_records = await facade.get_user_records(
                        str(script_id),
                        str(user_id),
                    )

                self.assertEqual(records[0].name, "Updated plugin")
                self.assertFalse(records[0].config["Run"]["Enabled"])
                self.assertEqual(records[0].user_count, 1)
                self.assertEqual(user_records[0].type, "AlphaPlugin")
                self.assertEqual(user_records[0].name, "Updated user")
                self.assertEqual(
                    user_records[0].config["Account"],
                    "alpha-account",
                )
            finally:
                facade.close()

    async def test_path_budget_fails_before_facade_creates_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            with (
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
                await facade.init_config()

            self.assertFalse((root / "config").exists())
            self.assertFalse((root / "debug").exists())
            self.assertFalse((root / "data").exists())
            self.assertFalse((root / "history").exists())

    async def test_static_script_user_crud_projects_legacy_transport_and_persists(
        self,
    ) -> None:
        """Static native scripts retain the legacy HTTP shape without ConfigBase."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                script_id, script = await facade.add_script("MAA")
                self.assertEqual(type(script).__name__, "MaaScript")
                await facade.update_script(
                    str(script_id),
                    {"Info": {"Name": "原生 Alpha MAA"}},
                )
                user_id, user = await facade.add_user(str(script_id))
                self.assertEqual(type(user).__name__, "MaaUser")
                await facade.update_user(
                    str(script_id),
                    str(user_id),
                    {
                        "Info": {
                            "Id": "alpha-user",
                            # These are read-only display values emitted by
                            # the established user transport.  A client that
                            # reads and saves the whole form must not fail.
                            "Tag": "legacy-read-only-view",
                            "InfrastName": "legacy-read-only-view",
                            "InfrastIndex": "0",
                        }
                    },
                )

                script_index, script_data = await facade.get_script(None)
                self.assertEqual(
                    script_index,
                    [{"uid": str(script_id), "type": "MaaConfig"}],
                )
                projected_script = script_data[str(script_id)]
                self.assertEqual(projected_script["Info"]["Name"], "原生 Alpha MAA")
                self.assertNotIn("UserData", projected_script)
                self.assertEqual(
                    projected_script["SubConfigsInfo"]["UserData"]["instances"],
                    [{"uid": str(user_id), "type": "MaaUserConfig"}],
                )
                self.assertEqual(
                    projected_script["SubConfigsInfo"]["UserData"][str(user_id)]["Info"][
                        "Id"
                    ],
                    "alpha-user",
                )

                user_index, user_data = await facade.get_user(str(script_id), None)
                self.assertEqual(
                    user_index,
                    [{"uid": str(user_id), "type": "MaaUserConfig"}],
                )
                self.assertEqual(user_data[str(user_id)]["Info"]["Id"], "alpha-user")

                before_invalid_update = facade.state.generation
                with self.assertRaises(ConfigAggregateError):
                    await facade.update_script(
                        str(script_id),
                        {
                            "Info": {"Name": "不得部分提交"},
                            "Run": {"RunTimesLimit": 0},
                        },
                    )
                self.assertEqual(facade.state.generation, before_invalid_update)
                _, after_invalid_update = await facade.get_script(str(script_id))
                self.assertEqual(
                    after_invalid_update[str(script_id)]["Info"]["Name"],
                    "原生 Alpha MAA",
                )

                with self.assertRaises(AttributeError):
                    await facade.update_script(
                        str(script_id),
                        {
                            "Info": {
                                "Name": "未知字段不得部分提交",
                                "NeverPersisted": True,
                            }
                        },
                    )
                _, after_unknown_field = await facade.get_script(str(script_id))
                self.assertEqual(
                    after_unknown_field[str(script_id)]["Info"]["Name"],
                    "原生 Alpha MAA",
                )
                generation = facade.state.generation
            finally:
                facade.close()

            restarted = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await restarted.init_config()
            try:
                self.assertEqual(restarted.state.generation, generation)
                index, data = await restarted.get_script(str(script_id))
                self.assertEqual(index[0]["type"], "MaaConfig")
                self.assertEqual(data[str(script_id)]["Info"]["Name"], "原生 Alpha MAA")
                self.assertEqual(
                    data[str(script_id)]["SubConfigsInfo"]["UserData"][str(user_id)][
                        "Info"
                    ]["Id"],
                    "alpha-user",
                )
            finally:
                restarted.close()

    async def test_script_delete_cascades_queue_items_in_one_config_transaction(
        self,
    ) -> None:
        """The public delete contract removes matching QueueItems, not just refs."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                removed_script_id, _ = await facade.add_script("MAA")
                retained_script_id, _ = await facade.add_script("General")
                queue_id, _ = await facade.add_queue()
                removed_item_id, _ = await facade.add_queue_item(str(queue_id))
                retained_item_id, _ = await facade.add_queue_item(str(queue_id))
                await facade.update_queue_item(
                    str(queue_id),
                    str(removed_item_id),
                    {"Info": {"ScriptId": str(removed_script_id)}},
                )
                await facade.update_queue_item(
                    str(queue_id),
                    str(retained_item_id),
                    {"Info": {"ScriptId": str(retained_script_id)}},
                )

                await facade.del_script(str(removed_script_id))

                self.assertNotIn(removed_script_id, facade.roots.scripts)
                self.assertIn(retained_script_id, facade.roots.scripts)
                queue_items = facade.roots.queues[queue_id].QueueItem
                self.assertNotIn(removed_item_id, queue_items)
                self.assertIn(retained_item_id, queue_items)
                self.assertEqual(
                    queue_items[retained_item_id].Info.ScriptId,
                    str(retained_script_id),
                )
            finally:
                facade.close()

    async def test_script_delete_rolls_back_all_roots_when_later_item_is_locked(
        self,
    ) -> None:
        """A later QueueItem failure cannot persist an earlier cascade removal."""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                script_id, _ = await facade.add_script("MAA")
                queue_id, _ = await facade.add_queue()
                first_item_id, _ = await facade.add_queue_item(str(queue_id))
                locked_item_id, _ = await facade.add_queue_item(str(queue_id))
                for item_id in (first_item_id, locked_item_id):
                    await facade.update_queue_item(
                        str(queue_id),
                        str(item_id),
                        {"Info": {"ScriptId": str(script_id)}},
                    )

                queue_items = facade.roots.queues[queue_id].QueueItem
                await queue_items[locked_item_id].lock()
                with self.assertRaisesRegex(RuntimeError, "队列项"):
                    await facade.del_script(str(script_id))

                self.assertIn(script_id, facade.roots.scripts)
                self.assertIn(first_item_id, queue_items)
                self.assertIn(locked_item_id, queue_items)
                self.assertEqual(
                    queue_items[first_item_id].Info.ScriptId,
                    str(script_id),
                )
                await queue_items[locked_item_id].unlock()
            finally:
                facade.close()

    async def test_all_static_script_descriptors_create_and_project_their_users(
        self,
    ) -> None:
        """Every currently writable descriptor has an explicit API mapping."""

        expected = (
            ("MAA", "MaaConfig", "MaaUserConfig"),
            ("SRC", "SrcConfig", "SrcUserConfig"),
            ("MaaEnd", "MaaEndConfig", "MaaEndUserConfig"),
            ("M9A", "M9AConfig", "M9AUserConfig"),
            ("MaaFW", "MaaFWConfig", "MaaFWUserConfig"),
            ("General", "GeneralConfig", "GeneralUserConfig"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                for api_type, legacy_type, legacy_user_type in expected:
                    with self.subTest(api_type=api_type):
                        script_id, _ = await facade.add_script(api_type)
                        user_id, _ = await facade.add_user(str(script_id))
                        script_index, script_data = await facade.get_script(
                            str(script_id)
                        )
                        user_index, _ = await facade.get_user(str(script_id), None)
                        self.assertEqual(script_index[0]["type"], legacy_type)
                        self.assertEqual(user_index[0]["type"], legacy_user_type)
                        self.assertEqual(
                            script_data[str(script_id)]["SubConfigsInfo"]["UserData"][
                                "instances"
                            ][0],
                            {"uid": str(user_id), "type": legacy_user_type},
                        )
            finally:
                facade.close()

    async def test_unsafe_clone_and_unmigrated_script_types_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                script_id, _ = await facade.add_script("MAA")
                with self.assertRaisesRegex(RuntimeError, "暂不支持复制"):
                    await facade.add_script("MAA", str(script_id))

                for script_type in ("Okww", "OkScript", "PluginScript", "Unknown"):
                    with self.subTest(script_type=script_type):
                        with self.assertRaisesRegex(RuntimeError, "尚未完成原生"):
                            await facade.add_script(script_type)

                self.assertEqual(list(facade.roots.scripts.keys()), [script_id])
            finally:
                facade.close()

    async def test_crud_is_durable_without_legacy_object_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_directory = root / "config"
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=config_directory,
            )
            await facade.init_config()
            try:
                await facade.update_setting(
                    {"Function": {"IfSilence": True}}
                )
                emulator_id, emulator = await facade.add_emulator()
                await facade.update_emulator(
                    str(emulator_id),
                    {
                        "Info": {
                            "Name": "测试模拟器",
                            "Type": "mumu",
                        }
                    },
                )
                queue_id, _ = await facade.add_queue()
                time_id, _ = await facade.add_time_set(str(queue_id))

                index, data = await facade.get_emulator(None)
                self.assertEqual(
                    index,
                    [{"uid": str(emulator_id), "type": "EmulatorConfig"}],
                )
                self.assertEqual(
                    data[str(emulator_id)]["Info"]["Name"],
                    "测试模拟器",
                )
                self.assertIs(emulator, facade.EmulatorConfig[emulator_id])
                time_index, _ = await facade.get_time_set(str(queue_id), None)
                self.assertEqual(
                    time_index,
                    [{"uid": str(time_id), "type": "TimeSet"}],
                )
                generation = facade.state.generation
            finally:
                facade.close()

            restarted = NativeConfigFacade(
                workspace_root=root,
                config_directory=config_directory,
            )
            await restarted.init_config()
            try:
                self.assertNotEqual(restarted.state.generation, "")
                self.assertEqual(restarted.state.generation, generation)
                self.assertTrue(
                    (await restarted.get_setting())["Function"]["IfSilence"]
                )
                _, data = await restarted.get_emulator(str(emulator_id))
                self.assertEqual(
                    data[str(emulator_id)]["Info"]["Type"],
                    "mumu",
                )
            finally:
                restarted.close()

    async def test_multi_field_update_rolls_back_as_one_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            facade = NativeConfigFacade(
                workspace_root=root,
                config_directory=root / "config",
            )
            await facade.init_config()
            try:
                emulator_id, _ = await facade.add_emulator()
                before = facade.state.generation

                with self.assertRaises(ConfigAggregateError):
                    await facade.update_emulator(
                        str(emulator_id),
                        {
                            "Info": {
                                "Name": "不得部分提交",
                                "MaxWaitTime": 0,
                            }
                        },
                    )

                self.assertEqual(facade.state.generation, before)
                _, data = await facade.get_emulator(str(emulator_id))
                self.assertEqual(
                    data[str(emulator_id)]["Info"]["Name"],
                    "新模拟器",
                )
                self.assertEqual(
                    data[str(emulator_id)]["Info"]["MaxWaitTime"],
                    300,
                )
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
