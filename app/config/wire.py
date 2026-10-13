"""Wire 文档形状：JSON / TOML / ``model_dump`` 同一逻辑结构。

- Collection Wire：``{ "order": [{uid, type}, …], "data": { "<uuid>": <EntryWire>, … } }``
- Entry Wire：各 Group 字段名顶层嵌套 dict

落盘 IO 走 ``app.utils.io``；本模块只保留类型与 TOML 可写归一。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

type WireScalar = str | int | float | bool
"""Wire 叶子标量。"""

type WireValue = WireScalar | None | dict[str, Any] | list[Any]
"""Wire 单值；嵌套 dict/list 用 ``Any``，便于 ``to_dict`` 多层下标。"""

type WireDict = dict[str, Any]
"""Wire 顶层或 Entry 级 dict。"""


@dataclass
class ExportContext:
    """``_export_wire`` 导出上下文：控制解密与是否携带响应式字段。"""

    if_decrypt: bool = False
    """False → 密文；True → 明文。"""

    include_reactive: bool = False
    """是否携带响应式字段（virtual / trigger）。"""


class CollectionOrderItem(BaseModel):
    """Collection 索引项：``{ uid, type }``。"""

    uid: UUID
    type: str  # Entry 子类名，如 "ExampleQueue"


def to_tomlable(value: object) -> object:
    """将 Wire 值归一为 TOML 可写形态（去 None、UUID/Path → str）。"""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if v is None:
                continue
            key = str(k) if isinstance(k, UUID) else k
            out[str(key)] = to_tomlable(v)
        return out
    if isinstance(value, list):
        return [to_tomlable(v) for v in value if v is not None]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value
