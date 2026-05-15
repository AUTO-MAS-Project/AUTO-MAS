"""脚本适配插件的 schema 操作工具。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


def find_schema_group(schema: dict[str, Any], group_key: str) -> dict[str, Any] | None:
    groups = schema.get("groups")
    if not isinstance(groups, list):
        return None
    for group in groups:
        if isinstance(group, dict) and group.get("key") == group_key:
            return group
    return None


def find_schema_field(schema: dict[str, Any], field_key: str) -> dict[str, Any] | None:
    groups = schema.get("groups")
    if not isinstance(groups, list):
        return None
    for group in groups:
        if not isinstance(group, dict):
            continue
        fields = group.get("fields")
        if not isinstance(fields, list):
            continue
        for field in fields:
            if isinstance(field, dict) and field.get("key") == field_key:
                return field
    return None


def set_schema_group_label(schema: dict[str, Any], group_key: str, label: str) -> None:
    group = find_schema_group(schema, group_key)
    if group is not None:
        group["label"] = label


def set_schema_field_label(schema: dict[str, Any], field_key: str, label: str) -> None:
    field = find_schema_field(schema, field_key)
    if field is not None:
        field["label"] = label


def set_schema_field_options(
    schema: dict[str, Any],
    field_key: str,
    options: list[dict[str, Any]],
    *,
    allow_custom: bool | None = None,
) -> None:
    field = find_schema_field(schema, field_key)
    if field is None:
        return
    field["options"] = copy.deepcopy(options)
    if allow_custom is not None:
        field["allow_custom"] = allow_custom


def set_schema_field_state(
    schema: dict[str, Any],
    field_key: str,
    *,
    readonly: bool | None = None,
    help_text: str | None = None,
    placeholder: str | None = None,
    rows: int | None = None,
    size: str | None = None,
) -> None:
    field = find_schema_field(schema, field_key)
    if field is None:
        return
    if readonly is not None:
        field["readonly"] = readonly
    if help_text is not None:
        field["help"] = help_text
    if placeholder is not None:
        field["placeholder"] = placeholder
    if rows is not None:
        field["rows"] = rows
    if size is not None:
        field["size"] = size


def append_schema_field(
    schema: dict[str, Any],
    group_key: str,
    field_schema: dict[str, Any],
) -> None:
    group = find_schema_group(schema, group_key)
    if group is None:
        groups = schema.setdefault("groups", [])
        if not isinstance(groups, list):
            return
        group = {"key": group_key, "label": group_key, "fields": []}
        groups.append(group)
    fields = group.setdefault("fields", [])
    if not isinstance(fields, list):
        return
    field_key = field_schema.get("key")
    if field_key and any(
        isinstance(f, dict) and f.get("key") == field_key for f in fields
    ):
        return
    fields.append(copy.deepcopy(field_schema))


@dataclass
class SchemaDecorationContext:
    """传递给 schema 装饰钩子的上下文。"""

    get_emulator_combox: Callable[[], Awaitable[list[dict]]]
    get_emulator_devices_combox: Callable[[str], Awaitable[list[dict]]]
    get_plan_combox: Callable[[], Awaitable[list[dict]]]
    get_stage_info: Callable[[str], Awaitable[list[dict]]]

    def find_group(self, schema: dict[str, Any], group_key: str) -> dict[str, Any] | None:
        return find_schema_group(schema, group_key)

    def find_field(self, schema: dict[str, Any], field_key: str) -> dict[str, Any] | None:
        return find_schema_field(schema, field_key)

    def set_group_label(self, schema: dict[str, Any], group_key: str, label: str) -> None:
        set_schema_group_label(schema, group_key, label)

    def set_field_label(self, schema: dict[str, Any], field_key: str, label: str) -> None:
        set_schema_field_label(schema, field_key, label)

    def set_field_options(
        self,
        schema: dict[str, Any],
        field_key: str,
        options: list[dict[str, Any]],
        *,
        allow_custom: bool | None = None,
    ) -> None:
        set_schema_field_options(schema, field_key, options, allow_custom=allow_custom)

    def set_field_state(
        self,
        schema: dict[str, Any],
        field_key: str,
        *,
        readonly: bool | None = None,
        help_text: str | None = None,
        placeholder: str | None = None,
        rows: int | None = None,
        size: str | None = None,
    ) -> None:
        set_schema_field_state(
            schema, field_key,
            readonly=readonly, help_text=help_text,
            placeholder=placeholder, rows=rows, size=size,
        )

    def append_field(
        self,
        schema: dict[str, Any],
        group_key: str,
        field_schema: dict[str, Any],
    ) -> None:
        append_schema_field(schema, group_key, field_schema)
