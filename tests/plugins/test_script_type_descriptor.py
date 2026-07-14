from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.core.script_types import ScriptTypeProvider, build_descriptor
from app.models.schema import ScriptCreateIn
from app.models.script_api import ScriptRecordCreateIn, ScriptTypeDescriptor


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

    def test_client_and_unavailability_are_serialized_together(self) -> None:
        descriptor = ScriptTypeDescriptor.model_validate(
            build_descriptor(
                self._provider(
                    {
                        "client": {"config_editor": {"kind": "json"}},
                        "available": False,
                        "unavailable_reason": "adapter missing",
                    }
                )
            )
        )

        self.assertEqual(
            descriptor.client,
            {"config_editor": {"kind": "json"}},
        )
        self.assertFalse(descriptor.available)
        self.assertEqual(descriptor.unavailable_reason, "adapter missing")

    def test_hsr_creation_stays_out_of_the_legacy_static_contract(self) -> None:
        self.assertEqual(ScriptCreateIn(type="OkScript").type, "OkScript")
        with self.assertRaises(ValidationError):
            ScriptCreateIn(type="HSR")

        self.assertEqual(ScriptRecordCreateIn(type="HSR").type, "HSR")

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
