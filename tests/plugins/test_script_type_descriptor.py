from __future__ import annotations

import unittest

from app.core.script_types import ScriptTypeProvider, build_descriptor
from app.models.script_api import ScriptTypeDescriptor


class ScriptTypeDescriptorTest(unittest.TestCase):
    def test_create_group_uses_declared_metadata(self) -> None:
        descriptor = build_descriptor(self._provider({"create_group": "general"}))

        self.assertEqual(descriptor["create_group"], "general")
        self.assertEqual(
            ScriptTypeDescriptor.model_validate(descriptor).create_group,
            "general",
        )

    def test_create_group_defaults_to_specialized(self) -> None:
        descriptor = build_descriptor(self._provider({"create_group": "unknown"}))

        self.assertEqual(descriptor["create_group"], "specialized")

    @staticmethod
    def _provider(metadata: dict[str, object]) -> ScriptTypeProvider:
        return ScriptTypeProvider(
            type_key="PluginScript",
            display_name="插件脚本",
            script_config_class=object,
            user_config_class=object,
            supported_modes=(),
            manager_factory=lambda _: None,
            script_schema={},
            user_schema={},
            metadata=metadata,
        )


if __name__ == "__main__":
    unittest.main()
