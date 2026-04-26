from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class RefDeleteAction(str, Enum):
    RESTRICT = "restrict"
    SET_DEFAULT = "set_default"
    CASCADE = "cascade"
    CUSTOM = "custom"
VirtualDependency = tuple[str, str]


class OnDeleteCallback(Protocol):
    """引用字段删除回调协议。"""

    def __call__(self, owner: Any, deleted_value: Any) -> Any:
        """
        当引用的对象被删除时调用。

        Args:
            owner: 拥有引用字段的配置对象
            deleted_value: 被删除的引用值

        Returns:
            新的字段值
        """
        ...


@dataclass(frozen=True, slots=True)
class RefField:
    """
    声明式引用字段元数据。

    用于标记一个字段引用另一个配置对象，并定义引用完整性约束。

    Attributes:
        target: 引用目标的配置类型名称
        default: 引用失效时的默认值
        allow_values: 允许的特殊值（如 "-" 表示未选择）
        on_delete: 删除策略
        on_delete_callback: 自定义删除回调（仅当 on_delete="custom" 时有效）
    """

    target: str
    default: Any
    allow_values: tuple[Any, ...] = ()
    on_delete: RefDeleteAction = RefDeleteAction.SET_DEFAULT
    on_delete_callback: OnDeleteCallback | str | None = None

    def __post_init__(self) -> None:
        """验证字段配置。"""
        if self.on_delete == RefDeleteAction.CUSTOM and self.on_delete_callback is None:
            raise ValueError("on_delete='custom' 时必须提供 on_delete_callback")
        if self.on_delete != RefDeleteAction.CUSTOM and self.on_delete_callback is not None:
            raise ValueError("on_delete_callback 仅在 on_delete='custom' 时有效")


class VirtualFieldGetter(Protocol):
    """虚拟字段 getter 协议。"""

    def __call__(self, owner: Any) -> Any:
        """
        获取虚拟字段的值。

        Args:
            owner: 拥有虚拟字段的配置对象

        Returns:
            虚拟字段的计算值
        """
        ...


class VirtualFieldSetter(Protocol):
    """虚拟字段 setter 协议。"""

    def __call__(self, owner: Any, value: Any) -> Any:
        """
        设置虚拟字段的值。

        Args:
            owner: 拥有虚拟字段的配置对象
            value: 要设置的值

        Returns:
            实际设置的值
        """
        ...


@dataclass(frozen=True, slots=True)
class VirtualField:
    """
    声明式虚拟字段元数据。

    虚拟字段不直接存储数据，而是通过 getter/setter 计算或代理到其他字段。

    Attributes:
        getter: 获取字段值的函数或方法名
        setter: 设置字段值的函数或方法名（可选）
        depends_on: 依赖的字段列表，格式为 (group, field)
    """

    getter: VirtualFieldGetter | str
    setter: VirtualFieldSetter | str | None = None
    depends_on: tuple[VirtualDependency, ...] = field(default_factory=tuple)
