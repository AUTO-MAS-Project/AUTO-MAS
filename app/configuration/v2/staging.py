"""Node 暂存 op；``await commit()`` 时按序落入事务。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from .wire import WireDict


class StageKind(str, Enum):
    """暂存写操作种类（Entry 字段 / Collection 结构）。"""

    FIELD_SET = "field_set"
    COLLECTION_ADD = "collection_add"
    COLLECTION_REMOVE = "collection_remove"
    COLLECTION_SET_ORDER = "collection_set_order"


@dataclass(frozen=True)
class StagedOp:
    """统一暂存记录；``kind`` 区分语义，其余字段按 kind 选用。"""

    kind: StageKind
    group: str | None = None
    field: str | None = None
    value: object = None
    entry_type: type | None = None
    uid: UUID | None = None
    wire: WireDict | None = None
    order: tuple[UUID, ...] | None = None

    @classmethod
    def field_set(cls, group: str, field: str, value: object) -> StagedOp:
        return cls(kind=StageKind.FIELD_SET, group=group, field=field, value=value)

    @classmethod
    def collection_add(
        cls, entry_type: type, *, uid: UUID, wire: WireDict | None
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
