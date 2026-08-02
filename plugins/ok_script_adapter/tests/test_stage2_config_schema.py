from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ok_script_adapter.common.config_schema import (
    CONFIDENCE_DECLARED,
    CONTROL_INTEGER,
    CONTROL_SELECT,
    SOURCE_PROVIDER,
    SOURCE_UPSTREAM,
    VALUE_STRING,
    VALUE_INTEGER,
    FieldChoice,
    FieldDeclaration,
    build_config_draft,
    build_field_schema,
    materialize_field_schemas,
    merge_field_declarations,
    render_legacy_fields,
)
from ok_script_adapter.okef_config_schema import (
    build_field_schemas_for_config as build_okef_field_schemas,
)
from ok_script_adapter.providers.okww_schema import (
    build_field_schemas_for_config as build_okww_field_schemas,
    build_fields_for_config as build_okww_fields,
)
from ok_script_adapter.shell.config_parser import ProjectConfigParser
from ok_script_adapter.shell.parser import ProjectParser


class ProjectConfigParserSafetyTest(unittest.TestCase):
    def test_task_source_is_parsed_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-static-task"
            root.mkdir()
            (root / "pyappify.yml").write_text(
                "name: ok-static-task\n",
                encoding="utf-8",
            )
            (root / "config.py").write_text(
                "config = {\n"
                "    'config_folder': 'configs',\n"
                "    'onetime_tasks': [('tasks', 'DailyTask')],\n"
                "}\n",
                encoding="utf-8",
            )
            marker = root / "task-source-executed.txt"
            (root / "tasks.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
                "class DailyTask:\n"
                "    def __init__(self):\n"
                "        self.default_config = {'enabled': True}\n",
                encoding="utf-8",
            )

            descriptor = ProjectParser(root).parse()
            description = ProjectConfigParser(descriptor).parse()

            self.assertFalse(marker.exists())
            resource = description.get("DailyTask.json")
            self.assertIsNotNone(resource)
            self.assertEqual([field.path for field in resource.fields], ["enabled"])


class FieldDeclarationMergeTest(unittest.TestCase):
    def test_upstream_semantics_keep_provider_labels_and_layout(self) -> None:
        upstream = FieldDeclaration(
            path="mode",
            label="mode",
            control=CONTROL_SELECT,
            value_type=VALUE_INTEGER,
            default=2,
            choices=(
                FieldChoice(value=1, label="1"),
                FieldChoice(value=2, label="2"),
            ),
            source=SOURCE_UPSTREAM,
            confidence=CONFIDENCE_DECLARED,
            section="项目配置",
        )
        provider = FieldDeclaration(
            path="mode",
            label="运行模式",
            description="选择运行模式",
            choices=(
                FieldChoice(value="1", label="模式一"),
                FieldChoice(value="3", label="额外模式"),
            ),
            source=SOURCE_PROVIDER,
            confidence=CONFIDENCE_DECLARED,
            section="运行设置",
            section_priority=10,
            priority=20,
        )

        (merged,) = merge_field_declarations(
            upstream=(upstream,),
            provider=(provider,),
        )

        self.assertEqual(merged.source, SOURCE_UPSTREAM)
        self.assertEqual(merged.default, 2)
        self.assertEqual(merged.value_type, VALUE_INTEGER)
        self.assertEqual([choice.value for choice in merged.choices], [1, 2])
        self.assertEqual([choice.label for choice in merged.choices], ["模式一", "2"])
        self.assertEqual(merged.label, "运行模式")
        self.assertEqual(merged.description, "选择运行模式")
        self.assertEqual(merged.section, "运行设置")
        self.assertEqual(merged.section_priority, 10)
        self.assertEqual(merged.priority, 20)


class FieldSchemaMaterializeTest(unittest.TestCase):
    def test_current_order_then_upstream_defaults_without_provider_only_fields(self) -> None:
        schemas = materialize_field_schemas(
            {"count": 3, "legacy": {"enabled": True}},
            upstream=(
                FieldDeclaration(
                    path="mode",
                    default="auto",
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                ),
            ),
            provider=(
                FieldDeclaration(
                    path="count",
                    label="次数",
                    value_type=VALUE_INTEGER,
                    source=SOURCE_PROVIDER,
                    confidence=CONFIDENCE_DECLARED,
                ),
                FieldDeclaration(
                    path="provider_only",
                    label="仅 provider 字段",
                    source=SOURCE_PROVIDER,
                    confidence=CONFIDENCE_DECLARED,
                ),
            ),
        )

        self.assertEqual([schema.path for schema in schemas], ["count", "legacy", "mode"])
        self.assertEqual(schemas[0].source, SOURCE_PROVIDER)
        self.assertEqual(schemas[1].source, "inferred")
        self.assertTrue(schemas[2].has_default)
        self.assertTrue(schemas[2].omit_when_unset)

        legacy_fields = render_legacy_fields(schemas, {"count": 3, "legacy": {"enabled": True}})
        mode = next(field for field in legacy_fields if field["name"] == "mode")
        self.assertFalse(mode["isSet"])
        self.assertEqual(mode["value"], "auto")

        draft = build_config_draft(
            "Task.json",
            {"count": 3},
            {},
            schemas,
        )
        self.assertEqual(draft.merged, {"count": 3})
        self.assertEqual(draft.changes, ())

    def test_numeric_choices_keep_type_and_mark_existing_unknown_value(self) -> None:
        schema = build_field_schema(
            FieldDeclaration(
                path="level",
                control=CONTROL_SELECT,
                value_type=VALUE_INTEGER,
                choices=(
                    FieldChoice(value="1", label="一级"),
                    FieldChoice(value="2", label="二级"),
                ),
                source=SOURCE_UPSTREAM,
                confidence=CONFIDENCE_DECLARED,
            ),
            value=3,
        )

        self.assertEqual([choice.value for choice in schema.choices], [1, 2, 3])
        self.assertTrue(schema.choices[-1].unknown)
        legacy = schema.to_legacy_field({"level": 3})
        self.assertEqual(legacy["type"], "int")
        self.assertIsNone(legacy["options"])


class ProviderFieldSchemaTest(unittest.TestCase):
    def test_provider_only_missing_options_do_not_create_null_fields(self) -> None:
        fields = build_okww_fields("FarmEchoTask.json", {}, {})

        self.assertEqual(fields, [])

    def test_provider_numeric_options_follow_current_value_type(self) -> None:
        (schema,) = build_okww_field_schemas(
            "FarmEchoTask.json",
            {"Boss Level": 80},
            {},
        )

        self.assertEqual(schema.value_type, VALUE_INTEGER)
        self.assertEqual([choice.value for choice in schema.choices], [50, 60, 70, 80])
        legacy = schema.to_legacy_field({"Boss Level": 80})
        self.assertEqual(legacy["type"], "int")
        self.assertIsNone(legacy["options"])

    def test_upstream_defaults_cannot_restore_provider_hidden_fields(self) -> None:
        okww_schemas = build_okww_field_schemas(
            "DailyTask.json",
            {"_enabled": False},
            {},
            upstream=(
                FieldDeclaration(
                    path="_enabled",
                    default=False,
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                ),
                FieldDeclaration(
                    path="visible",
                    default=True,
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                ),
            ),
        )
        okef_schemas = build_okef_field_schemas(
            "DailyTask.json",
            {"配置选择": "默认", "enabled": True},
            {},
            upstream=(
                FieldDeclaration(
                    path="配置选择",
                    default="默认",
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                ),
            ),
        )

        self.assertEqual([schema.path for schema in okww_schemas], ["visible"])
        self.assertEqual([schema.path for schema in okef_schemas], ["enabled"])


class ConfigDraftRoundTripTest(unittest.TestCase):
    def test_scalar_array_object_and_null_values_round_trip_without_type_drift(self) -> None:
        original = {
            "enabled": True,
            "count": 2,
            "ratio": 0.5,
            "items": ["second", "first"],
            "metadata": {"nested": {"keep": 1}},
            "optional": None,
        }
        schemas = materialize_field_schemas(original)

        draft = build_config_draft(
            "Task.json",
            original,
            {
                "enabled": False,
                "count": 3,
                "ratio": 1,
                "items": ["first", "second"],
                "metadata": {"nested": {"added": 2}},
                "optional": None,
            },
            schemas,
        )

        self.assertTrue(draft.valid)
        self.assertIs(draft.merged["enabled"], False)
        self.assertEqual(draft.merged["count"], 3)
        self.assertIsInstance(draft.merged["count"], int)
        self.assertEqual(draft.merged["ratio"], 1)
        self.assertEqual(draft.merged["items"], ["first", "second"])
        self.assertEqual(
            draft.merged["metadata"],
            {"nested": {"keep": 1, "added": 2}},
        )
        self.assertIsNone(draft.merged["optional"])
        diff_paths = {change.path for change in draft.changes}
        self.assertIn("metadata.nested.added", diff_paths)
        self.assertIn("items", diff_paths)

    def test_wrong_scalar_array_and_object_types_return_field_errors(self) -> None:
        original = {
            "enabled": True,
            "count": 2,
            "ratio": 0.5,
            "items": ["one"],
            "metadata": {"keep": 1},
        }
        draft = build_config_draft(
            "Task.json",
            original,
            {
                "enabled": "false",
                "count": 2.5,
                "ratio": "1.0",
                "items": [1],
                "metadata": "invalid",
            },
            materialize_field_schemas(original),
        )

        self.assertFalse(draft.valid)
        self.assertEqual(
            {error.path for error in draft.errors},
            {"enabled", "count", "ratio", "items[0]", "metadata"},
        )

    def test_existing_unknown_choice_is_preserved_but_new_unknown_is_rejected(self) -> None:
        schema = build_field_schema(
            FieldDeclaration(
                path="mode",
                control=CONTROL_SELECT,
                value_type=VALUE_STRING,
                choices=(
                    FieldChoice(value="auto", label="自动"),
                    FieldChoice(value="manual", label="手动"),
                ),
                source=SOURCE_UPSTREAM,
                confidence=CONFIDENCE_DECLARED,
            ),
            value="legacy",
        )

        preserved = build_config_draft(
            "Task.json",
            {"mode": "legacy"},
            {"mode": "legacy"},
            (schema,),
        )
        rejected = build_config_draft(
            "Task.json",
            {"mode": "legacy"},
            {"mode": "typo"},
            (schema,),
        )

        self.assertTrue(preserved.valid)
        self.assertFalse(rejected.valid)
        self.assertEqual(rejected.errors[0].code, "CHOICE_NOT_ALLOWED")

    def test_explicit_nullable_contract_controls_null_updates(self) -> None:
        nullable = build_field_schema(
            FieldDeclaration(
                path="optional",
                value_type=VALUE_STRING,
                nullable=True,
                source=SOURCE_UPSTREAM,
                confidence=CONFIDENCE_DECLARED,
            )
        )
        required = build_field_schema(
            FieldDeclaration(
                path="required",
                value_type=VALUE_STRING,
                nullable=False,
                source=SOURCE_UPSTREAM,
                confidence=CONFIDENCE_DECLARED,
            )
        )

        nullable_draft = build_config_draft(
            "Task.json",
            {},
            {"optional": None},
            (nullable,),
        )
        required_draft = build_config_draft(
            "Task.json",
            {},
            {"required": None},
            (required,),
        )

        self.assertTrue(nullable_draft.valid)
        self.assertFalse(required_draft.valid)
        self.assertEqual(required_draft.errors[0].code, "NULL_NOT_ALLOWED")

    def test_upstream_default_can_materialize_provider_options(self) -> None:
        (schema,) = build_okww_field_schemas(
            "FarmEchoTask.json",
            {},
            {},
            upstream=(
                FieldDeclaration(
                    path="Boss Level",
                    default=80,
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                ),
            ),
        )

        self.assertTrue(schema.has_default)
        self.assertEqual(schema.default, 80)
        self.assertEqual([choice.value for choice in schema.choices], [50, 60, 70, 80])


if __name__ == "__main__":
    unittest.main()
