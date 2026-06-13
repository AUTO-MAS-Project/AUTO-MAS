"""插件配置字段定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field
from pydantic_core import PydanticUndefined


PluginFieldFormat = Literal["password", "url", "email", "textarea"]
PluginFieldSize = Literal[
    "1/1",
    "1/2",
    "1/3",
    "2/3",
    "1/4",
    "3/4",
    "small",
    "half",
    "medium",
    "large",
]
PluginPathKind = Literal["file", "folder"]


@dataclass(frozen=True, slots=True)
class PluginFieldDeclaration:
    """声明式配置字段。

    这类字段不是 Pydantic 字段，而是脚本适配框架生成运行时 ConfigBase
    和前端 SchemaForm schema 的唯一输入。
    """

    name: str
    label: str
    field_type: str
    default: Any = PydanticUndefined
    options: list[Any] | None = None
    option_labels: dict[Any, str] | None = None
    options_provider: dict[str, Any] | None = None
    placeholder: str | None = None
    help: str | None = None
    hidden: bool = False
    readonly: bool = False
    sensitive: bool = False
    required: bool = False
    rows: int | None = None
    size: PluginFieldSize | None = None
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    format: str | None = None
    json_type: Literal["object", "array"] | None = None
    item_type: str | None = None
    path_kind: PluginPathKind | None = None
    validator: str | None = None
    related_config: str | None = None
    related_default: Any = PydanticUndefined
    action: dict[str, Any] | None = None
    button: dict[str, Any] | None = None
    configurable: bool = True
    legacy_group: str | None = None
    legacy_name: str | None = None
    virtual_handler: Any | None = None
    multiple_groups: tuple["PluginFieldGroup", ...] = ()
    multiple_class_name: str | None = None
    include_in_schema: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginFieldGroup:
    """声明式配置分组。"""

    key: str
    label: str
    fields: tuple[PluginFieldDeclaration, ...]


class PluginFieldFactory:
    """插件字段工厂，兼容 Pydantic Field 写法并提供声明式字段入口。"""

    def __call__(
        self,
        default: Any = PydanticUndefined,
        *,
        format: PluginFieldFormat | None = None,
        rows: int | None = None,
        placeholder: str | None = None,
        help: str | None = None,
        hidden: bool | None = None,
        ui_type: str | None = None,
        json_type: Literal["object", "array"] | None = None,
        item_type: str | None = None,
        options: list[Any] | None = None,
        option_labels: dict[Any, str] | None = None,
        options_provider: dict[str, Any] | None = None,
        action: dict[str, Any] | None = None,
        button: dict[str, Any] | None = None,
        configurable: bool | None = None,
        readonly: bool | None = None,
        sensitive: bool | None = None,
        size: PluginFieldSize | None = None,
        step: int | float | None = None,
        path_kind: PluginPathKind | None = None,
        validator: str | None = None,
        related_config: str | None = None,
        related_default: Any = PydanticUndefined,
        legacy_group: str | None = None,
        legacy_name: str | None = None,
        virtual_handler: Any | None = None,
        include_in_schema: bool | None = None,
        filters: list[dict[str, Any]] | None = None,
        json_schema_extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """声明插件配置字段，并把插件 UI 元数据写入 Pydantic schema extra。"""

        extra = dict(json_schema_extra or {})
        if format is not None:
            extra["format"] = format
        if rows is not None:
            extra["rows"] = rows
        if placeholder is not None:
            extra["placeholder"] = placeholder
        if help is not None:
            extra["help"] = help
        if hidden is not None:
            extra["hidden"] = hidden
        if ui_type is not None:
            extra["type"] = ui_type
        if json_type is not None:
            extra["json_type"] = json_type
        if item_type is not None:
            extra["item_type"] = item_type
        if options is not None:
            extra["options"] = options
        if option_labels is not None:
            extra["option_labels"] = option_labels
        if options_provider is not None:
            extra["options_provider"] = options_provider
        if action is not None:
            extra["action"] = action
        if button is not None:
            extra["button"] = button
        if configurable is not None:
            extra["configurable"] = configurable
        if readonly is not None:
            extra["readonly"] = readonly
        if sensitive is not None:
            extra["sensitive"] = sensitive
        if size is not None:
            extra["size"] = size
        if step is not None:
            extra["step"] = step
        if path_kind is not None:
            extra["path_kind"] = path_kind
        if validator is not None:
            extra["validator"] = validator
        if related_config is not None:
            extra["related_config"] = related_config
        if related_default is not PydanticUndefined:
            extra["related_default"] = related_default
        if legacy_group is not None:
            extra["legacy_group"] = legacy_group
        if legacy_name is not None:
            extra["legacy_name"] = legacy_name
        if virtual_handler is not None:
            extra["virtual_handler"] = virtual_handler
        if include_in_schema is not None:
            extra["include_in_schema"] = include_in_schema
        if filters is not None:
            extra["filters"] = filters

        field_kwargs = dict(kwargs)
        if extra:
            field_kwargs["json_schema_extra"] = extra

        if default is PydanticUndefined:
            return Field(**field_kwargs)
        return Field(default, **field_kwargs)

    def group(
        self,
        key: str,
        label: str,
        fields: list[PluginFieldDeclaration] | tuple[PluginFieldDeclaration, ...],
    ) -> PluginFieldGroup:
        return _group(key, label, fields)

    def string(self, name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
        return _string(name, label, default, **kwargs)

    def boolean(self, name: str, label: str, default: bool = False, **kwargs: Any) -> PluginFieldDeclaration:
        return _boolean(name, label, default, **kwargs)

    def select(
        self,
        name: str,
        label: str,
        default: Any,
        options: list[Any] | tuple[Any, ...],
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _select(name, label, default, options, **kwargs)

    def number(
        self,
        name: str,
        label: str,
        default: int | float = 0,
        *,
        min: int | float | None = None,
        max: int | float | None = None,
        step: int | float | None = None,
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _number(name, label, default, min=min, max=max, step=step, **kwargs)

    def file(self, name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
        return _file(name, label, default, **kwargs)

    def folder(self, name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
        return _folder(name, label, default, **kwargs)

    def json(
        self,
        name: str,
        label: str,
        default: str = "{ }",
        *,
        json_type: Literal["object", "array"] = "object",
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _json(name, label, default, json_type=json_type, **kwargs)

    def datetime(
        self,
        name: str,
        label: str,
        default: str,
        *,
        format: str = "%Y-%m-%d",
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _datetime(name, label, default, format=format, **kwargs)

    def related_id(
        self,
        name: str,
        label: str,
        default: str = "-",
        *,
        related_config: str,
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _related_id(name, label, default, related_config=related_config, **kwargs)

    def virtual(
        self,
        name: str,
        label: str,
        default: str = "",
        *,
        handler: Any,
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _virtual(name, label, default, handler=handler, **kwargs)

    def tag(
        self,
        name: str,
        label: str,
        default: str = "[ ]",
        *,
        handler: Any | None = None,
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _tag(name, label, default, handler=handler, **kwargs)

    def button(self, name: str, label: str, button: dict[str, Any], **kwargs: Any) -> PluginFieldDeclaration:
        return _button(name, label, button, **kwargs)

    def multiple(
        self,
        name: str,
        label: str,
        groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...],
        *,
        class_name: str | None = None,
        include_in_schema: bool = False,
        **kwargs: Any,
    ) -> PluginFieldDeclaration:
        return _multiple(
            name,
            label,
            groups,
            class_name=class_name,
            include_in_schema=include_in_schema,
            **kwargs,
        )


def _declaration(
    name: str,
    label: str,
    field_type: str,
    default: Any = PydanticUndefined,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    """构建声明式字段，供 PluginField.* 快捷入口复用。"""

    known_keys = {
        "options",
        "option_labels",
        "options_provider",
        "placeholder",
        "help",
        "hidden",
        "readonly",
        "sensitive",
        "required",
        "rows",
        "size",
        "min",
        "max",
        "step",
        "format",
        "json_type",
        "item_type",
        "path_kind",
        "validator",
        "related_config",
        "related_default",
        "action",
        "button",
        "configurable",
        "legacy_group",
        "legacy_name",
        "virtual_handler",
        "multiple_groups",
        "multiple_class_name",
        "include_in_schema",
    }
    declaration_kwargs = {key: kwargs.pop(key) for key in list(kwargs) if key in known_keys}
    declaration_kwargs["extra"] = dict(kwargs)
    return PluginFieldDeclaration(
        name=name,
        label=label,
        field_type=field_type,
        default=default,
        **declaration_kwargs,
    )


def _group(
    key: str,
    label: str,
    fields: list[PluginFieldDeclaration] | tuple[PluginFieldDeclaration, ...],
) -> PluginFieldGroup:
    return PluginFieldGroup(key=key, label=label, fields=tuple(fields))


def _string(name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
    return _declaration(name, label, "string", default, **kwargs)


def _boolean(name: str, label: str, default: bool = False, **kwargs: Any) -> PluginFieldDeclaration:
    return _declaration(name, label, "boolean", default, **kwargs)


def _select(
    name: str,
    label: str,
    default: Any,
    options: list[Any] | tuple[Any, ...],
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(name, label, "select", default, options=list(options), **kwargs)


def _number(
    name: str,
    label: str,
    default: int | float = 0,
    *,
    min: int | float | None = None,
    max: int | float | None = None,
    step: int | float | None = None,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(name, label, "number", default, min=min, max=max, step=step, **kwargs)


def _file(name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
    return _declaration(name, label, "file", default, path_kind="file", **kwargs)


def _folder(name: str, label: str, default: str = "", **kwargs: Any) -> PluginFieldDeclaration:
    return _declaration(name, label, "folder", default, path_kind="folder", **kwargs)


def _json(
    name: str,
    label: str,
    default: str = "{ }",
    *,
    json_type: Literal["object", "array"] = "object",
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(name, label, "json", default, json_type=json_type, **kwargs)


def _datetime(
    name: str,
    label: str,
    default: str,
    *,
    format: str = "%Y-%m-%d",
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(name, label, "datetime", default, format=format, **kwargs)


def _related_id(
    name: str,
    label: str,
    default: str = "-",
    *,
    related_config: str,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(
        name,
        label,
        "related-id",
        default,
        related_config=related_config,
        related_default=kwargs.pop("related_default", default),
        **kwargs,
    )


def _virtual(
    name: str,
    label: str,
    default: str = "",
    *,
    handler: Any,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(
        name,
        label,
        "readonly",
        default,
        readonly=True,
        virtual_handler=handler,
        **kwargs,
    )


def _tag(
    name: str,
    label: str,
    default: str = "[ ]",
    *,
    handler: Any | None = None,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    if handler is not None:
        kwargs["virtual_handler"] = handler
    kwargs.setdefault("hidden", True)
    return _declaration(
        name,
        label,
        "tag",
        default,
        readonly=True,
        **kwargs,
    )


def _button(name: str, label: str, button: dict[str, Any], **kwargs: Any) -> PluginFieldDeclaration:
    return _declaration(
        name,
        label,
        "button",
        configurable=False,
        button=button,
        **kwargs,
    )


def _multiple(
    name: str,
    label: str,
    groups: list[PluginFieldGroup] | tuple[PluginFieldGroup, ...],
    *,
    class_name: str | None = None,
    include_in_schema: bool = False,
    **kwargs: Any,
) -> PluginFieldDeclaration:
    return _declaration(
        name,
        label,
        "multiple",
        configurable=False,
        multiple_groups=tuple(groups),
        multiple_class_name=class_name,
        include_in_schema=include_in_schema,
        **kwargs,
    )


PluginField = PluginFieldFactory()


__all__ = [
    "PluginField",
    "PluginFieldDeclaration",
    "PluginFieldFactory",
    "PluginFieldFormat",
    "PluginFieldGroup",
    "PluginFieldSize",
    "PluginPathKind",
]
