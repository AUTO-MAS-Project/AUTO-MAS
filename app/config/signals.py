"""配置变更信号：基于 blinker；与工作区 / 事务集成。

- 发送者（sender）：``entry.connect(...)`` 的 entry；``send(sender=…)`` / 回调首参同义。
- 接收者（receiver）：用户 handler fn；包装为 ``wrapped`` 注册进 blinker。
- 守卫：发送者 deleted 仅 ``Cls.send`` 检查；``_wrap`` 仅对 ConfigNode 实例方法查 deleted。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID


from .core.node import ConfigNode
from .wire import CollectionOrderItem

if TYPE_CHECKING:
    from .core.entry import ConfigEntry

type ConfigEvent = FieldChangeEvent | CollectionChangeEvent
type SignalCallback = Callable[..., object | Awaitable[object] | None]
type WrappedSignal = Callable[..., object | Awaitable[object] | None]


@dataclass(frozen=True)
class FieldChangeEvent:
    """Entry 字段变更事件。回调首参 ``sender`` 为发送者 Entry。"""

    kind: Literal["init_set", "set"]
    node: ConfigEntry
    group: str
    field: str
    value: object
    old_value: object

    @property
    def config(self) -> ConfigEntry:
        """兼容别名：发送该事件的 Entry。"""
        return self.node

    @property
    def config_uid(self) -> UUID:
        return self.node.uid


@dataclass(frozen=True)
class CollectionChangeEvent:
    """Collection 结构变更事件。回调首参 ``sender`` 为发送者 Collection。"""

    kind: Literal["init_add", "add", "remove", "set_order"]
    collection: ConfigNode
    uid: UUID | None = None
    entry: ConfigNode | None = None
    old_order: list[CollectionOrderItem] | None = None
    order: list[CollectionOrderItem] | None = None
