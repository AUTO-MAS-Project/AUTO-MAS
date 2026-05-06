#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import ast
import copy
import importlib
import importlib.util
import inspect
import json
import typing
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from types import NoneType, UnionType
from typing import Annotated, Any, Callable, Dict, ForwardRef, Literal, Mapping, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .pypi_site import iter_plugin_entry_points


def _make_literal(values: tuple[Any, ...]) -> Any:
    """运行时动态构造 Literal 类型。"""
    return Literal.__getitem__(values)  # type: ignore[attr-defined]


class PluginSchemaError(Exception):
    """插件 Schema 与配置处理错误。"""


class _FieldSpecModel(BaseModel):
    """字段定义模型，用于约束字段元信息结构。"""

    model_config = ConfigDict(extra="allow")

    type: Any
    required: bool = False
    nullable: bool = False
    description: str | None = None
    constraints: Dict[str, Any] = Field(default_factory=dict)
    size: Literal["small", "half", "medium", "large"] | None = None


@dataclass
class _CompiledField:
    """编译后的字段校验单元。"""

    name: str
    spec: _FieldSpecModel
    adapter: TypeAdapter[Any]
    required: bool
    has_default: bool
    default: Any


class PluginSchemaManager:
    """负责加载插件 Schema，并基于 Pydantic 执行配置校验。"""

    _PRIMITIVE_TYPE_ALIASES: Dict[str, Any] = {
        "any": Any,
        "Any": Any,
        "button": Any,
        "str": str,
        "string": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": float,
        "bool": bool,
        "boolean": bool,
        "dict": dict[str, Any],
        "list": list[Any],
        "key_value": dict[str, Any],
        "table": list[dict[str, Any]],
    }

    def _canonical_plugin_name(self, plugin_name: str) -> str:
        """将插件名规范化为基础名。

        当插件名包含来源后缀（例如 `test@local`）时，
        仅提取 `@` 前的基础插件名用于路径与入口点回退匹配。

        Args:
            plugin_name (str): 原始插件名。

        Returns:
            str: 规范化后的基础插件名。
        """
        normalized = str(plugin_name or "").strip()
        if not normalized:
            return ""
        return normalized.split("@", 1)[0].strip() or normalized

    def _resolve_local_plugin_py_path(self, plugin_name: str, plugin_path: Path) -> Path | None:
        """解析本地插件入口文件路径。

        兼容以下目录结构：
        1) `plugins/<name>/plugin.py`
        2) `plugins/<name>/src/<name>/plugin.py`
        3) `plugins/<name>/src/<base_name>/plugin.py`（`<base_name>` 来自 `@` 前缀）

        Args:
            plugin_name (str): 插件名（允许包含来源后缀）。
            plugin_path (Path): 本地插件根目录。

        Returns:
            Path | None: 匹配到的 plugin.py 路径；未匹配返回 None。
        """
        root_plugin = plugin_path / "plugin.py"
        if root_plugin.exists():
            return root_plugin

        candidates = [plugin_path.name, self._canonical_plugin_name(plugin_name)]
        seen: set[str] = set()
        for candidate in candidates:
            name = str(candidate or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            src_plugin = plugin_path / "src" / name / "plugin.py"
            if src_plugin.exists():
                return src_plugin

        return None

    def _resolve_local_schema_path(
        self,
        plugin_name: str,
        plugin_path: Path,
        file_name: str,
    ) -> Path | None:
        """解析本地插件 Schema 文件路径。

        兼容以下目录结构：
        1) `plugins/<name>/<file_name>`
        2) `plugins/<name>/src/<name>/<file_name>`
        3) `plugins/<name>/src/<base_name>/<file_name>`（`<base_name>` 来自 `@` 前缀）

        Args:
            plugin_name (str): 插件名（允许包含来源后缀）。
            plugin_path (Path): 本地插件根目录。
            file_name (str): 目标文件名（例如 schema.py / schema.json）。

        Returns:
            Path | None: 匹配到的文件路径；未匹配返回 None。
        """
        root_schema = plugin_path / file_name
        if root_schema.exists():
            return root_schema

        candidates = [plugin_path.name, self._canonical_plugin_name(plugin_name)]
        seen: set[str] = set()
        for candidate in candidates:
            name = str(candidate or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            src_schema = plugin_path / "src" / name / file_name
            if src_schema.exists():
                return src_schema

        return None

    def load_schema(self, plugin_name: str, plugin_path: Path | None) -> Dict[str, Dict[str, Any]]:
        """
        加载并校验插件 Schema 定义。

        Args:
            plugin_name (str): 插件名。
            plugin_path (Path | None): 插件本地目录路径；为 None 时仅尝试 Entry Point。

        Returns:
            Dict[str, Dict[str, Any]]: 通过校验后的 Schema 字段定义字典；不存在时返回空字典。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) schema.py 或 schema.json 加载失败；
                2) plugin.py 的 Config 声明加载失败；
                3) Entry Point 加载失败或模块导入失败；
                3) Schema 顶层不是对象；
                4) 字段定义格式错误（字段缺少 type、constraints 非对象等）。
        """
        schema: Dict[str, Dict[str, Any]] = {}
        canonical_plugin_name = self._canonical_plugin_name(plugin_name)
        if plugin_path is not None:
            schema_py = self._resolve_local_schema_path(
                plugin_name,
                plugin_path,
                "schema.py",
            )
            schema_json = self._resolve_local_schema_path(
                plugin_name,
                plugin_path,
                "schema.json",
            )

            if schema_py is not None and schema_py.exists():
                schema = self._load_schema_from_py(plugin_name, schema_py)
            elif schema_json is not None and schema_json.exists():
                schema = self._load_schema_from_json(plugin_name, schema_json)

            if not schema:
                plugin_py = self._resolve_local_plugin_py_path(plugin_name, plugin_path)
                if plugin_py is not None and plugin_py.exists():
                    schema = self._load_schema_from_plugin_py(plugin_name, plugin_py)

        if not schema:
            schema = self._load_schema_from_entry_point(plugin_name)

        if not schema and canonical_plugin_name != plugin_name:
            schema = self._load_schema_from_entry_point(canonical_plugin_name)

        if not schema:
            return {}

        self._validate_schema_definition(plugin_name, schema)
        return schema

    def _extract_schema_from_module(self, plugin_name: str, module: Any) -> Dict[str, Dict[str, Any]]:
        """
        从模块对象中提取 schema 定义。

        Args:
            plugin_name (str): 插件名。
            module (Any): 待提取 schema 的模块对象。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 schema。

        Raises:
            PluginSchemaError: 模块中的 schema 不是对象结构时抛出。
        """
        if module is None:
            return {}

        if hasattr(module, "Config"):
            schema = self._build_schema_from_config_declaration(
                plugin_name,
                getattr(module, "Config"),
            )
        elif hasattr(module, "schema"):
            schema = self._normalize_schema_object(getattr(module, "schema"))
        elif callable(getattr(module, "get_schema", None)):
            schema = self._normalize_schema_object(module.get_schema())
        else:
            return {}

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")

        return self._normalize_schema_fields(plugin_name, schema)

    def _import_module_from_file(self, module_name: str, file_path: Path) -> Any:
        """
        从文件路径导入 Python 模块对象。

        Args:
            module_name (str): 模块名。
            file_path (Path): 模块文件路径。

        Returns:
            Any: 导入后的模块对象。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 无法创建模块规格；
                2) 模块执行失败。
        """
        import sys

        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise PluginSchemaError(f"无法加载 Python 模块: {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(module_name, None)
            raise PluginSchemaError(
                f"执行 Python 模块失败: {file_path.name}, error={type(e).__name__}: {e}"
            ) from e
        finally:
            sys.modules.pop(module_name, None)
        return module

    def _load_schema_from_plugin_py(
        self,
        plugin_name: str,
        plugin_py_path: Path,
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 plugin.py 中读取 `Config`/`schema`/`get_schema` 声明。

        Args:
            plugin_name (str): 插件名。
            plugin_py_path (Path): plugin.py 文件路径。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 schema；不存在时返回空字典。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) plugin.py 模块导入失败；
                2) `Config`/`schema`/`get_schema` 声明结构非法。
        """
        module_name = f"mas_plugin_module_{plugin_name}"
        module = self._import_module_from_file(module_name, plugin_py_path)
        return self._extract_schema_from_module(plugin_name, module)

    def _load_schema_from_entry_point(self, plugin_name: str) -> Dict[str, Dict[str, Any]]:
        """
        从 PyPI Entry Point 对应模块加载 schema。

        Args:
            plugin_name (str): 插件名。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 schema；不存在时返回空字典。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) Entry Point 加载失败；
                2) callable 所在模块导入失败；
                3) schema 结构非法。
        """
        for entry_point in iter_plugin_entry_points():
            if str(getattr(entry_point, "name", "")).strip() != plugin_name:
                continue

            try:
                loaded = entry_point.load()
            except Exception as e:
                raise PluginSchemaError(
                    f"加载插件入口失败: {plugin_name}, error={type(e).__name__}: {e}"
                ) from e

            if hasattr(loaded, "__dict__") and not callable(loaded):
                schema = self._extract_schema_from_module(plugin_name, loaded)
                if schema:
                    return schema

            if callable(loaded):
                module_name = getattr(loaded, "__module__", "")
                if module_name:
                    try:
                        module = importlib.import_module(module_name)
                    except Exception as e:
                        raise PluginSchemaError(
                            f"导入插件模块失败: {plugin_name}, module={module_name}, error={type(e).__name__}: {e}"
                        ) from e
                    schema = self._extract_schema_from_module(plugin_name, module)
                    if schema:
                        return schema

                    package_name = module_name.rsplit(".", 1)[0] if "." in module_name else module_name
                    schema_module_name = f"{package_name}.schema"
                    if schema_module_name != module_name:
                        try:
                            schema_module = importlib.import_module(schema_module_name)
                            schema = self._extract_schema_from_module(plugin_name, schema_module)
                            if schema:
                                return schema
                        except ImportError:
                            pass

        return {}

    def _load_schema_from_py(
        self,
        plugin_name: str,
        schema_path: Path,
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 schema.py 文件加载 schema 定义。

        Args:
            plugin_name (str): 插件名。
            schema_path (Path): schema.py 文件路径。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 schema。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) schema.py 模块无法加载；
                2) 缺少 `Config`/`schema`/`get_schema` 声明；
                3) schema 结构非法。
        """
        module_name = f"mas_plugin_schema_{plugin_name}"
        module = self._import_module_from_file(module_name, schema_path)

        if hasattr(module, "Config"):
            schema = self._build_schema_from_config_declaration(
                plugin_name,
                getattr(module, "Config"),
            )
        elif hasattr(module, "schema"):
            schema = module.schema
        elif callable(getattr(module, "get_schema", None)):
            schema = module.get_schema()
        else:
            raise PluginSchemaError(
                f"插件 Schema 缺少 Config/schema/get_schema 声明: {plugin_name}"
            )

        schema = self._normalize_schema_object(schema)

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")

        return self._normalize_schema_fields(plugin_name, schema)

    def _build_schema_from_config_declaration(
        self,
        plugin_name: str,
        declaration: Any,
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 `Config` 声明构建 schema 字典。

        Args:
            plugin_name (str): 插件名。
            declaration (Any): `Config` 声明对象，支持 BaseModel 子类、BaseModel 实例或返回上述对象的可调用对象。

        Returns:
            Dict[str, Dict[str, Any]]: 从 BaseModel 字段推导出的 schema。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) `Config` 是可调用对象但执行失败；
                2) `Config` 返回值既不是 BaseModel 子类/实例，也不是字典；
                3) BaseModel 字段默认值工厂执行失败。
        """
        target = declaration
        if callable(declaration) and not (inspect.isclass(declaration) and issubclass(declaration, BaseModel)):
            try:
                target = declaration()
            except Exception as e:
                raise PluginSchemaError(
                    f"执行 Config 声明失败: {plugin_name}, error={type(e).__name__}: {e}"
                ) from e

        if inspect.isclass(target) and issubclass(target, BaseModel):
            return self._build_schema_from_model(plugin_name, target)

        if isinstance(target, BaseModel):
            return self._build_schema_from_model(plugin_name, type(target))

        normalized = self._normalize_schema_object(target)
        if isinstance(normalized, dict):
            return self._normalize_schema_fields(plugin_name, normalized)

        raise PluginSchemaError(
            f"Config 声明不支持的返回类型: {plugin_name}, type={type(target).__name__}"
        )

    def _build_schema_from_model(
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
        result: Dict[str, Dict[str, Any]] = {}
        for field_name, field_info in model_cls.model_fields.items():
            annotation = self._resolve_forward_ref(field_info.annotation)
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
                        factory = cast(Callable[[], Any], field_info.default_factory)
                        field_schema["default"] = factory()
                    except Exception as e:
                        raise PluginSchemaError(
                            f"Config 字段 default_factory 执行失败: {plugin_name}.{field_name}, "
                            f"error={type(e).__name__}: {e}"
                        ) from e
                else:
                    field_schema["default"] = copy.deepcopy(field_info.default)

            extra = field_info.json_schema_extra
            if extra is not None:
                if not isinstance(extra, dict):
                    raise PluginSchemaError(
                        f"Config 字段 json_schema_extra 必须是对象: {plugin_name}.{field_name}"
                    )
                field_schema.update(copy.deepcopy(extra))

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

    def _normalize_schema_object(self, schema: Any) -> Any:
        """
        将 DSL 或 Pydantic 对象归一化为字典结构。

        Args:
            schema (Any): 原始 schema 对象。

        Returns:
            Any: 归一化后的对象。
        """
        if hasattr(schema, "to_dict") and callable(schema.to_dict):
            return schema.to_dict()
        if hasattr(schema, "model_dump") and callable(schema.model_dump):
            return schema.model_dump()
        return schema

    def _normalize_schema_fields(
        self,
        plugin_name: str,
        schema: Mapping[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """
        归一化字段定义，确保字段值均为标准字典。

        Args:
            plugin_name (str): 插件名。
            schema (Mapping[str, Any]): 原始字段映射。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的字段映射。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 字段名不是字符串；
                2) 字段定义既不是字典，也没有 `to_dict/model_dump` 方法；
                3) 字段定义归一化后不是对象。
        """
        normalized: Dict[str, Dict[str, Any]] = {}
        for field_name, field_schema in schema.items():
            if not isinstance(field_name, str):
                raise PluginSchemaError(
                    f"Schema 字段名必须是字符串: {plugin_name}.{field_name}"
                )

            value = field_schema
            if hasattr(value, "to_dict") and callable(value.to_dict):
                value = value.to_dict()
            elif hasattr(value, "model_dump") and callable(value.model_dump):
                value = value.model_dump()

            if not isinstance(value, dict):
                raise PluginSchemaError(
                    f"Schema 字段定义必须是对象: {plugin_name}.{field_name}"
                )
            normalized[field_name] = value
        return normalized

    def _load_schema_from_json(
        self,
        plugin_name: str,
        schema_path: Path,
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 schema.json 文件加载 schema 定义。

        Args:
            plugin_name (str): 插件名。
            schema_path (Path): schema.json 文件路径。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 schema。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 读取 JSON 文件失败；
                2) 顶层不是对象；
                3) 字段结构非法。
        """
        try:
            with schema_path.open("r", encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            raise PluginSchemaError(f"读取 Schema 失败: {plugin_name}, error={e}") from e

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")

        return self._normalize_schema_fields(plugin_name, schema)

    def _validate_schema_definition(
        self,
        plugin_name: str,
        schema: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        校验 schema 定义合法性，并确保每个字段可被编译为 Pydantic 校验器。

        Args:
            plugin_name (str): 插件名。
            schema (Dict[str, Dict[str, Any]]): schema 字段定义。

        Returns:
            None: 无返回值。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 字段定义缺少 type；
                2) required/nullable/description/constraints 类型非法；
                3) type 表达式无法解析为有效 Python 注解；
                4) constraints 无法构建 Pydantic Field。
        """
        self._compile_schema(plugin_name, schema)

    def apply_defaults_and_validate(
        self,
        plugin_name: str,
        schema: Dict[str, Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        对配置应用默认值并按 Schema 进行类型校验。

        Args:
            plugin_name (str): 插件名。
            schema (Dict[str, Dict[str, Any]]): 插件 Schema 定义。
            config (Dict[str, Any]): 原始配置对象。

        Returns:
            Dict[str, Any]: 合并默认值并通过校验后的配置对象。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) config 不是对象；
                2) 缺少 required=true 的必填字段且无默认值；
                3) 任一字段值不满足声明类型或约束；
                4) 字段值为 None 且字段未声明 nullable。
        """
        if not isinstance(config, dict):
            raise PluginSchemaError(f"插件配置必须是对象: {plugin_name}")

        compiled = self._compile_schema(plugin_name, schema)
        merged = copy.deepcopy(config)

        for item in compiled:
            if item.name not in merged:
                if item.has_default:
                    merged[item.name] = copy.deepcopy(item.default)
                elif item.required:
                    raise PluginSchemaError(f"缺少必填配置项: {plugin_name}.{item.name}")
                else:
                    continue

            merged[item.name] = self._validate_field_value(
                plugin_name=plugin_name,
                field_name=item.name,
                value=merged[item.name],
                compiled=item,
            )

        return merged

    def _compile_schema(
        self,
        plugin_name: str,
        schema: Dict[str, Dict[str, Any]],
    ) -> list[_CompiledField]:
        """
        将 schema 字段定义编译为可执行校验器。

        Args:
            plugin_name (str): 插件名。
            schema (Dict[str, Dict[str, Any]]): 插件 schema。

        Returns:
            list[_CompiledField]: 编译后的字段校验单元列表。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 字段元信息不满足模型约束；
                2) type 字段缺失或无法解析；
                3) constraints 非法导致无法构建 Field。
        """
        compiled: list[_CompiledField] = []
        for field_name, raw_field in schema.items():
            if "type" not in raw_field:
                raise PluginSchemaError(f"Schema 字段缺少 type: {plugin_name}.{field_name}")

            if self._is_virtual_schema_field(raw_field):
                continue

            try:
                spec = _FieldSpecModel.model_validate(raw_field)
            except ValidationError as e:
                raise PluginSchemaError(
                    self._format_schema_error(plugin_name, field_name, e)
                ) from e

            annotation = self._parse_type_annotation(spec.type)
            enum_values = raw_field.get("enum")
            if enum_values is not None:
                annotation = self._apply_enum_annotation(
                    plugin_name,
                    field_name,
                    annotation,
                    enum_values,
                )
            if spec.nullable:
                annotation = annotation | None

            constraints = spec.constraints or {}
            if constraints:
                try:
                    annotation = Annotated[annotation, Field(**constraints)]
                except Exception as e:
                    raise PluginSchemaError(
                        f"Schema 约束非法: {plugin_name}.{field_name}, error={type(e).__name__}: {e}"
                    ) from e

            try:
                adapter = TypeAdapter(annotation)
            except Exception as e:
                raise PluginSchemaError(
                    f"Schema 类型无法编译: {plugin_name}.{field_name}, type={spec.type}, error={type(e).__name__}: {e}"
                ) from e

            has_default = "default" in raw_field
            default_value = raw_field.get("default")

            compiled.append(
                _CompiledField(
                    name=field_name,
                    spec=spec,
                    adapter=adapter,
                    required=bool(spec.required),
                    has_default=has_default,
                    default=default_value,
                )
            )

            raw_field["type"] = self._type_to_expr(spec.type)
        return compiled

    @staticmethod
    def _is_virtual_schema_field(raw_field: Dict[str, Any]) -> bool:
        """判断字段是否只用于前端渲染，不参与插件配置校验与落库。"""
        field_type = str(raw_field.get("type") or "").strip().lower()
        if field_type in {"button", "action"}:
            return True
        return raw_field.get("configurable") is False

    def _validate_field_value(
        self,
        plugin_name: str,
        field_name: str,
        value: Any,
        compiled: _CompiledField,
    ) -> Any:
        """
        使用编译后的校验器验证单个字段值。

        Args:
            plugin_name (str): 插件名。
            field_name (str): 字段名。
            value (Any): 待校验值。
            compiled (_CompiledField): 编译后的字段校验信息。

        Returns:
            Any: 通过校验并经 Pydantic 规范化后的值。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 值不满足字段类型；
                2) 值不满足字段约束；
                3) 字段为非 nullable 但值为 None。
        """
        if value is None and not compiled.spec.nullable:
            raise PluginSchemaError(f"配置项不允许为 null: {plugin_name}.{field_name}")

        try:
            return compiled.adapter.validate_python(value, strict=True)
        except ValidationError as e:
            raise PluginSchemaError(
                self._format_value_error(plugin_name, field_name, value, e)
            ) from e

    def _parse_type_annotation(self, raw_type: Any) -> Any:
        """
        将 schema 中的类型描述解析为 Python 注解对象。

        Args:
            raw_type (Any): 原始类型描述，支持 Python 类型对象或字符串表达式。

        Returns:
            Any: 可供 Pydantic TypeAdapter 使用的类型注解。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 类型表达式为空字符串；
                2) 类型表达式语法非法；
                3) 类型别名不受支持。
        """
        if raw_type is Any:
            return Any

        if isinstance(raw_type, type):
            return raw_type

        origin = get_origin(raw_type)
        if origin is not None:
            return raw_type

        if not isinstance(raw_type, str):
            raise PluginSchemaError(f"Schema type 不支持: {type(raw_type).__name__}")

        expr = raw_type.strip()
        if not expr:
            raise PluginSchemaError("Schema type 不能为空字符串")

        return self._parse_type_expr(expr)

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

    def _apply_enum_annotation(
        self,
        plugin_name: str,
        field_name: str,
        annotation: Any,
        enum_values: Any,
    ) -> Any:
        if not isinstance(enum_values, list) or not enum_values:
            raise PluginSchemaError(f"Schema enum 必须是非空数组: {plugin_name}.{field_name}")

        origin = get_origin(annotation)
        literal_annotation = _make_literal(tuple(enum_values))

        if origin is list:
            return list[literal_annotation]

        if origin is None and annotation is list:
            return list[literal_annotation]

        return literal_annotation

    def _parse_type_expr(self, expr: str) -> Any:
        """
        解析字符串类型表达式。

        Args:
            expr (str): 类型表达式，例如 `int`、`list[str]`、`dict[str, int]`。

        Returns:
            Any: Python 类型注解。

        Raises:
            PluginSchemaError: 在以下场景抛出：
                1) 泛型参数缺失或格式错误；
                2) 未知类型别名；
                3) 联合类型解析失败。
        """
        normalized = expr.strip()
        if (
            len(normalized) >= 2
            and normalized[0] == normalized[-1]
            and normalized[0] in {'"', "'"}
        ):
            normalized = normalized[1:-1].strip()

        if normalized in self._PRIMITIVE_TYPE_ALIASES:
            return self._PRIMITIVE_TYPE_ALIASES[normalized]

        lowered = normalized.lower()
        if lowered in self._PRIMITIVE_TYPE_ALIASES:
            return self._PRIMITIVE_TYPE_ALIASES[lowered]

        parts = self._split_top_level(normalized, "|")
        if len(parts) > 1:
            annotation = self._parse_type_expr(parts[0])
            for part in parts[1:]:
                annotation = annotation | self._parse_type_expr(part)
            return annotation

        if normalized.startswith("list[") and normalized.endswith("]"):
            inner = normalized[5:-1].strip()
            if not inner:
                raise PluginSchemaError(f"非法 list 类型表达式: {expr}")
            return list[self._parse_type_expr(inner)]

        if normalized.startswith("dict[") and normalized.endswith("]"):
            inner = normalized[5:-1].strip()
            items = self._split_top_level(inner, ",")
            if len(items) != 2:
                raise PluginSchemaError(f"非法 dict 类型表达式: {expr}")
            key_type = self._parse_type_expr(items[0].strip())
            value_type = self._parse_type_expr(items[1].strip())
            return dict[key_type, value_type]

        if normalized.startswith("tuple[") and normalized.endswith("]"):
            inner = normalized[6:-1].strip()
            if not inner:
                raise PluginSchemaError(f"非法 tuple 类型表达式: {expr}")
            tuple_args = [self._parse_type_expr(item.strip()) for item in self._split_top_level(inner, ",")]
            return tuple[tuple(tuple_args)]

        if normalized.startswith("Optional[") and normalized.endswith("]"):
            inner = normalized[9:-1].strip()
            if not inner:
                raise PluginSchemaError(f"非法 Optional 类型表达式: {expr}")
            return self._parse_type_expr(inner) | None

        if normalized.startswith("Literal[") and normalized.endswith("]"):
            inner = normalized[8:-1].strip()
            if not inner:
                raise PluginSchemaError(f"非法 Literal 类型表达式: {expr}")
            values = []
            for item in self._split_top_level(inner, ","):
                try:
                    values.append(ast.literal_eval(item))
                except Exception as e:
                    raise PluginSchemaError(
                        f"非法 Literal 值: {expr}, value={item}, error={type(e).__name__}: {e}"
                    ) from e
            return _make_literal(tuple(values))

        raise PluginSchemaError(f"不支持的 Schema type 表达式: {expr}")

    def _split_top_level(self, expr: str, separator: str) -> list[str]:
        """
        按顶层分隔符切分表达式，忽略泛型中括号内部内容。

        Args:
            expr (str): 待切分表达式。
            separator (str): 分隔符，仅支持单字符。

        Returns:
            list[str]: 切分结果。
        """
        result: list[str] = []
        depth = 0
        start = 0
        for index, ch in enumerate(expr):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth = max(0, depth - 1)
            elif ch == separator and depth == 0:
                result.append(expr[start:index])
                start = index + 1
        result.append(expr[start:])
        return [item.strip() for item in result if item.strip()]

    def _format_schema_error(self, plugin_name: str, field_name: str, error: ValidationError) -> str:
        """
        格式化 schema 字段元信息错误。

        Args:
            plugin_name (str): 插件名。
            field_name (str): 字段名。
            error (ValidationError): Pydantic 校验错误对象。

        Returns:
            str: 中文错误消息。
        """
        first = error.errors()[0] if error.errors() else {"msg": str(error), "loc": ()}
        loc = ".".join(str(item) for item in first.get("loc", ()))
        suffix = f".{loc}" if loc else ""
        return f"Schema 字段定义非法: {plugin_name}.{field_name}{suffix}, {first.get('msg', '未知错误')}"

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

    @staticmethod
    def _resolve_forward_ref(annotation: Any) -> Any:
        """将 ForwardRef 求值为真实类型对象。"""
        if not isinstance(annotation, ForwardRef):
            return annotation
        globalns: dict[str, Any] = vars(typing)
        globalns.update({"NoneType": NoneType})
        try:
            return typing._eval_type(annotation, globalns, None)  # type: ignore[attr-defined]
        except Exception:
            return annotation

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
