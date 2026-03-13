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
        self._data["default"] = deepcopy(value)
        return self

    def required(self, value: bool = True) -> "SchemaField":
        self._data["required"] = value
        return self

    def description(self, text: str) -> "SchemaField":
        self._data["description"] = text
        return self

    def nullable(self, value: bool = True) -> "SchemaField":
        self._data["nullable"] = value
        return self

    def item_type(self, value: str) -> "SchemaField":
        self._data["item_type"] = value
        return self

    def option(self, key: str, value: Any) -> "SchemaField":
        self._data[key] = value
        return self

    def to_dict(self) -> Dict[str, Any]:
        return deepcopy(self._data)


class Schema:
    """Schema DSL 命名空间。"""

    @staticmethod
    def boolean() -> SchemaField:
        return SchemaField("boolean")

    @staticmethod
    def string() -> SchemaField:
        return SchemaField("string")

    @staticmethod
    def password() -> SchemaField:
        return SchemaField("string").option("format", "password")

    @staticmethod
    def number() -> SchemaField:
        return SchemaField("number")

    @staticmethod
    def list(item_type: str = "any") -> SchemaField:
        return SchemaField("list").item_type(item_type)

    @staticmethod
    def key_value() -> SchemaField:
        return SchemaField("key_value")

    @staticmethod
    def table() -> SchemaField:
        return SchemaField("table")

    @staticmethod
    def object(fields: Dict[str, SchemaField | Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for name, value in fields.items():
            if isinstance(value, SchemaField):
                result[name] = value.to_dict()
            elif isinstance(value, dict):
                result[name] = deepcopy(value)
            else:
                raise TypeError(f"字段 {name} 的定义类型不支持: {type(value).__name__}")
        return result
