import unittest
from pathlib import Path

from app.plugins.schema import PluginSchemaManager


class OkwwPluginSchemaTest(unittest.TestCase):
    def test_plugin_py_does_not_shadow_config_schema_declaration(self) -> None:
        plugin_py = Path("plugins/okww_adapter/src/okww_adapter/plugin.py")

        schema = PluginSchemaManager()._load_schema_from_plugin_py("okww_adapter", plugin_py)

        self.assertEqual(schema, {})


if __name__ == "__main__":
    unittest.main()
