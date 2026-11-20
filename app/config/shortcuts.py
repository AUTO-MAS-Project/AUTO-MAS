"""声明装饰器与快捷工厂：``ref`` / ``collection`` / ``virtual_field`` / ``trigger_field`` 等。"""

from __future__ import annotations

from math import isfinite
from typing import Callable, Protocol, TypeVar, cast
from uuid import UUID

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
    UiVisibility,
    UiVisibilityBinding,
    VirtualFieldBinding,
    encrypted,
    legacy,
    parse_field_path,
    select,
    ui,
)
from .fields.ref import _TriggerTimeout

_F = TypeVar("_F", bound=Callable[..., object])
_TEntry = TypeVar("_TEntry", bound=ConfigNode)


def ref(
    target: str,
    *,
    default: str = "-",
    allow_values: tuple[str, ...] = (),
    entry_types: tuple[type[ConfigNode], ...] = (),
    display_field: str | None = None,
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
        entry_types=entry_types,
        display_field=display_field,
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


def trigger(*, timeout: float, description: str | None = None) -> UUID | None:
    """声明触发器字段的执行超时，单位秒。字段仍以 None 为空闲初值。"""
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("触发器超时必须为有限的正数秒")
    info = cast(FieldInfo, Field(default=None, description=description))
    info.metadata.append(_TriggerTimeout(timeout))
    return cast(UUID | None, info)


class _TriggerDecorator(Protocol):
    def __call__[TEntry: ConfigNode, TResult](
        self,
        func: Callable[[TEntry], TResult],
    ) -> Callable[[TEntry], TResult]: ...


def trigger_field(path: str, *, finish_on_cancel: bool = False) -> _TriggerDecorator:
    """注册无参处理器；需完整收尾的副作用可声明 finish_on_cancel。"""
    group, field_name = parse_field_path(path)

    def _decorator[TEntry: ConfigNode, TResult](
        func: Callable[[TEntry], TResult],
    ) -> Callable[[TEntry], TResult]:
        setattr(func, "__trigger_finish_on_cancel__", finish_on_cancel)
        setattr(
            func,
            "__trigger_field_binding__",
            TriggerFieldBinding(
                group=group, field_name=field_name, handler=func.__name__
            ),
        )
        return func

    return _decorator


def ui_visibility(
    path: str,
) -> Callable[[Callable[..., UiVisibility]], Callable[..., UiVisibility]]:
    """注册字段 UI 显隐求值；须为返回 ``UiVisibility`` 的同步方法。"""
    group, field_name = parse_field_path(path)

    def _decorator(func: Callable[..., UiVisibility]) -> Callable[..., UiVisibility]:
        setattr(
            func,
            "__ui_visibility_binding__",
            UiVisibilityBinding(group=group, field_name=field_name, getter=func),
        )
        return func

    return _decorator


__all__ = [
    "ref",
    "collection",
    "virtual_field",
    "trigger",
    "trigger_field",
    "ui_visibility",
    "encrypted",
    "ui",
    "select",
    "legacy",
    "Select",
]
