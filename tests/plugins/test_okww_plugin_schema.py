import unittest

from app.plugins.schema import PluginSchemaManager


class OkwwPluginSchemaTest(unittest.TestCase):
    def test_plugin_py_does_not_shadow_config_schema_declaration(self) -> None:
        schema = PluginSchemaManager().load_schema("okww_adapter")

        self.assertEqual(schema, {})


if __name__ == "__main__":
    unittest.main()
