#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import copy
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

from .pypi_site import iter_plugin_entry_points


class PluginSchemaError(Exception):
    """插件 Schema 与配置处理错误。"""


class PluginSchemaManager:
    """负责加载插件 Schema，并执行类型校验。"""

    SUPPORTED_TYPES = {"boolean", "string", "number", "list", "key_value", "table"}
    LIST_ITEM_TYPES = {"string", "number", "boolean", "any"}

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
                2) Entry Point 加载失败或模块导入失败；
                3) Schema 顶层不是对象；
                4) 字段定义格式错误（类型不支持、required/description/item_type 不合法等）。
        """
        schema: Dict[str, Dict[str, Any]] = {}
        if plugin_path is not None:
            schema_py = plugin_path / "schema.py"
            schema_json = plugin_path / "schema.json"

            if schema_py.exists():
                schema = self._load_schema_from_py(plugin_name, schema_py)
            elif schema_json.exists():
                schema = self._load_schema_from_json(plugin_name, schema_json)

        if not schema:
            schema = self._load_schema_from_entry_point(plugin_name)

        if not schema:
            return {}

        self._validate_schema_definition(plugin_name, schema)
        return schema

    def _extract_schema_from_module(self, plugin_name: str, module: Any) -> Dict[str, Dict[str, Any]]:
        """从模块对象中提取 schema 定义。"""
        if module is None:
            return {}

        if hasattr(module, "schema"):
            schema = self._normalize_schema_object(getattr(module, "schema"))
        elif callable(getattr(module, "get_schema", None)):
            schema = self._normalize_schema_object(module.get_schema())
        else:
            return {}

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")
        return schema

    def _load_schema_from_entry_point(self, plugin_name: str) -> Dict[str, Dict[str, Any]]:
        """从 PyPI Entry Point 对应模块加载 schema。"""
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

        return {}

    def _load_schema_from_py(
        self,
        plugin_name: str,
        schema_path: Path,
    ) -> Dict[str, Dict[str, Any]]:
        module_name = f"mas_plugin_schema_{plugin_name}"
        spec = importlib.util.spec_from_file_location(module_name, str(schema_path))
        if spec is None or spec.loader is None:
            raise PluginSchemaError(f"无法加载 Schema 模块: {plugin_name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "schema"):
            schema = module.schema
        elif callable(getattr(module, "get_schema", None)):
            schema = module.get_schema()
        else:
            raise PluginSchemaError(
                f"插件 Schema 缺少 schema 变量或 get_schema() 函数: {plugin_name}"
            )

        schema = self._normalize_schema_object(schema)

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")
        return schema

    def _normalize_schema_object(self, schema: Any) -> Any:
        """将 DSL 对象归一化为字典结构。"""
        if hasattr(schema, "to_dict") and callable(schema.to_dict):
            return schema.to_dict()
        return schema

    def _load_schema_from_json(
        self,
        plugin_name: str,
        schema_path: Path,
    ) -> Dict[str, Dict[str, Any]]:
        try:
            with schema_path.open("r", encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            raise PluginSchemaError(f"读取 Schema 失败: {plugin_name}, error={e}") from e

        if not isinstance(schema, dict):
            raise PluginSchemaError(f"插件 Schema 必须是对象: {plugin_name}")
        return schema

    def _validate_schema_definition(
        self,
        plugin_name: str,
        schema: Dict[str, Dict[str, Any]],
    ) -> None:
        for field_name, field_schema in schema.items():
            if not isinstance(field_schema, dict):
                raise PluginSchemaError(
                    f"Schema 字段定义必须是对象: {plugin_name}.{field_name}"
                )

            field_type = field_schema.get("type")
            if not isinstance(field_type, str) or field_type not in self.SUPPORTED_TYPES:
                raise PluginSchemaError(
                    f"Schema 字段类型不支持: {plugin_name}.{field_name}.type={field_type}"
                )

            if "required" in field_schema and not isinstance(
                field_schema["required"], bool
            ):
                raise PluginSchemaError(
                    f"Schema 字段 required 必须是布尔值: {plugin_name}.{field_name}"
                )

            if "description" in field_schema and not isinstance(
                field_schema["description"], str
            ):
                raise PluginSchemaError(
                    f"Schema 字段 description 必须是字符串: {plugin_name}.{field_name}"
                )

            if field_type == "list" and "item_type" in field_schema:
                item_type = field_schema["item_type"]
                if item_type not in self.LIST_ITEM_TYPES:
                    raise PluginSchemaError(
                        f"Schema list.item_type 不支持: {plugin_name}.{field_name}"
                    )

            if "default" in field_schema:
                self._validate_field_value(
                    plugin_name,
                    field_name,
                    field_schema["default"],
                    field_schema,
                )

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
                3) 任一字段值不满足声明类型（含 list/item_type、key_value、table 约束）；
                4) 字段值为 None 且字段未声明 nullable。
        """
        if not isinstance(config, dict):
            raise PluginSchemaError(f"插件配置必须是对象: {plugin_name}")

        merged = copy.deepcopy(config)

        for field_name, field_schema in schema.items():
            required = bool(field_schema.get("required", False))

            if field_name not in merged:
                if "default" in field_schema:
                    merged[field_name] = copy.deepcopy(field_schema["default"])
                elif required:
                    raise PluginSchemaError(
                        f"缺少必填配置项: {plugin_name}.{field_name}"
                    )
                else:
                    continue

            self._validate_field_value(
                plugin_name,
                field_name,
                merged[field_name],
                field_schema,
            )

        return merged

    def _validate_field_value(
        self,
        plugin_name: str,
        field_name: str,
        value: Any,
        field_schema: Dict[str, Any],
    ) -> None:
        field_type = field_schema["type"]

        if value is None:
            if field_schema.get("nullable", False):
                return
            raise PluginSchemaError(
                f"配置项不允许为 null: {plugin_name}.{field_name}"
            )

        if field_type == "boolean":
            if not isinstance(value, bool):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 boolean: {plugin_name}.{field_name}"
                )
            return

        if field_type == "string":
            if not isinstance(value, str):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 string: {plugin_name}.{field_name}"
                )
            return

        if field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 number: {plugin_name}.{field_name}"
                )
            return

        if field_type == "list":
            if not isinstance(value, list):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 list: {plugin_name}.{field_name}"
                )
            self._validate_list_item_type(plugin_name, field_name, value, field_schema)
            return

        if field_type == "key_value":
            if not isinstance(value, dict):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 key_value 对象: {plugin_name}.{field_name}"
                )
            for key in value.keys():
                if not isinstance(key, str):
                    raise PluginSchemaError(
                        f"key_value 的键必须是字符串: {plugin_name}.{field_name}"
                    )
            return

        if field_type == "table":
            if not isinstance(value, list):
                raise PluginSchemaError(
                    f"配置项类型错误，应为 table 列表: {plugin_name}.{field_name}"
                )
            for row in value:
                if not isinstance(row, (dict, list)):
                    raise PluginSchemaError(
                        f"table 行必须是对象或数组: {plugin_name}.{field_name}"
                    )
            return

    def _validate_list_item_type(
        self,
        plugin_name: str,
        field_name: str,
        value: list,
        field_schema: Dict[str, Any],
    ) -> None:
        item_type = field_schema.get("item_type", "any")
        if item_type == "any":
            return

        for item in value:
            if item_type == "string" and not isinstance(item, str):
                raise PluginSchemaError(
                    f"list 元素类型错误，应为 string: {plugin_name}.{field_name}"
                )
            if item_type == "boolean" and not isinstance(item, bool):
                raise PluginSchemaError(
                    f"list 元素类型错误，应为 boolean: {plugin_name}.{field_name}"
                )
            if item_type == "number" and (
                isinstance(item, bool) or not isinstance(item, (int, float))
            ):
                raise PluginSchemaError(
                    f"list 元素类型错误，应为 number: {plugin_name}.{field_name}"
                )
