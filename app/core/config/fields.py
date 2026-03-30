from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


RefDeleteAction = Literal["restrict", "set_default", "cascade", "custom"]
VirtualDependency = tuple[str, str]


@dataclass(frozen=True, slots=True)
class RefField:
    """声明式引用字段元数据。"""

    target: str
    default: Any
    allow_values: tuple[Any, ...] = ()
    on_delete: RefDeleteAction = "set_default"
    on_delete_callback: str | Callable[[Any, Any], Any] | None = None


@dataclass(frozen=True, slots=True)
class VirtualField:
    """声明式虚拟字段元数据。"""

    getter: str | Callable[[Any], Any]
    setter: str | Callable[[Any, Any], Any] | None = None
    depends_on: tuple[VirtualDependency, ...] = field(default_factory=tuple)

