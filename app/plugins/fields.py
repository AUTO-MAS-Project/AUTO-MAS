"""插件配置字段定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field
from pydantic_core import PydanticUndefined


PluginFieldFormat = Literal["password", "url", "email", "textarea"]
PluginFieldSize = Literal["small", "half", "medium", "large"]
PluginPathKind = Literal["file", "folder"]


def PluginField(
    default: Any = PydanticUndefined,
    *,
    format: PluginFieldFormat | None = None,
    rows: int | None = None,
    placeholder: str | None = None,
    help: str | None = None,
    ui_type: str | None = None,
    item_type: str | None = None,
    options: list[Any] | None = None,
    action: dict[str, Any] | None = None,
    configurable: bool | None = None,
    size: PluginFieldSize | None = None,
    step: int | float | None = None,
    path_kind: PluginPathKind | None = None,
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
    if ui_type is not None:
        extra["type"] = ui_type
    if item_type is not None:
        extra["item_type"] = item_type
    if options is not None:
        extra["options"] = options
    if action is not None:
        extra["action"] = action
    if configurable is not None:
        extra["configurable"] = configurable
    if size is not None:
        extra["size"] = size
    if step is not None:
        extra["step"] = step
    if path_kind is not None:
        extra["path_kind"] = path_kind
    if filters is not None:
        extra["filters"] = filters

    field_kwargs = dict(kwargs)
    if extra:
        field_kwargs["json_schema_extra"] = extra

    if default is PydanticUndefined:
        return Field(**field_kwargs)
    return Field(default, **field_kwargs)


__all__ = ["PluginField", "PluginFieldFormat", "PluginFieldSize", "PluginPathKind"]
