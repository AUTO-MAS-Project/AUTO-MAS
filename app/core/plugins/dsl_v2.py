#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path as _Path
from types import UnionType
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, ConfigDict
from pydantic_core import PydanticUndefined


NoneType = type(None)
ModelT = TypeVar("ModelT", bound="PluginConfigModel")


class Codec(Protocol):
    """字段编解码协议：前端值、运行时值、存储值三者互转。"""

    def from_frontend(self, value: Any) -> Any: ...

    def to_frontend(self, value: Any) -> Any: ...

    def from_storage(self, value: Any) -> Any: ...

    def to_storage(self, value: Any) -> Any: ...


class IdentityCodec:
    """默认编解码器：不做转换。"""

    def from_frontend(self, value: Any) -> Any:
        return value

    def to_frontend(self, value: Any) -> Any:
        return value

    def from_storage(self, value: Any) -> Any:
        return value

    def to_storage(self, value: Any) -> Any:
        return value


class PathCodec:
    """路径示例编解码器。

    允许前端返回字符串或对象：
    - "C:/tmp/a.txt"
    - {"path": "C:/tmp/a.txt", ...}
    """

    def from_frontend(self, value: Any) -> Any:
        if isinstance(value, dict) and "path" in value:
            return str(value.get("path") or "")
        if value is None:
            return ""
        return str(value)

    def to_frontend(self, value: Any) -> Any:
        text = "" if value is None else str(value)
        return {"path": text}

    def from_storage(self, value: Any) -> Any:
        if value is None:
            return ""
        return str(value)

    def to_storage(self, value: Any) -> Any:
        text = "" if value is None else str(value)
        if not text:
            return text
        return str(_Path(text))


class CodecRegistry:
    """Codec 注册表。"""

    def __init__(self) -> None:
        self._codecs: Dict[str, Codec] = {}
        self.register("identity", IdentityCodec())
        self.register("path", PathCodec())

    def register(self, name: str, codec: Codec) -> None:
        key = str(name).strip()
        if not key:
            raise ValueError("codec 名称不能为空")
        self._codecs[key] = codec

    def get(self, name: str) -> Codec:
        codec = self._codecs.get(name)
        if codec is None:
            raise KeyError(f"未注册的 codec: {name}")
        return codec


GLOBAL_CODEC_REGISTRY = CodecRegistry()
FIELD_UI_EXTRA_ATTR = "__plg_field_ui_extra__"


@dataclass(frozen=True)
class TypePreset:
    """类型预设元数据。

    说明：
    - schema_type / item_type 对齐现有插件 schema 协议
    - ui 为前端组件元数据
    - codec 可为注册名或实例
    """

    schema_type: str
    item_type: str | None = None
    format: str | None = None
    codec: str | Codec | None = None
    ui: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Desc:
    """字段描述元数据，用于声明 description。"""

    text: str


def preset(
    py_type: Any,
    *,
    schema_type: str,
    item_type: str | None = None,
    format: str | None = None,
    codec: str | Codec | None = None,
    widget: str | None = None,
    ui: Optional[Dict[str, Any]] = None,
) -> Any:
    """声明一个可复用预定义类型。"""
    ui_data = deepcopy(ui or {})
    if widget and "widget" not in ui_data:
        ui_data["widget"] = widget
    return Annotated[
        py_type,
        TypePreset(
            schema_type=schema_type,
            item_type=item_type,
            format=format,
            codec=codec,
            ui=ui_data,
        ),
    ]


def describe(py_type: Any, text: str) -> Any:
    """为类型附加 description 元数据。"""
    return Annotated[py_type, Desc(text)]


def _unwrap_annotated(annotation: Any) -> tuple[Any, list[Any]]:
    meta: list[Any] = []
    current = annotation
    while get_origin(current) is Annotated:
        args = list(get_args(current))
        if not args:
            break
        current = args[0]
        meta.extend(args[1:])
    return current, meta


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin not in (Union, UnionType):
        return annotation, False

    args = get_args(annotation)
    non_none_args = [item for item in args if item is not NoneType]
    if len(non_none_args) == 1 and len(non_none_args) != len(args):
        return non_none_args[0], True
    return annotation, False


def _infer_schema_type(annotation: Any) -> str:
    if annotation is bool:
        return "boolean"
    if annotation is str:
        return "string"
    if annotation in (int, float):
        return "number"

    origin = get_origin(annotation)
    if origin in (list, List):
        return "list"
    if origin in (dict, Dict, Mapping, MutableMapping):
        return "key_value"

    return "string"


def _infer_item_type(annotation: Any) -> str:
    base, _ = _unwrap_annotated(annotation)
    base, _ = _unwrap_optional(base)

    if base is str:
        return "string"
    if base is bool:
        return "boolean"
    if base in (int, float):
        return "number"
    return "any"


def _resolve_codec(codec: str | Codec | None, registry: CodecRegistry) -> Codec:
    if codec is None:
        return registry.get("identity")
    if isinstance(codec, str):
        return registry.get(codec)
    return codec


def _invoke_default_factory(factory: Any) -> Any:
    """兼容 pydantic default_factory 的 0/1 参数签名。"""
    try:
        return factory()
    except TypeError:
        return factory({})


@dataclass
class _FieldRuntime:
    name: str
    schema_type: str
    item_type: str | None
    nullable: bool
    required: bool
    default: Any
    has_default: bool
    description: str | None
    format: str | None
    ui: Dict[str, Any]
    codec: Codec
    item_codec: Codec


class PluginConfigModel(BaseModel):
    """DSL v2 配置模型基类。

    设计目标：
    - 用类型声明配置字段（尽量保持语法干净）
    - 通过预定义类型 + codec 实现前后端/存储值转换
    - 允许在 Config 类中定义自定义校验与后处理
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def codec_registry(cls) -> CodecRegistry:
        return GLOBAL_CODEC_REGISTRY

    @classmethod
    def validate_config(cls, data: "PluginConfigModel") -> None:
        """自定义跨字段校验入口（可选覆写）。"""

    def post_load(self) -> "PluginConfigModel":
        """加载后处理（可选覆写）。"""
        return self

    def pre_save(self) -> "PluginConfigModel":
        """保存前处理（可选覆写）。"""
        return self

    @classmethod
    def _build_runtime_fields(cls) -> Dict[str, _FieldRuntime]:
        hints = get_type_hints(cls, include_extras=True)
        runtime_fields: Dict[str, _FieldRuntime] = {}
        registry = cls.codec_registry()
        class_ui_extra = getattr(cls, FIELD_UI_EXTRA_ATTR, {})
        if not isinstance(class_ui_extra, dict):
            class_ui_extra = {}

        # 支持将额外前端元数据直接写在 Config 类内：__extra__ = {...}
        inline_extra = getattr(cls, "__extra__", {})
        if not isinstance(inline_extra, dict):
            inline_extra = {}

        merged_ui_extra: Dict[str, Any] = deepcopy(class_ui_extra)
        for field_name, payload in inline_extra.items():
            if not isinstance(payload, dict):
                continue
            current = merged_ui_extra.get(field_name, {})
            if not isinstance(current, dict):
                current = {}
            current.update(deepcopy(payload))
            merged_ui_extra[field_name] = current

        for field_name, field_info in cls.model_fields.items():
            hint = hints.get(field_name, field_info.annotation)

            ann, nullable = _unwrap_optional(hint)
            ann_base, metas = _unwrap_annotated(ann)
            preset_meta = next((m for m in metas if isinstance(m, TypePreset)), None)
            desc_meta = next((m for m in metas if isinstance(m, Desc)), None)

            schema_type = (
                preset_meta.schema_type if preset_meta else _infer_schema_type(ann_base)
            )
            item_type = preset_meta.item_type if preset_meta else None

            item_codec: Codec = registry.get("identity")
            if schema_type in {"list", "table"}:
                origin = get_origin(ann_base)
                if origin in (list, List):
                    item_ann = get_args(ann_base)[0] if get_args(ann_base) else Any
                    item_base, item_metas = _unwrap_annotated(item_ann)
                    item_preset = next(
                        (m for m in item_metas if isinstance(m, TypePreset)),
                        None,
                    )
                    if item_type is None:
                        item_type = _infer_item_type(item_base)
                    if item_preset is not None:
                        item_codec = _resolve_codec(item_preset.codec, registry)

            if schema_type == "key_value":
                origin = get_origin(ann_base)
                if origin in (dict, Dict, Mapping, MutableMapping):
                    args = get_args(ann_base)
                    value_ann = args[1] if len(args) == 2 else Any
                    value_base, value_metas = _unwrap_annotated(value_ann)
                    value_preset = next(
                        (m for m in value_metas if isinstance(m, TypePreset)),
                        None,
                    )
                    if item_type is None:
                        item_type = _infer_item_type(value_base)
                    if value_preset is not None:
                        item_codec = _resolve_codec(value_preset.codec, registry)

            if item_type is None and schema_type == "list":
                item_type = "any"
            if item_type is None and schema_type == "table":
                item_type = "object"

            required = field_info.is_required()
            has_default = (
                field_info.default is not PydanticUndefined
                or field_info.default_factory is not None
            )

            if field_info.default_factory is not None:
                default_value = _invoke_default_factory(field_info.default_factory)
            elif field_info.default is not PydanticUndefined:
                default_value = deepcopy(field_info.default)
            else:
                default_value = None

            runtime_fields[field_name] = _FieldRuntime(
                name=field_name,
                schema_type=schema_type,
                item_type=item_type,
                nullable=nullable,
                required=required,
                default=default_value,
                has_default=has_default,
                description=desc_meta.text if desc_meta else field_info.description,
                format=preset_meta.format if preset_meta else None,
                ui=deepcopy(preset_meta.ui) if preset_meta else {},
                codec=_resolve_codec(
                    preset_meta.codec if preset_meta else None, registry
                ),
                item_codec=item_codec,
            )

            field_extra = merged_ui_extra.get(field_name)
            if isinstance(field_extra, dict):
                extra_copy = deepcopy(field_extra)
                if "description" in extra_copy and isinstance(
                    extra_copy["description"], str
                ):
                    runtime_fields[field_name].description = extra_copy.pop(
                        "description"
                    )
                if "format" in extra_copy and isinstance(extra_copy["format"], str):
                    runtime_fields[field_name].format = extra_copy.pop("format")
                if "item_type" in extra_copy and isinstance(
                    extra_copy["item_type"], str
                ):
                    runtime_fields[field_name].item_type = extra_copy.pop("item_type")

                nested_ui = extra_copy.pop("ui", None)
                if isinstance(nested_ui, dict):
                    runtime_fields[field_name].ui.update(deepcopy(nested_ui))

                runtime_fields[field_name].ui.update(extra_copy)

        return runtime_fields

    @classmethod
    def to_schema_dict(cls) -> Dict[str, Dict[str, Any]]:
        """导出与现有插件 schema 兼容的字典结构。"""
        result: Dict[str, Dict[str, Any]] = {}

        for name, runtime in cls._build_runtime_fields().items():
            item: Dict[str, Any] = {
                "type": runtime.schema_type,
                "required": runtime.required,
            }

            if runtime.has_default:
                item["default"] = deepcopy(runtime.default)
            if runtime.description:
                item["description"] = runtime.description
            if runtime.nullable:
                item["nullable"] = True
            if runtime.item_type is not None and runtime.schema_type in {
                "list",
                "key_value",
                "table",
            }:
                item["item_type"] = runtime.item_type
            if runtime.format:
                item["format"] = runtime.format
            if runtime.ui:
                item["ui"] = deepcopy(runtime.ui)

            result[name] = item

        return result

    @classmethod
    def _convert_input_values(cls, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        converted = deepcopy(data)
        fields = cls._build_runtime_fields()

        for name, runtime in fields.items():
            if name not in converted:
                continue

            value = converted[name]
            if runtime.schema_type in {"list", "table"} and isinstance(value, list):
                if source == "frontend":
                    converted[name] = [
                        runtime.item_codec.from_frontend(item) for item in value
                    ]
                else:
                    converted[name] = [
                        runtime.item_codec.from_storage(item) for item in value
                    ]
                continue

            if runtime.schema_type == "key_value" and isinstance(value, dict):
                if source == "frontend":
                    converted[name] = {
                        str(key): runtime.item_codec.from_frontend(item)
                        for key, item in value.items()
                    }
                else:
                    converted[name] = {
                        str(key): runtime.item_codec.from_storage(item)
                        for key, item in value.items()
                    }
                continue

            if source == "frontend":
                converted[name] = runtime.codec.from_frontend(value)
            else:
                converted[name] = runtime.codec.from_storage(value)

        return converted

    def _convert_output_values(self, target: str) -> Dict[str, Any]:
        dumped = self.model_dump(mode="python")
        fields = self._build_runtime_fields()

        for name, runtime in fields.items():
            if name not in dumped:
                continue

            value = dumped[name]
            if runtime.schema_type in {"list", "table"} and isinstance(value, list):
                if target == "frontend":
                    dumped[name] = [
                        runtime.item_codec.to_frontend(item) for item in value
                    ]
                else:
                    dumped[name] = [
                        runtime.item_codec.to_storage(item) for item in value
                    ]
                continue

            if runtime.schema_type == "key_value" and isinstance(value, dict):
                if target == "frontend":
                    dumped[name] = {
                        str(key): runtime.item_codec.to_frontend(item)
                        for key, item in value.items()
                    }
                else:
                    dumped[name] = {
                        str(key): runtime.item_codec.to_storage(item)
                        for key, item in value.items()
                    }
                continue

            if target == "frontend":
                dumped[name] = runtime.codec.to_frontend(value)
            else:
                dumped[name] = runtime.codec.to_storage(value)

        return dumped

    @classmethod
    def from_frontend(cls: type[ModelT], raw: Dict[str, Any]) -> ModelT:
        """从前端载荷构建配置对象。"""
        converted = cls._convert_input_values(raw, source="frontend")
        model = cls.model_validate(converted)
        model = model.post_load()
        cls.validate_config(model)
        return cast(ModelT, model)

    @classmethod
    def from_storage(cls: type[ModelT], raw: Dict[str, Any]) -> ModelT:
        """从存储载荷构建配置对象。"""
        converted = cls._convert_input_values(raw, source="storage")
        model = cls.model_validate(converted)
        model = model.post_load()
        cls.validate_config(model)
        return cast(ModelT, model)

    def to_frontend(self) -> Dict[str, Any]:
        """导出前端可消费的配置值。"""
        model = self.pre_save()
        type(self).validate_config(model)
        return model._convert_output_values(target="frontend")

    def to_storage(self) -> Dict[str, Any]:
        """导出存储值。"""
        model = self.pre_save()
        type(self).validate_config(model)
        return model._convert_output_values(target="storage")


class SchemaModelAdapter:
    """将 PluginConfigModel 适配为现有 schema 管理器可识别对象。"""

    def __init__(self, model_cls: type[PluginConfigModel]) -> None:
        self._model_cls = model_cls

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return self._model_cls.to_schema_dict()


__all__ = [
    "Codec",
    "CodecRegistry",
    "GLOBAL_CODEC_REGISTRY",
    "IdentityCodec",
    "PathCodec",
    "TypePreset",
    "Desc",
    "preset",
    "describe",
    "PluginConfigModel",
    "SchemaModelAdapter",
]
