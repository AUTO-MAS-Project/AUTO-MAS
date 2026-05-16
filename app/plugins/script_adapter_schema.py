from __future__ import annotations

import copy
from dataclasses import dataclass
from types import NoneType, UnionType
from typing import Any, Callable, Literal, get_args, get_origin

from pydantic import BaseModel
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


def build_script_adapter_schema_from_models(
    *,
    script_class_name: str,
    user_class_name: str,
    script_model: type[BaseModel],
    user_model: type[BaseModel],
    module: str,
    related_bindings: dict[str, str] | None = None,
    user_data_attribute: str | None = "UserData",
) -> ScriptAdapterSchemaArtifacts:
    """根据 Pydantic 分组模型生成脚本适配配置类和前端 schema。"""

    return build_script_adapter_schema(
        script_class_name=script_class_name,
        user_class_name=user_class_name,
        script_groups=build_field_groups_from_model(script_model),
        user_groups=build_field_groups_from_model(user_model),
        module=module,
        related_bindings=related_bindings,
        user_data_attribute=user_data_attribute,
    )


def build_field_groups_from_model(
    model: type[BaseModel],
) -> tuple[PluginFieldGroup, ...]:
    """把 Pydantic 顶层分组模型编译为声明式字段组。"""

    groups: list[PluginFieldGroup] = []
    for group_key, group_info in model.model_fields.items():
        group_model = _annotation_model(group_info.annotation)
        if group_model is None:
            group_label = group_info.title or group_info.description or "配置"
            groups.append(
                PluginFieldGroup(
                    key="default",
                    label=str(group_label),
                    fields=(_field_from_model_field(group_key, group_info),),
                )
            )
            continue

        group_label = group_info.title or group_info.description or group_key
        groups.append(
            PluginFieldGroup(
                key=group_key,
                label=str(group_label),
                fields=tuple(
                    _field_from_model_field(field_name, field_info)
                    for field_name, field_info in group_model.model_fields.items()
                ),
            )
        )

    return tuple(groups)


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


def _annotation_without_none(annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (UnionType, getattr(__import__("typing"), "Union")):
        non_none = [arg for arg in args if arg not in (None, NoneType, type(None))]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _annotation_model(annotation: Any) -> type[BaseModel] | None:
    annotation = _annotation_without_none(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _list_model(annotation: Any) -> type[BaseModel] | None:
    annotation = _annotation_without_none(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list and args:
        return _annotation_model(args[0])
    return None


def _literal_values(annotation: Any) -> list[Any] | None:
    annotation = _annotation_without_none(annotation)
    origin = get_origin(annotation)
    if origin is Literal:
        return list(get_args(annotation))
    return None


def _field_default(field_info: Any) -> Any:
    if field_info.default_factory is not None:
        return field_info.default_factory()
    if field_info.is_required():
        return PydanticUndefined
    return field_info.default


def _field_constraints(field_info: Any) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for item in field_info.metadata or []:
        for source, target in (("ge", "min"), ("gt", "min"), ("le", "max"), ("lt", "max")):
            value = getattr(item, source, None)
            if value is not None and target not in constraints:
                constraints[target] = value
        multiple_of = getattr(item, "multiple_of", None)
        if multiple_of is not None:
            constraints["step"] = multiple_of
    return constraints


def _field_type(annotation: Any, extra: dict[str, Any]) -> str:
    ui_type = extra.get("type") or extra.get("ui_type")
    if isinstance(ui_type, str) and ui_type:
        return ui_type

    annotation = _annotation_without_none(annotation)
    if _literal_values(annotation) is not None:
        return "select"
    if annotation is bool:
        return "boolean"
    if annotation is int or annotation is float:
        return "number"
    if annotation is dict or get_origin(annotation) is dict:
        return "json"
    if get_origin(annotation) is list:
        return "list"
    return "string"


def _field_options(annotation: Any, extra: dict[str, Any]) -> list[Any] | None:
    options = extra.get("options")
    if isinstance(options, list):
        return copy.deepcopy(options)
    values = _literal_values(annotation)
    if values is None:
        return None
    return [{"label": str(value), "value": value} for value in values]


def _field_from_model_field(name: str, field_info: Any) -> PluginFieldDeclaration:
    extra = dict(field_info.json_schema_extra or {})
    item_model = _list_model(field_info.annotation)
    if item_model is not None:
        multiple_groups = build_field_groups_from_model(item_model)
        return PluginFieldDeclaration(
            name=name,
            label=str(field_info.title or field_info.description or name),
            field_type="multiple",
            default=_field_default(field_info),
            multiple_groups=multiple_groups,
            multiple_class_name=str(extra.pop("multiple_class_name", "") or item_model.__name__),
            include_in_schema=bool(extra.pop("include_in_schema", False)),
            extra=extra,
        )

    constraints = _field_constraints(field_info)
    field_type = _field_type(field_info.annotation, extra)
    field_kwargs: dict[str, Any] = {
        "options": _field_options(field_info.annotation, extra),
        "placeholder": extra.pop("placeholder", None),
        "help": extra.pop("help", None),
        "readonly": bool(extra.pop("readonly", False)),
        "sensitive": bool(extra.pop("sensitive", False)),
        "required": bool(field_info.is_required()),
        "rows": extra.pop("rows", None),
        "size": extra.pop("size", None),
        "min": extra.pop("min", constraints.get("min")),
        "max": extra.pop("max", constraints.get("max")),
        "step": extra.pop("step", constraints.get("step")),
        "format": extra.pop("format", None),
        "json_type": extra.pop("json_type", None),
        "item_type": extra.pop("item_type", None),
        "path_kind": extra.pop("path_kind", None),
        "validator": extra.pop("validator", None),
        "related_config": extra.pop("related_config", None),
        "related_default": extra.pop("related_default", PydanticUndefined),
        "action": extra.pop("action", None),
        "button": extra.pop("button", None),
        "configurable": extra.pop("configurable", True),
        "legacy_group": extra.pop("legacy_group", None),
        "legacy_name": extra.pop("legacy_name", None),
        "virtual_handler": extra.pop("virtual_handler", None),
        "include_in_schema": bool(extra.pop("include_in_schema", True)),
    }
    if field_type == "json" and field_kwargs["json_type"] is None:
        field_kwargs["json_type"] = "object"
    if field_type == "folder" and field_kwargs["path_kind"] is None:
        field_kwargs["path_kind"] = "folder"
    if field_type in {"file", "path"} and field_kwargs["path_kind"] is None:
        field_kwargs["path_kind"] = "file"
    if field_type == "password":
        field_type = "string"
        field_kwargs["format"] = "password"
        field_kwargs["sensitive"] = True

    return PluginFieldDeclaration(
        name=name,
        label=str(field_info.title or field_info.description or name),
        field_type=field_type,
        default=_field_default(field_info),
        extra=extra,
        **field_kwargs,
    )


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
