"""声明装饰器与快捷工厂：``ref`` / ``collection`` / ``virtual_field`` / ``trigger_field`` 等。"""

from __future__ import annotations

from typing import Callable, TypeVar, cast

from pydantic import Field
from pydantic.fields import FieldInfo

from .core.collection import ConfigCollection
from .core.node import ConfigNode
from .fields import (
    NestedCollectionMarker,
    OnDeleteCallback,
    RefDeleteAction,
    RefField,
    Select,
    TriggerFieldBinding,
    VirtualFieldBinding,
    encrypted,
    legacy,
    parse_field_path,
    select,
    ui,
)

_F = TypeVar("_F", bound=Callable[..., object])
_TEntry = TypeVar("_TEntry", bound=ConfigNode)


def ref(
    target: str,
    *,
    default: str = "-",
    allow_values: tuple[str, ...] = (),
    on_delete: RefDeleteAction = RefDeleteAction.SET_DEFAULT,
    on_delete_callback: OnDeleteCallback | str | None = None,
) -> RefField:
    """声明 UUID 外键引用字段（置于 ``Annotated`` 内）。

    ``target`` 须经 ``manager.register_collection`` 登记的 ref 池名。
    """
    return RefField(
        target=target,
        default=default,
        allow_values=allow_values,
        on_delete=on_delete,
        on_delete_callback=on_delete_callback,
    )


def collection(*entry_types: type[_TEntry]) -> ConfigCollection[_TEntry]:
    """声明 Entry 上的嵌套 ``ConfigCollection`` 字段（唯一合法挂载方式）。

    运行时返回 ``FieldInfo``（类体赋值）；注解为 ``ConfigCollection[T]`` 供类型检查
    （与 Django ``ForeignKey`` 等描述符写法相同）。
    """
    types = list(entry_types)
    info = cast(
        FieldInfo,
        Field(
            default_factory=lambda: ConfigCollection(types),
            exclude=True,
            repr=False,
        ),
    )
    info.metadata.append(NestedCollectionMarker())
    return cast(ConfigCollection[_TEntry], info)


def virtual_field(path: str) -> Callable[[_F], _F]:
    """注册只读虚拟字段，通过 ``entry.<group>.<field>`` 访问。"""
    group, field_name = parse_field_path(path)

    def _decorator(func: _F) -> _F:
        setattr(
            func,
            "__virtual_field_binding__",
            VirtualFieldBinding(
                group=group, field_name=field_name, getter=func.__name__
            ),
        )
        return func

    return _decorator


def trigger_field(path: str) -> Callable[[_F], _F]:
    """注册触发器；``entry.<group>.<field> = True`` 执行一次 handler。"""
    group, field_name = parse_field_path(path)

    def _decorator(func: _F) -> _F:
        setattr(
            func,
            "__trigger_field_binding__",
            TriggerFieldBinding(
                group=group, field_name=field_name, handler=func.__name__
            ),
        )
        return func

    return _decorator


__all__ = [
    "ref",
    "collection",
    "virtual_field",
    "trigger_field",
    "encrypted",
    "ui",
    "select",
    "legacy",
    "Select",
]
