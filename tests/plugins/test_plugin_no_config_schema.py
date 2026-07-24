import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import BaseModel, Field

from app.plugins.fields import PLUGIN_FIELD_MARKER
from app.plugins.schema import (
    NO_PLUGIN_CONFIG_FIELD,
    PluginSchemaError,
    PluginSchemaManager,
)


def _missing_module(name: str) -> ModuleNotFoundError:
    error = ModuleNotFoundError(f"No module named '{name}'")
    error.name = name
    return error


def _no_config_schema() -> dict:
    return {
        NO_PLUGIN_CONFIG_FIELD: {
            "type": "boolean",
            "default": True,
            "hidden": True,
            "configurable": False,
        }
    }


class PluginNoConfigSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PluginSchemaManager()
        self.entry_point = SimpleNamespace(name="fake_plugin", module="fake_pkg.plugin")

    def _entry_points(self):
        return patch("app.plugins.schema.iter_plugin_entry_points", return_value=[self.entry_point])

    def test_wheel_only_entry_module_marker_is_supported(self) -> None:
        plugin_module = SimpleNamespace(schema=_no_config_schema())

        def import_module(name: str):
            if name == "fake_pkg.schema":
                raise _missing_module(name)
            if name == "fake_pkg.plugin":
                return plugin_module
            raise AssertionError(name)

        with self._entry_points(), patch("app.plugins.schema.importlib.import_module", side_effect=import_module):
            schema = self.manager.load_schema("fake_plugin")
            effective = self.manager.apply_defaults_and_validate(
                "fake_plugin",
                {NO_PLUGIN_CONFIG_FIELD: True, "legacy": "kept"},
            )

        self.assertFalse(schema[NO_PLUGIN_CONFIG_FIELD]["configurable"])
        self.assertEqual(effective, {"legacy": "kept"})

    def test_schema_module_marker_is_supported_without_config_model(self) -> None:
        schema_module = SimpleNamespace(schema=_no_config_schema())

        with self._entry_points(), patch(
            "app.plugins.schema.importlib.import_module",
            return_value=schema_module,
        ) as importer:
            schema = self.manager.load_schema("fake_plugin")

        self.assertIn(NO_PLUGIN_CONFIG_FIELD, schema)
        importer.assert_called_once_with("fake_pkg.schema")

    def test_entry_module_marker_is_used_when_schema_has_no_config(self) -> None:
        schema_module = SimpleNamespace()
        plugin_module = SimpleNamespace(schema=_no_config_schema())

        def import_module(name: str):
            return schema_module if name == "fake_pkg.schema" else plugin_module

        with self._entry_points(), patch("app.plugins.schema.importlib.import_module", side_effect=import_module):
            self.assertIn(NO_PLUGIN_CONFIG_FIELD, self.manager.load_schema("fake_plugin"))

    def test_real_config_model_takes_priority_over_marker(self) -> None:
        class Config(BaseModel):
            value: int = Field(
                default=7,
                json_schema_extra={PLUGIN_FIELD_MARKER: True},
            )

        schema_module = SimpleNamespace(Config=Config, schema=_no_config_schema())
        with self._entry_points(), patch(
            "app.plugins.schema.importlib.import_module",
            return_value=schema_module,
        ):
            schema = self.manager.load_schema("fake_plugin")
            effective = self.manager.apply_defaults_and_validate("fake_plugin", {})

        self.assertNotIn(NO_PLUGIN_CONFIG_FIELD, schema)
        self.assertEqual(effective, {"value": 7})

    def test_internal_schema_import_failure_is_not_hidden_by_plugin_marker(self) -> None:
        plugin_module = SimpleNamespace(schema=_no_config_schema())

        def import_module(name: str):
            if name == "fake_pkg.schema":
                raise _missing_module("missing_dependency")
            return plugin_module

        with self._entry_points(), patch("app.plugins.schema.importlib.import_module", side_effect=import_module):
            with self.assertRaisesRegex(PluginSchemaError, "missing_dependency"):
                self.manager.load_schema("fake_plugin")

    def test_missing_config_without_explicit_marker_remains_an_error(self) -> None:
        def import_module(name: str):
            if name == "fake_pkg.schema":
                raise _missing_module(name)
            return SimpleNamespace(schema={})

        with self._entry_points(), patch("app.plugins.schema.importlib.import_module", side_effect=import_module):
            with self.assertRaisesRegex(PluginSchemaError, "显式无配置标记"):
                self.manager.load_schema("fake_plugin")


if __name__ == "__main__":
    unittest.main()
