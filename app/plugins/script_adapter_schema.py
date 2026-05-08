from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from pydantic_core import PydanticUndefined

from app.models.ConfigBase import (
    BoolValidator,
    ConfigBase,
    ConfigItem,
    DateTimeValidator,
    EncryptValidator,
    FileValidator,
    FolderValidator,
    JSONValidator,
    MultipleConfig,
    MultipleUIDValidator,
    OptionsValidator,
    RangeValidator,
    StringValidator,
    URLValidator,
    UserNameValidator,
    ValidatorBase,
    VirtualConfigValidator,
)

from .fields import PluginFieldDeclaration, PluginFieldGroup


@dataclass(slots=True)
class ScriptAdapterSchemaArtifacts:
    """字段声明编译后的脚本适配产物。"""

    script_config_class: type[ConfigBase]
    user_config_class: type[ConfigBase]
    script_schema: dict[str, Any]
    user_schema: dict[str, Any]
    bind_related_config: Callable[[Any], None]


def build_script_adapter_schema(
    *,
    script_class_name: str,
    user_class_name: str,
    script_groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...],
    user_groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...],
    module: str,
    related_bindings: dict[str, str] | None = None,
    user_data_attribute: str | None = "UserData",
) -> ScriptAdapterSchemaArtifacts:
    """根据字段声明生成脚本配置类、用户配置类和前端 schema。"""

    user_config_class = build_configbase_class(
        user_class_name,
        user_groups,
        module=module,
    )
    script_extra_multiples: list[tuple[str, type[ConfigBase]]] = []
    if user_data_attribute:
        script_extra_multiples.append((user_data_attribute, user_config_class))

    script_config_class = build_configbase_class(
        script_class_name,
        script_groups,
        module=module,
        extra_multiples=script_extra_multiples,
    )

    def _bind_related_config(global_config: Any) -> None:
        for related_name, host_attr in (related_bindings or {}).items():
            if hasattr(global_config, host_attr):
                script_config_class.related_config[related_name] = getattr(global_config, host_attr)
            if hasattr(global_config, host_attr):
                user_config_class.related_config[related_name] = getattr(global_config, host_attr)

    return ScriptAdapterSchemaArtifacts(
        script_config_class=script_config_class,
        user_config_class=user_config_class,
        script_schema=build_schema(script_groups),
        user_schema=build_schema(user_groups),
        bind_related_config=_bind_related_config,
    )


def build_configbase_class(
    class_name: str,
    groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...],
    *,
    module: str,
    extra_multiples: list[tuple[str, type[ConfigBase]]] | None = None,
) -> type[ConfigBase]:
    """把字段组声明编译成 ConfigBase 兼容类。"""

    normalized_groups = tuple(groups)
    nested_multiples = _compile_nested_multiples(class_name, normalized_groups, module)
    all_multiples = tuple(nested_multiples + list(extra_multiples or []))

    def __init__(self: ConfigBase) -> None:
        for group in normalized_groups:
            for field in group.fields:
                if _is_runtime_field(field):
                    setattr(
                        self,
                        _config_item_attr(group.key, field.name),
                        ConfigItem(
                            group.key,
                            field.name,
                            _copy_default(field.default),
                            _build_validator(self, group.key, field),
                            legacy_group=field.legacy_group,
                            legacy_name=field.legacy_name,
                        ),
                    )

        for attr_name, config_class in all_multiples:
            setattr(self, attr_name, MultipleConfig([config_class]))

        ConfigBase.__init__(self)

    namespace: dict[str, Any] = {
        "__doc__": "由 PluginField 字段声明生成的运行时配置类。",
        "__init__": __init__,
        "__module__": module,
        "related_config": {},
        "_field_groups": normalized_groups,
    }
    return type(class_name, (ConfigBase,), namespace)


def build_schema(groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...]) -> dict[str, Any]:
    """把字段组声明编译成前端 SchemaForm 可消费的结构。"""

    schema_groups: list[dict[str, Any]] = []
    for group in groups:
        fields = [_build_schema_field(group.key, field) for field in group.fields if field.include_in_schema]
        if fields:
            schema_groups.append({"key": group.key, "label": group.label, "fields": fields})
    return {"groups": schema_groups}


def _compile_nested_multiples(
    parent_class_name: str,
    groups: tuple[PluginFieldGroup, ...],
    module: str,
) -> list[tuple[str, type[ConfigBase]]]:
    result: list[tuple[str, type[ConfigBase]]] = []
    for group in groups:
        for field in group.fields:
            if field.field_type != "multiple":
                continue
            class_name = field.multiple_class_name or f"{parent_class_name}{field.name}"
            config_class = build_configbase_class(
                class_name,
                field.multiple_groups,
                module=module,
            )
            result.append((_multiple_attr(group.key, field.name), config_class))
    return result


def _is_runtime_field(field: PluginFieldDeclaration) -> bool:
    if field.field_type in {"button", "action", "multiple"}:
        return False
    return field.configurable


def _build_validator(
    config: ConfigBase,
    group: str,
    field: PluginFieldDeclaration,
) -> ValidatorBase:
    if field.virtual_handler is not None:
        return VirtualConfigValidator(lambda: str(field.virtual_handler(config)))

    if field.validator == "username":
        return UserNameValidator()
    if field.field_type == "related-id":
        return MultipleUIDValidator(
            _copy_default(
                field.related_default
                if field.related_default is not PydanticUndefined
                else field.default
            ),
            type(config).related_config,
            str(field.related_config or ""),
        )
    if field.field_type == "folder" or field.path_kind == "folder":
        return FolderValidator()
    if field.field_type in {"file", "path"} or field.path_kind == "file":
        return FileValidator()
    if field.field_type == "datetime":
        return DateTimeValidator(str(field.format or "%Y-%m-%d"))
    if field.field_type == "json":
        return JSONValidator(list if field.json_type == "array" else dict)
    if field.field_type == "password" or field.sensitive:
        return EncryptValidator()
    if field.field_type == "url" or field.format == "url":
        return URLValidator(default=str(_copy_default(field.default) or ""))
    if field.field_type == "select":
        return OptionsValidator(_option_values(field.options or []))
    if field.field_type == "boolean":
        return BoolValidator()
    if field.field_type == "number":
        if field.min is not None and field.max is not None:
            return RangeValidator(field.min, field.max)
        return RangeValidator(-999999, 999999)

    _ = group
    return StringValidator()


def _build_schema_field(group: str, field: PluginFieldDeclaration) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "key": f"{group}.{field.name}",
        "group": group,
        "name": field.name,
        "label": field.label,
        "type": field.field_type,
        "required": field.required,
    }
    if field.default is not PydanticUndefined:
        schema["default"] = _copy_default(field.default)
    if field.readonly:
        schema["readonly"] = True
    if field.sensitive:
        schema["sensitive"] = True
    if field.options is not None:
        schema["options"] = copy.deepcopy(field.options)

    _copy_optional(schema, "placeholder", field.placeholder)
    _copy_optional(schema, "help", field.help)
    _copy_optional(schema, "rows", field.rows)
    _copy_optional(schema, "size", field.size)
    _copy_optional(schema, "min", field.min)
    _copy_optional(schema, "max", field.max)
    _copy_optional(schema, "step", field.step)
    _copy_optional(schema, "format", field.format)
    _copy_optional(schema, "json_type", field.json_type)
    _copy_optional(schema, "item_type", field.item_type)
    _copy_optional(schema, "path_kind", field.path_kind)
    _copy_optional(schema, "action", field.action)
    _copy_optional(schema, "button", field.button)

    if field.extra:
        schema.update(copy.deepcopy(field.extra))
    return schema


def _copy_optional(schema: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        schema[key] = copy.deepcopy(value)


def _option_values(options: list[Any]) -> list[Any]:
    values: list[Any] = []
    for option in options:
        if isinstance(option, dict) and "value" in option:
            values.append(option["value"])
        else:
            values.append(option)
    return values


def _copy_default(default: Any) -> Any:
    if default is PydanticUndefined:
        return None
    return copy.deepcopy(default)


def _config_item_attr(group: str, name: str) -> str:
    return _safe_attr(f"{group}_{name}")


def _multiple_attr(group: str, name: str) -> str:
    return _safe_attr(name if not group else f"{group}_{name}")


def _safe_attr(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in value)
