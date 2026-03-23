#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


class SchemaField:
    """Schema 字段构建器，支持链式定义。"""

    def __init__(self, field_type: str) -> None:
        self._data: Dict[str, Any] = {"type": field_type}

    def default(self, value: Any) -> "SchemaField":
        """
        设置字段默认值。

        Args:
            value (Any): 字段默认值。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data["default"] = deepcopy(value)
        return self

    def required(self, value: bool = True) -> "SchemaField":
        """
        设置字段是否必填。

        Args:
            value (bool): 是否必填，默认为 True。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data["required"] = value
        return self

    def description(self, text: str) -> "SchemaField":
        """
        设置字段说明文本。

        Args:
            text (str): 字段说明内容。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data["description"] = text
        return self

    def nullable(self, value: bool = True) -> "SchemaField":
        """
        设置字段是否允许为 null。

        Args:
            value (bool): 是否允许空值，默认为 True。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data["nullable"] = value
        return self

    def item_type(self, value: str) -> "SchemaField":
        """
        设置列表字段的元素类型。

        Args:
            value (str): 元素类型标识，例如 string/number/boolean/any。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data["item_type"] = value
        return self

    def option(self, key: str, value: Any) -> "SchemaField":
        """
        写入自定义字段选项。

        Args:
            key (str): 选项键。
            value (Any): 选项值。

        Returns:
            SchemaField: 当前字段构建器实例，支持链式调用。
        """
        self._data[key] = value
        return self

    def to_dict(self) -> Dict[str, Any]:
        """
        导出字段定义字典。

        Returns:
            Dict[str, Any]: 当前字段定义的深拷贝结果。
        """
        return deepcopy(self._data)


class Schema:
    """Schema DSL 命名空间。"""

    @staticmethod
    def boolean() -> SchemaField:
        """
        创建布尔类型字段定义。

        Returns:
            SchemaField: 类型为 boolean 的字段构建器。
        """
        return SchemaField("boolean")

    @staticmethod
    def string() -> SchemaField:
        """
        创建字符串类型字段定义。

        Returns:
            SchemaField: 类型为 string 的字段构建器。
        """
        return SchemaField("string")

    @staticmethod
    def password() -> SchemaField:
        """
        创建密码格式的字符串字段定义。

        Returns:
            SchemaField: 带有 password 格式选项的字符串字段构建器。
        """
        return SchemaField("string").option("format", "password")

    @staticmethod
    def number() -> SchemaField:
        """
        创建数值类型字段定义。

        Returns:
            SchemaField: 类型为 number 的字段构建器。
        """
        return SchemaField("number")

    @staticmethod
    def list(item_type: str = "any") -> SchemaField:
        """
        创建列表类型字段定义。

        Args:
            item_type (str): 列表元素类型，默认为 any。

        Returns:
            SchemaField: 类型为 list 的字段构建器。
        """
        return SchemaField("list").item_type(item_type)

    @staticmethod
    def key_value() -> SchemaField:
        """
        创建键值对象类型字段定义。

        Returns:
            SchemaField: 类型为 key_value 的字段构建器。
        """
        return SchemaField("key_value")

    @staticmethod
    def table() -> SchemaField:
        """
        创建表格类型字段定义。

        Returns:
            SchemaField: 类型为 table 的字段构建器。
        """
        return SchemaField("table")

    @staticmethod
    def object(fields: Dict[str, SchemaField | Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        将字段构建器映射转换为标准 Schema 字典。

        Args:
            fields (Dict[str, SchemaField | Dict[str, Any]]): 字段定义映射。

        Returns:
            Dict[str, Dict[str, Any]]: 归一化后的 Schema 字段字典。

        Raises:
            TypeError: 存在不支持的字段定义类型时抛出。
        """
        result: Dict[str, Dict[str, Any]] = {}
        for name, value in fields.items():
            if isinstance(value, SchemaField):
                result[name] = value.to_dict()
            elif isinstance(value, dict):
                result[name] = deepcopy(value)
            else:
                raise TypeError(f"字段 {name} 的定义类型不支持: {type(value).__name__}")
        return result
