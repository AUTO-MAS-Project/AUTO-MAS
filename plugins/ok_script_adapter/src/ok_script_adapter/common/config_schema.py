#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 配置字段契约、草稿校验与无损差异。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


FIELD_SCHEMA_VERSION = 1

VALUE_BOOLEAN = "boolean"
VALUE_INTEGER = "integer"
VALUE_NUMBER = "number"
VALUE_STRING = "string"
VALUE_OBJECT = "object"
VALUE_ARRAY = "array"
VALUE_UNKNOWN = "unknown"

CONTROL_SWITCH = "switch"
CONTROL_SELECT = "select"
CONTROL_MULTISELECT = "multiselect"
CONTROL_INTEGER = "integer"
CONTROL_NUMBER = "number"
CONTROL_TEXT = "text"
CONTROL_TEXTAREA = "textarea"
CONTROL_JSON = "json"

SOURCE_UPSTREAM = "upstream"
SOURCE_PROVIDER = "provider"
SOURCE_INFERRED = "inferred"

CONFIDENCE_AUTHORITATIVE = "authoritative"
CONFIDENCE_DECLARED = "declared"
CONFIDENCE_INFERRED = "inferred"

_VALUE_TYPES = {
    VALUE_BOOLEAN,
    VALUE_INTEGER,
    VALUE_NUMBER,
    VALUE_STRING,
    VALUE_OBJECT,
    VALUE_ARRAY,
    VALUE_UNKNOWN,
}
_CONTROLS = {
    CONTROL_SWITCH,
    CONTROL_SELECT,
    CONTROL_MULTISELECT,
    CONTROL_INTEGER,
    CONTROL_NUMBER,
    CONTROL_TEXT,
    CONTROL_TEXTAREA,
    CONTROL_JSON,
}
_SOURCES = {SOURCE_UPSTREAM, SOURCE_PROVIDER, SOURCE_INFERRED}
_CONFIDENCE_LEVELS = {
    CONFIDENCE_AUTHORITATIVE,
    CONFIDENCE_DECLARED,
    CONFIDENCE_INFERRED,
}


class _UnsetValue:
    __slots__ = ()


UNSET = _UnsetValue()


@dataclass(frozen=True, slots=True)
class FieldChoice:
    """字段候选值；value 始终保留原 JSON 类型。"""

    value: Any
    label: str
    unknown: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = {"value": self.value, "label": self.label}
        if self.unknown:
            data["unknown"] = True
        return data


@dataclass(frozen=True, slots=True)
class FieldDeclaration:
    """上游或 provider 给出的可选字段声明。"""

    path: str
    label: str = ""
    description: str = ""
    control: str = ""
    value_type: str = ""
    item_type: str = ""
    default: Any = UNSET
    nullable: bool | None = None
    required: bool = False
    choices: tuple[FieldChoice, ...] = ()
    allow_custom: bool | None = None
    preserve_unknown: bool = True
    ordered: bool = True
    format: str = ""
    timezone_policy: str = ""
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    pattern: str = ""
    source: str = SOURCE_INFERRED
    confidence: str = CONFIDENCE_INFERRED
    omit_when_unset: bool = True
    section: str = ""
    section_priority: int | None = None
    priority: int | None = None
    advanced: bool = False


@dataclass(frozen=True, slots=True)
class FieldSchema:
    """与当前值分离的版本化字段结构。"""

    path: str
    label: str
    description: str
    control: str
    value_type: str
    item_type: str = ""
    default: Any = UNSET
    nullable: bool = False
    required: bool = False
    choices: tuple[FieldChoice, ...] = ()
    allow_custom: bool = False
    preserve_unknown: bool = True
    ordered: bool = True
    format: str = ""
    timezone_policy: str = ""
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    pattern: str = ""
    source: str = SOURCE_INFERRED
    confidence: str = CONFIDENCE_INFERRED
    omit_when_unset: bool = True
    section: str = ""
    section_priority: int | None = None
    priority: int | None = None
    advanced: bool = False
    schema_version: int = FIELD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("FieldSchema.path 不能为空")
        if self.value_type not in _VALUE_TYPES:
            raise ValueError(f"不支持的 value_type: {self.value_type}")
        if self.item_type and self.item_type not in _VALUE_TYPES:
            raise ValueError(f"不支持的 item_type: {self.item_type}")
        if self.control not in _CONTROLS:
            raise ValueError(f"不支持的 control: {self.control}")
        if self.source not in _SOURCES:
            raise ValueError(f"不支持的 schema source: {self.source}")
        if self.confidence not in _CONFIDENCE_LEVELS:
            raise ValueError(f"不支持的 schema confidence: {self.confidence}")

    @property
    def has_default(self) -> bool:
        return self.default is not UNSET

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "fieldId": self.path,
            "path": self.path,
            "label": self.label,
            "description": self.description,
            "control": self.control,
            "valueType": self.value_type,
            "itemType": self.item_type or None,
            "hasDefault": self.has_default,
            "nullable": self.nullable,
            "required": self.required,
            "choices": [choice.to_dict() for choice in self.choices],
            "allowCustom": self.allow_custom,
            "preserveUnknown": self.preserve_unknown,
            "ordered": self.ordered,
            "format": self.format or None,
            "timezonePolicy": self.timezone_policy or None,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "pattern": self.pattern or None,
            "source": self.source,
            "confidence": self.confidence,
            "omitWhenUnset": self.omit_when_unset,
        }
        if self.has_default:
            data["default"] = self.default
        if self.section:
            data["section"] = self.section
        if self.section_priority is not None:
            data["sectionPriority"] = self.section_priority
        if self.priority is not None:
            data["priority"] = self.priority
        if self.advanced:
            data["advanced"] = True
        return data

    def to_legacy_field(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """投影为当前 OkScriptConfigEditor 可消费的旧字段结构。"""

        is_set = self.path in values
        value = values[self.path] if is_set else self.default if self.has_default else None
        legacy_type = _legacy_field_type(self)
        legacy_options: list[str] | None = None
        if legacy_type in ("select", "list") and all(
            isinstance(choice.value, str) for choice in self.choices
        ):
            legacy_options = [str(choice.value) for choice in self.choices]

        return {
            "name": self.path,
            "type": legacy_type,
            "label": self.label,
            "description": self.description,
            "value": value,
            "options": legacy_options,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "section": self.section or "通用",
            "sectionPriority": self.section_priority,
            "priority": self.priority,
            "advanced": self.advanced,
            "isSet": is_set,
            "schema": self.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    """某个配置文件在读取时的值与来源指纹。"""

    values: dict[str, Any]
    source_fingerprint: str
    schema_version: int = FIELD_SCHEMA_VERSION

    @property
    def revision(self) -> str:
        return _fingerprint_json(self.values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "sourceFingerprint": self.source_fingerprint,
            "revision": self.revision,
            "values": self.values,
        }


@dataclass(frozen=True, slots=True)
class FieldValidationError:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class ConfigDiffEntry:
    path: str
    operation: str
    before: Any = UNSET
    after: Any = UNSET

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "operation": self.operation,
            "beforeSet": self.before is not UNSET,
            "afterSet": self.after is not UNSET,
        }
        if self.before is not UNSET:
            data["before"] = self.before
        if self.after is not UNSET:
            data["after"] = self.after
        return data


@dataclass(frozen=True, slots=True)
class ConfigDraft:
    """一次尚未提交的配置补丁及其完整校验结果。"""

    filename: str
    patch: dict[str, Any]
    merged: dict[str, Any]
    changes: tuple[ConfigDiffEntry, ...]
    errors: tuple[FieldValidationError, ...]
    schema_version: int = FIELD_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "filename": self.filename,
            "valid": self.valid,
            "changes": [change.to_dict() for change in self.changes],
            "errors": [error.to_dict() for error in self.errors],
        }


def build_field_schema(
    declaration: FieldDeclaration,
    *,
    value: Any = UNSET,
) -> FieldSchema:
    """把声明和当前值合成为一项强类型字段契约。"""

    reference = _reference_value(value, declaration.default)
    value_type = declaration.value_type or _infer_value_type(reference)
    if value_type == VALUE_UNKNOWN and declaration.choices:
        value_type = _infer_choice_type(declaration.choices)

    item_type = declaration.item_type
    if value_type == VALUE_ARRAY and not item_type:
        item_type = _infer_array_item_type(reference)
        if item_type == VALUE_UNKNOWN and declaration.choices:
            item_type = _infer_choice_type(declaration.choices)

    choices = _normalize_choices(
        declaration.choices,
        target_type=item_type if value_type == VALUE_ARRAY else value_type,
    )
    choices = _append_unknown_choices(
        choices,
        value=value,
        value_type=value_type,
        item_type=item_type,
    )
    control = declaration.control or _infer_control(
        value_type=value_type,
        item_type=item_type,
        choices=choices,
    )
    allow_custom = declaration.allow_custom
    if allow_custom is None:
        allow_custom = value_type == VALUE_ARRAY and not choices and item_type == VALUE_STRING
    nullable = declaration.nullable
    if nullable is None:
        nullable = value is None or declaration.default is None

    return FieldSchema(
        path=declaration.path,
        label=declaration.label or declaration.path,
        description=declaration.description,
        control=control,
        value_type=value_type,
        item_type=item_type,
        default=declaration.default,
        nullable=nullable,
        required=declaration.required,
        choices=choices,
        allow_custom=allow_custom,
        preserve_unknown=declaration.preserve_unknown,
        ordered=declaration.ordered,
        format=declaration.format,
        timezone_policy=declaration.timezone_policy,
        minimum=declaration.minimum,
        maximum=declaration.maximum,
        step=declaration.step,
        pattern=declaration.pattern,
        source=declaration.source,
        confidence=declaration.confidence,
        omit_when_unset=declaration.omit_when_unset,
        section=declaration.section,
        section_priority=declaration.section_priority,
        priority=declaration.priority,
        advanced=declaration.advanced,
    )


def build_inferred_field_schemas(values: Mapping[str, Any]) -> tuple[FieldSchema, ...]:
    """为未知项目的已有 JSON 值建立低可信兼容 schema。"""

    return tuple(
        build_field_schema(
            FieldDeclaration(path=str(path), label=str(path)),
            value=value,
        )
        for path, value in values.items()
    )


def merge_field_declarations(
    *,
    upstream: Iterable[FieldDeclaration] = (),
    provider: Iterable[FieldDeclaration] = (),
) -> tuple[FieldDeclaration, ...]:
    """合并上游字段语义与 provider 的本地化、布局补充。"""

    upstream_by_path = {item.path: item for item in upstream}
    provider_by_path = {item.path: item for item in provider}
    paths = list(upstream_by_path)
    paths.extend(path for path in provider_by_path if path not in upstream_by_path)

    merged: list[FieldDeclaration] = []
    for path in paths:
        upstream_item = upstream_by_path.get(path)
        provider_item = provider_by_path.get(path)
        if upstream_item is None:
            if provider_item is not None:
                merged.append(provider_item)
            continue
        if provider_item is None:
            merged.append(upstream_item)
            continue

        value_type = upstream_item.value_type or provider_item.value_type
        item_type = upstream_item.item_type or provider_item.item_type
        choice_type = item_type if value_type == VALUE_ARRAY else value_type
        choices = _merge_declared_choices(
            upstream_item.choices,
            provider_item.choices,
            target_type=choice_type,
        )
        merged.append(
            FieldDeclaration(
                path=path,
                label=provider_item.label or upstream_item.label,
                description=provider_item.description or upstream_item.description,
                control=upstream_item.control or provider_item.control,
                value_type=value_type,
                item_type=item_type,
                default=(
                    upstream_item.default
                    if upstream_item.default is not UNSET
                    else provider_item.default
                ),
                nullable=(
                    upstream_item.nullable
                    if upstream_item.nullable is not None
                    else provider_item.nullable
                ),
                required=upstream_item.required or provider_item.required,
                choices=choices,
                allow_custom=(
                    upstream_item.allow_custom
                    if upstream_item.allow_custom is not None
                    else provider_item.allow_custom
                ),
                preserve_unknown=upstream_item.preserve_unknown,
                ordered=upstream_item.ordered,
                format=upstream_item.format or provider_item.format,
                timezone_policy=(
                    upstream_item.timezone_policy or provider_item.timezone_policy
                ),
                minimum=(
                    upstream_item.minimum
                    if upstream_item.minimum is not None
                    else provider_item.minimum
                ),
                maximum=(
                    upstream_item.maximum
                    if upstream_item.maximum is not None
                    else provider_item.maximum
                ),
                step=(
                    upstream_item.step
                    if upstream_item.step is not None
                    else provider_item.step
                ),
                pattern=upstream_item.pattern or provider_item.pattern,
                source=upstream_item.source,
                confidence=upstream_item.confidence,
                omit_when_unset=upstream_item.omit_when_unset,
                section=provider_item.section or upstream_item.section,
                section_priority=(
                    provider_item.section_priority
                    if provider_item.section_priority is not None
                    else upstream_item.section_priority
                ),
                priority=(
                    provider_item.priority
                    if provider_item.priority is not None
                    else upstream_item.priority
                ),
                advanced=provider_item.advanced or upstream_item.advanced,
            )
        )
    return tuple(merged)


def materialize_field_schemas(
    values: Mapping[str, Any],
    *,
    upstream: Iterable[FieldDeclaration] = (),
    provider: Iterable[FieldDeclaration] = (),
) -> tuple[FieldSchema, ...]:
    """按当前 JSON 顺序生成字段，并追加有上游默认值的缺失字段。"""

    upstream_items = tuple(upstream)
    merged = merge_field_declarations(
        upstream=upstream_items,
        provider=provider,
    )
    declaration_by_path = {item.path: item for item in merged}
    upstream_by_path = {item.path: item for item in upstream_items}
    schemas: list[FieldSchema] = []
    seen: set[str] = set()

    for raw_path, value in values.items():
        path = str(raw_path)
        declaration = declaration_by_path.get(path)
        if declaration is None:
            declaration = FieldDeclaration(path=path, label=path)
        schemas.append(build_field_schema(declaration, value=value))
        seen.add(path)

    for declaration in merged:
        if declaration.path in seen:
            continue
        upstream_item = upstream_by_path.get(declaration.path)
        if upstream_item is None or upstream_item.default is UNSET:
            continue
        schemas.append(build_field_schema(declaration))
    return tuple(schemas)


def render_legacy_fields(
    schemas: Iterable[FieldSchema],
    values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [schema.to_legacy_field(values) for schema in schemas]


def build_config_draft(
    filename: str,
    original: Mapping[str, Any],
    patch: Mapping[str, Any],
    schemas: Iterable[FieldSchema],
) -> ConfigDraft:
    """校验一份补丁并生成递归合并后的无副作用草稿。"""

    original_data = dict(original)
    patch_data = dict(patch)
    schema_by_path = {schema.path: schema for schema in schemas}
    errors: list[FieldValidationError] = []
    for path, value in patch_data.items():
        schema = schema_by_path.get(path)
        if schema is None:
            errors.append(
                FieldValidationError(
                    path=str(path),
                    code="UNKNOWN_FIELD",
                    message="字段不在当前配置 schema 中",
                )
            )
            continue
        errors.extend(
            _validate_field_value(
                schema,
                value,
                original=original_data.get(path, UNSET),
            )
        )

    merged = merge_config_objects(original_data, patch_data)
    return ConfigDraft(
        filename=filename,
        patch=patch_data,
        merged=merged,
        changes=build_config_diff(original_data, merged),
        errors=tuple(errors),
    )


def merge_config_objects(
    original: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(original)
    for key, value in updates.items():
        current = merged.get(key, UNSET)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_config_objects(current, value)
        else:
            merged[key] = value
    return merged


def build_config_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[ConfigDiffEntry, ...]:
    changes: list[ConfigDiffEntry] = []
    _collect_diff(dict(before), dict(after), "", changes)
    return tuple(changes)


def schema_catalog_fingerprint(
    schemas_by_file: Mapping[str, Iterable[FieldSchema]],
    *,
    source_fingerprint: str = "",
) -> str:
    payload = {
        "schemaVersion": FIELD_SCHEMA_VERSION,
        "sourceFingerprint": source_fingerprint,
        "files": {
            filename: [schema.to_dict() for schema in schemas]
            for filename, schemas in sorted(schemas_by_file.items())
        },
    }
    return _fingerprint_json(payload)


def _reference_value(value: Any, default: Any) -> Any:
    if value is not UNSET and value is not None:
        return value
    if default is not UNSET and default is not None:
        return default
    return UNSET


def _infer_value_type(value: Any) -> str:
    if value is UNSET or value is None:
        return VALUE_UNKNOWN
    if isinstance(value, bool):
        return VALUE_BOOLEAN
    if isinstance(value, int):
        return VALUE_INTEGER
    if isinstance(value, float):
        return VALUE_NUMBER
    if isinstance(value, str):
        return VALUE_STRING
    if isinstance(value, dict):
        return VALUE_OBJECT
    if isinstance(value, list):
        return VALUE_ARRAY
    return VALUE_UNKNOWN


def _infer_array_item_type(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return VALUE_UNKNOWN
    item_types = {_infer_value_type(item) for item in value if item is not None}
    if not item_types:
        return VALUE_UNKNOWN
    if item_types <= {VALUE_INTEGER, VALUE_NUMBER}:
        return VALUE_NUMBER if VALUE_NUMBER in item_types else VALUE_INTEGER
    return next(iter(item_types)) if len(item_types) == 1 else VALUE_UNKNOWN


def _infer_choice_type(choices: Iterable[FieldChoice]) -> str:
    choice_types = {_infer_value_type(choice.value) for choice in choices}
    if choice_types <= {VALUE_INTEGER, VALUE_NUMBER}:
        return VALUE_NUMBER if VALUE_NUMBER in choice_types else VALUE_INTEGER
    return next(iter(choice_types)) if len(choice_types) == 1 else VALUE_UNKNOWN


def _infer_control(
    *,
    value_type: str,
    item_type: str,
    choices: tuple[FieldChoice, ...],
) -> str:
    if choices:
        return CONTROL_MULTISELECT if value_type == VALUE_ARRAY else CONTROL_SELECT
    if value_type == VALUE_BOOLEAN:
        return CONTROL_SWITCH
    if value_type == VALUE_INTEGER:
        return CONTROL_INTEGER
    if value_type == VALUE_NUMBER:
        return CONTROL_NUMBER
    if value_type == VALUE_STRING:
        return CONTROL_TEXT
    if value_type == VALUE_ARRAY and item_type == VALUE_STRING:
        return CONTROL_MULTISELECT
    return CONTROL_JSON


def _normalize_choices(
    choices: Iterable[FieldChoice],
    *,
    target_type: str,
) -> tuple[FieldChoice, ...]:
    normalized: list[FieldChoice] = []
    for choice in choices:
        value = _coerce_declared_choice(choice.value, target_type)
        candidate = FieldChoice(value=value, label=choice.label, unknown=choice.unknown)
        if not any(_json_values_equal(item.value, candidate.value) for item in normalized):
            normalized.append(candidate)
    return tuple(normalized)


def _merge_declared_choices(
    upstream: tuple[FieldChoice, ...],
    provider: tuple[FieldChoice, ...],
    *,
    target_type: str,
) -> tuple[FieldChoice, ...]:
    if not upstream:
        return provider
    if not provider:
        return upstream

    merged: list[FieldChoice] = []
    for upstream_choice in upstream:
        upstream_value = _coerce_declared_choice(upstream_choice.value, target_type)
        provider_choice = next(
            (
                item
                for item in provider
                if _json_values_equal(
                    upstream_value,
                    _coerce_declared_choice(item.value, target_type),
                )
            ),
            None,
        )
        merged.append(
            FieldChoice(
                value=upstream_choice.value,
                label=(
                    provider_choice.label
                    if provider_choice is not None and provider_choice.label
                    else upstream_choice.label
                ),
                unknown=upstream_choice.unknown,
            )
        )
    return tuple(merged)


def _coerce_declared_choice(value: Any, target_type: str) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        if target_type == VALUE_INTEGER and re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        if target_type == VALUE_NUMBER and re.fullmatch(
            r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
            text,
        ):
            return float(text)
        if target_type == VALUE_BOOLEAN and text.casefold() in ("true", "false"):
            return text.casefold() == "true"
    except (OverflowError, ValueError):
        return value
    return value


def _append_unknown_choices(
    choices: tuple[FieldChoice, ...],
    *,
    value: Any,
    value_type: str,
    item_type: str,
) -> tuple[FieldChoice, ...]:
    if not choices or value is UNSET or value is None:
        return choices
    current_values = value if value_type == VALUE_ARRAY and isinstance(value, list) else [value]
    result = list(choices)
    target_type = item_type if value_type == VALUE_ARRAY else value_type
    for current in current_values:
        if current is None:
            continue
        typed_current = _coerce_declared_choice(current, target_type)
        if any(_json_values_equal(choice.value, typed_current) for choice in result):
            continue
        result.append(FieldChoice(value=current, label=str(current), unknown=True))
    return tuple(result)


def _legacy_field_type(schema: FieldSchema) -> str:
    if schema.control == CONTROL_TEXTAREA:
        return "textarea"
    if schema.value_type == VALUE_BOOLEAN:
        return "bool"
    if schema.value_type == VALUE_INTEGER:
        return "int"
    if schema.value_type == VALUE_NUMBER:
        return "float"
    if schema.value_type in (VALUE_OBJECT, VALUE_UNKNOWN):
        return "json"
    if schema.value_type == VALUE_ARRAY:
        if schema.item_type == VALUE_STRING:
            return "list"
        return "json"
    if schema.control == CONTROL_SELECT and all(
        isinstance(choice.value, str) for choice in schema.choices
    ):
        return "select"
    return "string"


def _validate_field_value(
    schema: FieldSchema,
    value: Any,
    *,
    original: Any,
) -> list[FieldValidationError]:
    if value is None:
        if schema.nullable:
            return []
        return [_validation_error(schema, "NULL_NOT_ALLOWED", "字段不允许为 null")]

    if not _is_json_value(value):
        return [_validation_error(schema, "INVALID_JSON_VALUE", "字段值不是有效 JSON 值")]
    if not _matches_value_type(value, schema.value_type):
        return [
            _validation_error(
                schema,
                "TYPE_MISMATCH",
                f"字段必须是 {_value_type_label(schema.value_type)}",
            )
        ]
    if schema.value_type == VALUE_ARRAY and isinstance(value, list) and schema.item_type:
        for index, item in enumerate(value):
            if item is None or schema.item_type == VALUE_UNKNOWN:
                continue
            if not _matches_value_type(item, schema.item_type):
                return [
                    FieldValidationError(
                        path=f"{schema.path}[{index}]",
                        code="ITEM_TYPE_MISMATCH",
                        message=f"列表项必须是 {_value_type_label(schema.item_type)}",
                    )
                ]

    choice_error = _validate_choices(schema, value, original=original)
    if choice_error is not None:
        return [choice_error]

    errors: list[FieldValidationError] = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            errors.append(_validation_error(schema, "NUMBER_NOT_FINITE", "数字必须是有限值"))
        if schema.minimum is not None and numeric < float(schema.minimum):
            errors.append(
                _validation_error(schema, "NUMBER_TOO_SMALL", f"数字不能小于 {schema.minimum}")
            )
        if schema.maximum is not None and numeric > float(schema.maximum):
            errors.append(
                _validation_error(schema, "NUMBER_TOO_LARGE", f"数字不能大于 {schema.maximum}")
            )
        if schema.step not in (None, 0):
            base = float(schema.minimum or 0)
            quotient = (numeric - base) / float(schema.step)
            if not math.isclose(quotient, round(quotient), rel_tol=1e-9, abs_tol=1e-9):
                errors.append(
                    _validation_error(schema, "NUMBER_STEP_MISMATCH", f"数字步长必须是 {schema.step}")
                )
    if schema.pattern and isinstance(value, str):
        try:
            matched = re.fullmatch(schema.pattern, value) is not None
        except re.error:
            matched = True
        if not matched:
            errors.append(_validation_error(schema, "PATTERN_MISMATCH", "字段格式不符合要求"))
    return errors


def _validate_choices(
    schema: FieldSchema,
    value: Any,
    *,
    original: Any,
) -> FieldValidationError | None:
    if not schema.choices:
        return None
    values = value if schema.value_type == VALUE_ARRAY and isinstance(value, list) else [value]
    original_values = (
        original
        if schema.value_type == VALUE_ARRAY and isinstance(original, list)
        else [original]
    )
    for item in values:
        if any(_json_values_equal(choice.value, item) for choice in schema.choices):
            continue
        if schema.allow_custom:
            continue
        if schema.preserve_unknown and any(
            original_item is not UNSET and _json_values_equal(original_item, item)
            for original_item in original_values
        ):
            continue
        return _validation_error(
            schema,
            "CHOICE_NOT_ALLOWED",
            f"值 {item!r} 不在允许的选项中",
        )
    return None


def _validation_error(schema: FieldSchema, code: str, message: str) -> FieldValidationError:
    return FieldValidationError(path=schema.path, code=code, message=message)


def _matches_value_type(value: Any, value_type: str) -> bool:
    if value_type == VALUE_UNKNOWN:
        return _is_json_value(value)
    if value_type == VALUE_BOOLEAN:
        return isinstance(value, bool)
    if value_type == VALUE_INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == VALUE_NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == VALUE_STRING:
        return isinstance(value, str)
    if value_type == VALUE_OBJECT:
        return isinstance(value, dict)
    if value_type == VALUE_ARRAY:
        return isinstance(value, list)
    return False


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _value_type_label(value_type: str) -> str:
    return {
        VALUE_BOOLEAN: "布尔值",
        VALUE_INTEGER: "整数",
        VALUE_NUMBER: "数字",
        VALUE_STRING: "字符串",
        VALUE_OBJECT: "对象",
        VALUE_ARRAY: "数组",
        VALUE_UNKNOWN: "JSON 值",
    }.get(value_type, value_type)


def _collect_diff(
    before: Any,
    after: Any,
    path: str,
    changes: list[ConfigDiffEntry],
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        keys = list(before)
        keys.extend(key for key in after if key not in before)
        for key in keys:
            child_path = f"{path}.{key}" if path else str(key)
            _collect_diff(
                before.get(key, UNSET),
                after.get(key, UNSET),
                child_path,
                changes,
            )
        return
    if before is not UNSET and after is not UNSET and _json_values_equal(before, after):
        return
    operation = "add" if before is UNSET else "remove" if after is UNSET else "replace"
    changes.append(ConfigDiffEntry(path=path, operation=operation, before=before, after=after))


def _json_values_equal(left: Any, right: Any) -> bool:
    if left is UNSET or right is UNSET:
        return left is right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return list(left) == list(right) and all(
            key in right and _json_values_equal(value, right[key])
            for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _fingerprint_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
