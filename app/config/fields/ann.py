"""注解剥离：循环解开 ``Annotated`` / PEP695 TypeAlias，得到核心类型与 metadata。"""

from __future__ import annotations

from types import UnionType
from typing import Annotated, TypeVar, Union, get_args, get_origin


def unwrap_ann(ann: object) -> tuple[object, tuple[object, ...]]:
    """循环剥 ``Annotated`` / TypeAlias，返回 ``(核心类型, 累积 metadata)``。

    - 外层 → 内层 metadata 依次累积（含多层 ``Annotated``）。
    - **不**剥 ``T | None`` / Union；需要时再调 ``strip_optional``。
    """
    meta: list[object] = []
    cur: object | None = ann
    while cur is not None:
        origin = get_origin(cur)
        if origin is Annotated:
            args = get_args(cur)
            if not args:
                break
            meta.extend(args[1:])
            cur = args[0]
            continue
        # FilePath 等直接取别名定义；Virtual[str] 等先取参数化别名的 origin。
        alias = origin or cur
        value = getattr(alias, "__value__", None)
        if value is None or value is cur:
            break
        bindings: dict[object, object] = dict(
            zip(getattr(alias, "__type_params__", ()), get_args(cur))
        )
        if isinstance(value, TypeVar):
            value = bindings.get(value, value)
        else:
            parameters = getattr(value, "__parameters__", ())
            if parameters:
                # 按定义内部的参数顺序绑定，交给 Python 完成嵌套替换。
                # type Pair[T, U] = tuple[U, T] 的内部顺序是 U、T。
                value = value[
                    tuple(
                        bindings.get(parameter, parameter) for parameter in parameters
                    )
                ]
        cur = value
    return (object if cur is None else cur), tuple(meta)


def strip_optional(ann: object) -> object:
    """``T | None``（恰一个非 None 成员）→ ``T``；否则原样返回。"""
    origin = get_origin(ann)
    if origin is not Union and origin is not UnionType:
        return ann
    non_none = [a for a in get_args(ann) if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    return ann
