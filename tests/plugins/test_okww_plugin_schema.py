import sys
import unittest
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import patch

from app.plugins.schema import PluginSchemaManager


class OkwwPluginSchemaTest(unittest.TestCase):
    def test_plugin_py_does_not_shadow_config_schema_declaration(self) -> None:
        plugin_source = (
            Path(__file__).resolve().parents[2]
            / "plugins"
            / "okww_adapter"
            / "src"
        )
        if str(plugin_source) not in sys.path:
            sys.path.insert(0, str(plugin_source))
        entry_point = EntryPoint(
            name="okww_adapter",
            value="okww_adapter.plugin:Plugin",
            group="auto_mas.plugins",
        )
        with patch(
            "app.plugins.schema.iter_plugin_entry_points",
            return_value=[entry_point],
        ):
            schema = PluginSchemaManager().load_schema("okww_adapter")

        self.assertEqual(schema, {})


if __name__ == "__main__":
    unittest.main()
