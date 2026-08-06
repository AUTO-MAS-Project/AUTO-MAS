"""Node 暂存 op；``await commit()`` 时按序落入事务。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..wire import WireDict

if TYPE_CHECKING:
    from .node import ConfigNode


class StageKind(str, Enum):
    """暂存写操作种类（Entry 字段 / Collection 结构）。"""

    FIELD_SET = "field_set"
    COLLECTION_ADD = "collection_add"
    COLLECTION_REMOVE = "collection_remove"
    COLLECTION_SET_ORDER = "collection_set_order"
    COLLECTION_ADD_TYPE = "collection_add_type"
    COLLECTION_REMOVE_TYPE = "collection_remove_type"
    COLLECTION_RELOAD_TYPE = "collection_reload_type"


@dataclass(frozen=True)
class StagedOp:
    """统一暂存记录；``kind`` 区分语义，其余字段按 kind 选用。"""

    kind: StageKind
    group: str | None = None
    field: str | None = None
    value: object = None
    entry_type: type[ConfigNode] | None = None
    uid: UUID | None = None
    wire: WireDict | None = None
    order: tuple[UUID, ...] | None = None

    @classmethod
    def field_set(cls, group: str, field: str, value: object) -> StagedOp:
        return cls(kind=StageKind.FIELD_SET, group=group, field=field, value=value)

    @classmethod
    def collection_add(
        cls, entry_type: type[ConfigNode], *, uid: UUID, wire: WireDict | None
    ) -> StagedOp:
        return cls(
            kind=StageKind.COLLECTION_ADD,
            entry_type=entry_type,
            uid=uid,
            wire=wire,
        )

    @classmethod
    def collection_remove(cls, uid: UUID) -> StagedOp:
        return cls(kind=StageKind.COLLECTION_REMOVE, uid=uid)

    @classmethod
    def collection_set_order(cls, order: list[UUID]) -> StagedOp:
        return cls(kind=StageKind.COLLECTION_SET_ORDER, order=tuple(order))

    @classmethod
    def collection_add_type(cls, entry_type: type[ConfigNode]) -> StagedOp:
        return cls(kind=StageKind.COLLECTION_ADD_TYPE, entry_type=entry_type)

    @classmethod
    def collection_remove_type(cls, entry_type: type[ConfigNode]) -> StagedOp:
        return cls(kind=StageKind.COLLECTION_REMOVE_TYPE, entry_type=entry_type)

    @classmethod
    def collection_reload_type(cls, entry_type: type[ConfigNode]) -> StagedOp:
        return cls(kind=StageKind.COLLECTION_RELOAD_TYPE, entry_type=entry_type)
