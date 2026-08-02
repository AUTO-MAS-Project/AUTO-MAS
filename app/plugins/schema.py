#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import copy
import importlib
import inspect
from enum import Enum
from types import NoneType, UnionType
from typing import Annotated, Any, Dict, Literal, Mapping, Union, cast, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .fields import PLUGIN_FIELD_MARKER
from .pypi_site import iter_plugin_entry_points




def normalize_schema_options(
    options: list[Any] | tuple[Any, ...] | None,
    option_labels: Mapping[Any, str] | None = None,
) -> list[dict[str, Any]] | None:
    """Normalize schema options to the frontend `{label, value}` shape."""

    if options is None:
        return None

    labels = option_labels if isinstance(option_labels, Mapping) else {}
    normalized: list[dict[str, Any]] = []
    for option in options:
        if isinstance(option, dict) and "value" in option:
            item = copy.deepcopy(option)
            if "label" not in item:
                item["label"] = _option_label(item["value"], labels)
            normalized.append(item)
            continue

        normalized.append(
            {
                "label": _option_label(option, labels),
                "value": copy.deepcopy(option),
            }
        )
    return normalized


def option_values(options: list[Any] | tuple[Any, ...] | None) -> list[Any]:
    """Extract runtime values from normalized or shorthand schema options."""

    values: list[Any] = []
    for option in options or []:
        if isinstance(option, dict) and "value" in option:
            values.append(option["value"])
        else:
            values.append(option)
    return values


def _option_label(value: Any, labels: Mapping[Any, str]) -> str:
    for key, label in labels.items():
        if key == value:
            return str(label)
    return str(value)


class PluginSchemaError(Exception):
    """插件 Schema 与配置处理错误。"""




class PluginSchemaManager:
    """加载插件 schema.py 中的 Config 模型并校验配置。"""

    def load_schema(self, plugin_name: str) -> Dict[str, Dict[str, Any]]:
        """从插件 Entry Point 同包的 schema.py 加载 Config 模型。"""
        model = self._load_config_model(plugin_name)
        return self.build_schema_from_model(plugin_name, model)

    def _load_config_model(self, plugin_name: str) -> type[BaseModel]:
        entry_point_name = str(plugin_name or "").strip()
        if not entry_point_name:
            raise PluginSchemaError("插件名不能为空")
        entry_point = next(
            (
                item
                for item in iter_plugin_entry_points()
                if str(getattr(item, "name", "")).strip() == entry_point_name
            ),
            None,
        )
        if entry_point is None:
            raise PluginSchemaError(f"未找到插件 Entry Point: {plugin_name}")

        module_name = str(getattr(entry_point, "module", "") or "").strip()
        package_name = module_name.rsplit(".", 1)[0] if "." in module_name else module_name
        if not package_name:
            raise PluginSchemaError(f"插件 Entry Point 缺少模块名: {plugin_name}")

        schema_module_name = f"{package_name}.schema"
        try:
            schema_module = importlib.import_module(schema_module_name)
        except Exception as e:
            raise PluginSchemaError(
                f"导入插件 Schema 失败: {plugin_name}, module={schema_module_name}, "
                f"error={type(e).__name__}: {e}"
            ) from e

        model = getattr(schema_module, "Config", None)
        if not inspect.isclass(model) or not issubclass(model, BaseModel):
            raise PluginSchemaError(
                f"插件 schema.py 必须导出 Config: BaseModel: {plugin_name}"
            )
        return model

    def _validate_plugin_fields(
        self,
        plugin_name: str,
        model_cls: type[BaseModel],
        prefix: str = "",
    ) -> None:
        for field_name, field_info in model_cls.model_fields.items():
            path = f"{prefix}.{field_name}" if prefix else field_name
            extra = field_info.json_schema_extra
            if not isinstance(extra, dict) or extra.get(PLUGIN_FIELD_MARKER) is not True:
                raise PluginSchemaError(
                    f"插件 Schema 字段必须使用 PluginField: {plugin_name}.{path}"
                )
            annotation = field_info.annotation
            nested = self._nested_model_type(annotation)
            if nested is not None:
                self._validate_plugin_fields(plugin_name, nested, path)

    def _nested_model_type(self, annotation: Any) -> type[BaseModel] | None:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is Annotated and args:
            return self._nested_model_type(args[0])
        if origin in (Union, UnionType):
            models = [self._nested_model_type(arg) for arg in args if arg not in (NoneType, type(None))]
            models = [model for model in models if model is not None]
            return models[0] if len(models) == 1 else None
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            return annotation
        return None











    def build_schema_from_model(
        self,
        plugin_name: str,
        model_cls: type[BaseModel],
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 Pydantic BaseModel 类型推导 schema 字段定义。

        Args:
            plugin_name (str): 插件名。
            model_cls (type[BaseModel]): Pydantic 配置模型类型。

        Returns:
            Dict[str, Dict[str, Any]]: 推导出的 schema 字段映射。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 字段默认值工厂执行失败；
                2) `json_schema_extra` 不是字典对象。
        """
        self._validate_plugin_fields(plugin_name, model_cls)
        result: Dict[str, Dict[str, Any]] = {}
        for field_name, field_info in model_cls.model_fields.items():
            annotation = field_info.annotation
            type_expr = self._type_to_expr(annotation)
            field_schema: Dict[str, Any] = {
                "type": type_expr,
                "required": bool(field_info.is_required()),
            }
            literal_values = self._literal_values(annotation)
            if literal_values is not None:
                field_schema["enum"] = copy.deepcopy(literal_values)
                if not self._is_list_annotation(annotation):
                    field_schema["type"] = self._enum_base_type(literal_values)

            if field_info.description is not None:
                field_schema["description"] = str(field_info.description)

            if field_info.title is not None:
                field_schema["title"] = str(field_info.title)

            if field_info.examples is not None:
                field_schema["examples"] = copy.deepcopy(field_info.examples)

            if self._annotation_allows_none(annotation):
                field_schema["nullable"] = True

            constraints = self._constraints_from_field_metadata(field_info.metadata)
            if constraints:
                field_schema["constraints"] = constraints

            item_type = self._list_item_type(annotation)
            if item_type is not None:
                field_schema.setdefault("item_type", item_type)

            if not field_info.is_required():
                if field_info.default_factory is not None:
                    try:
                        field_schema["default"] = field_info.get_default(
                            call_default_factory=True
                        )
                    except Exception as e:
                        raise PluginSchemaError(
                            f"Config 字段 default_factory 执行失败: {plugin_name}.{field_name}, "
                            f"error={type(e).__name__}: {e}"
                        ) from e
                else:
                    field_schema["default"] = copy.deepcopy(field_info.default)

            extra = cast(dict[str, Any], field_info.json_schema_extra)
            field_schema.update(copy.deepcopy(extra))
            field_schema.pop(PLUGIN_FIELD_MARKER, None)

            option_labels = field_schema.pop("option_labels", None)
            labels = option_labels if isinstance(option_labels, dict) else None
            options = field_schema.get("options")
            if isinstance(options, list):
                field_schema["options"] = normalize_schema_options(options, labels)
            elif labels is not None and isinstance(field_schema.get("enum"), list):
                field_schema["options"] = normalize_schema_options(field_schema["enum"], labels)

            result[field_name] = field_schema

        return result

    def _constraints_from_field_metadata(self, metadata: Any) -> Dict[str, Any]:
        constraints: Dict[str, Any] = {}
        for item in metadata or []:
            for name in (
                "gt",
                "ge",
                "lt",
                "le",
                "multiple_of",
                "min_length",
                "max_length",
                "pattern",
            ):
                value = getattr(item, name, None)
                if value is not None:
                    constraints[name] = value
        return constraints

    def _list_item_type(self, annotation: Any) -> str | None:
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Annotated and args:
            return self._list_item_type(args[0])

        if origin is Union or origin is UnionType:
            non_none_args = [arg for arg in args if arg not in (NoneType, type(None))]
            if len(non_none_args) == 1:
                return self._list_item_type(non_none_args[0])
            return None

        if origin is not list or not args:
            return None

        item = args[0]
        item_origin = get_origin(item)
        if item_origin is Literal:
            return self._enum_base_type(list(get_args(item)))
        if item is str:
            return "string"
        if item is bool:
            return "boolean"
        if item is int or item is float:
            return "number"
        if inspect.isclass(item) and issubclass(item, BaseModel):
            return "object"
        if inspect.isclass(item) and issubclass(item, Enum):
            return "string"
        return None

    def _annotation_allows_none(self, annotation: Any) -> bool:
        """
        判断类型注解是否允许 None。

        Args:
            annotation (Any): 待判断类型注解。

        Returns:
            bool: 允许 None 返回 True，否则返回 False。
        """
        if annotation in (NoneType, type(None)):
            return True

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Annotated and args:
            return self._annotation_allows_none(args[0])

        if origin in (Union, UnionType):
            return any(self._annotation_allows_none(arg) for arg in args)

        return False





    def apply_defaults_and_validate(
        self,
        plugin_name: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用插件 Config 模型补齐默认值并严格校验配置。"""
        model = self._load_config_model(plugin_name)
        try:
            validated = model.model_validate(copy.deepcopy(config), strict=True)
        except ValidationError as e:
            raise PluginSchemaError(
                self._format_value_error(plugin_name, "<root>", config, e)
            ) from e
        return validated.model_dump(mode="python")


    def _literal_values(self, annotation: Any) -> list[Any] | None:
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Annotated and args:
            return self._literal_values(args[0])

        if origin is Literal:
            return list(args)

        if origin is list and args:
            return self._literal_values(args[0])

        return None

    def _is_list_annotation(self, annotation: Any) -> bool:
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Annotated and args:
            return self._is_list_annotation(args[0])

        if origin is Union or origin is UnionType:
            return any(self._is_list_annotation(arg) for arg in args if arg not in (NoneType, type(None)))

        return origin is list

    @staticmethod
    def _enum_base_type(values: list[Any]) -> str:
        if not values:
            return "string"
        if all(isinstance(item, bool) for item in values):
            return "boolean"
        if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
            return "integer"
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in values):
            return "number"
        return "string"





    def _format_value_error(
        self,
        plugin_name: str,
        field_name: str,
        value: Any,
        error: ValidationError,
    ) -> str:
        """
        格式化字段值校验错误。

        Args:
            plugin_name (str): 插件名。
            field_name (str): 字段名。
            value (Any): 待校验原始值。
            error (ValidationError): Pydantic 校验错误对象。

        Returns:
            str: 中文错误消息。
        """
        first = error.errors()[0] if error.errors() else {"msg": str(error), "loc": ()}
        loc = first.get("loc", ())
        suffix = "" if not loc else "." + ".".join(str(item) for item in loc)

        value_type = type(value).__name__
        value_preview = repr(value)
        if len(value_preview) > 120:
            value_preview = value_preview[:117] + "..."

        return (
            f"配置项校验失败: {plugin_name}.{field_name}{suffix}, "
            f"错误={first.get('msg', '未知错误')}, "
            f"实际类型={value_type}, 实际值={value_preview}"
        )

    def _type_to_expr(self, raw_type: Any) -> str:
        """
        将类型对象或表达式转换为统一字符串，便于序列化到 API 输出。

        Args:
            raw_type (Any): 原始类型描述。

        Returns:
            str: 统一类型表达式字符串。
        """
        if isinstance(raw_type, str):
            return raw_type.strip()

        if raw_type is Any:
            return "Any"

        if raw_type is str:
            return "string"
        if raw_type is int:
            return "integer"
        if raw_type is float:
            return "number"
        if raw_type is bool:
            return "boolean"

        origin = get_origin(raw_type)
        args = get_args(raw_type)

        if origin is Literal:
            return self._enum_base_type(list(args))

        if origin is list:
            inner = self._type_to_expr(args[0] if args else Any)
            return f"list[{inner}]"

        if origin is dict:
            key_type = self._type_to_expr(args[0] if len(args) > 0 else str)
            value_type = self._type_to_expr(args[1] if len(args) > 1 else Any)
            return f"dict[{key_type}, {value_type}]"

        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return f"tuple[{self._type_to_expr(args[0])}, ...]"
            return "tuple[" + ", ".join(self._type_to_expr(arg) for arg in args) + "]"

        return str(raw_type).replace("typing.", "")
