"""L1 配置集合 ``ConfigCollection``：管理多个 ConfigEntry 成员。

公开 Wire 字段仅 ``order`` + ``data``（§3.9）。

Entry 类型集在构造时固定；运行时开放类型表（register/unregister/reload）
已明确不做，保持 closed。
"""

from __future__ import annotations

import weakref
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ClassVar, Generic, Iterator, Self, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import Field, PrivateAttr

from ..errors import ConfigAggregateError, DeletedNodeError
from .manager import config_manager
from .node import ConfigNode, NodeState
from ..signals import CollectionChangeEvent
from .staging import StageKind, StagedOp
from ..wire import CollectionOrderItem, ExportContext, WireDict

TEntry = TypeVar("TEntry", bound=ConfigNode)

type RemoveGuard[E: ConfigNode] = Callable[
    [ConfigCollection[E], UUID, E], Awaitable[None]
]
"""commit 应用 remove 前的异步守卫；抛错则本笔事务失败回滚。"""


class ConfigCollection(ConfigNode, Generic[TEntry]):
    """L1 配置集合。"""

    # 类型化子类（如 FastAPI response_model）可声明默认成员类型用于热态调度
    _default_entry_types: ClassVar[tuple[type[ConfigNode], ...]] = ()
    # 本实例允许的成员类型：类名 → 类型（构造 / collection() 传入；固定不可改）
    _entry_types: dict[str, type[TEntry]] = PrivateAttr(default_factory=dict)
    # remove 守卫（挂 live；不经工作区拷贝语义影响读路径）
    _remove_guards: list[RemoveGuard[TEntry]] = PrivateAttr(default_factory=list)

    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[UUID, TEntry] = Field(default_factory=dict)

    def __init__(
        self,
        entry_types: type[TEntry] | list[type[TEntry]] | None = None,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        wire: WireDict | None = None,
        file: Path | str | None = None,
        name: str | None = None,
        **field_values: object,
    ) -> None:
        # field_values 承接 pydantic model_validate 注入的 order/data 字段（FastAPI Body 必需）。
        # 嵌套字段须经 collection() 声明，不经本构造的 name=/file= 登记路径。
        super().__init__(**field_values)
        self._parent_ref = weakref.ref(parent) if parent is not None else None
        if wire is not None and file is not None:
            raise ValueError("wire 与 file 互斥")
        if file is not None:
            if not self.is_root:
                raise ValueError("仅根节点可 file=")
            config_manager.register_root(self, Path(file))
        if uid is not None:
            self._uid = uid if isinstance(uid, UUID) else UUID(uid)
        resolved_types: list[type[TEntry]]
        if entry_types is None:
            resolved_types = cast(
                list[type[TEntry]], list(type(self)._default_entry_types)
            )
        elif isinstance(entry_types, type):
            resolved_types = [cast(type[TEntry], entry_types)]
        else:
            resolved_types = entry_types
        types_by_name: dict[str, type[TEntry]] = {}
        for entry_cls in resolved_types:
            type_name = entry_cls.__name__
            prev = types_by_name.get(type_name)
            if prev is not None and prev is not entry_cls:
                raise ValueError(
                    f"Entry 类型名冲突: {type_name!r} 对应多个类型，"
                    f"add(str) 无法区分（{prev!r} vs {entry_cls!r}）"
                )
            types_by_name[type_name] = entry_cls
        self._entry_types = types_by_name
        if name is not None:
            if not self.is_root:
                raise ValueError(
                    "嵌套 Collection 禁止 name=；请事后 register_collection"
                )
            config_manager.register_collection(name, self)
        self._pending_wire = wire

    @classmethod
    def build(
        cls,
        entry_types: type[TEntry] | list[type[TEntry]] | None = None,
        *,
        parent: ConfigNode | None = None,
        uid: UUID | str | None = None,
        wire: WireDict | None = None,
        file: Path | str | None = None,
        name: str | None = None,
        **field_values: object,
    ) -> Self:
        """类型友好的构造入口（语义同 ``ConfigEntry.build``）。"""
        self = object.__new__(cls)
        # ``ConfigCollection.__init__`` 在 unbound 调用时 TEntry 退化为 Unknown；
        # 经 cls 绑定后与 build 的 TypeVar 一致。
        cls.__init__(
            self,
            entry_types,
            parent=parent,
            uid=uid,
            wire=wire,
            file=file,
            name=name,
            **field_values,
        )
        return self

    async def _commit_op(self, op: StagedOp) -> None:
        if op.kind not in (
            StageKind.COLLECTION_ADD,
            StageKind.COLLECTION_REMOVE,
            StageKind.COLLECTION_SET_ORDER,
        ):
            raise TypeError(f"Collection 不支持: {op.kind.value}")

        use_init = (
            op.kind == StageKind.COLLECTION_ADD
            and self.activation_state == NodeState.INITIALIZING
        )
        async with (
            config_manager.init_transaction()
            if use_init
            else config_manager.transaction()
        ):
            (self._build_init_workspace if use_init else self._build_workspace)()

            if op.kind == StageKind.COLLECTION_ADD:
                assert op.entry_type is not None and op.uid is not None
                if op.uid in self.effective.data:
                    raise ValueError(f"成员 uid 已存在: {op.uid}")
                # 推迟导入：entry ↔ collection；用 build 避开 pydantic 合成 __init__
                from .entry import ConfigEntry

                if not issubclass(op.entry_type, ConfigEntry):
                    raise TypeError(
                        f"Collection 成员须为 ConfigEntry 子类: {op.entry_type!r}"
                    )
                entry = cast(
                    TEntry,
                    op.entry_type.build(uid=op.uid, wire=op.wire, parent=self),
                )
                await entry.activate()
                self.effective.data[entry.uid] = entry
                self.effective.order.append(
                    CollectionOrderItem(uid=entry.uid, type=op.entry_type.__name__)
                )
                await type(self).send(
                    sender=self,
                    event=CollectionChangeEvent(
                        kind="init_add" if use_init else "add",
                        collection=self,
                        uid=entry.uid,
                        entry=entry,
                    ),
                )
            elif op.kind == StageKind.COLLECTION_REMOVE:
                assert op.uid is not None
                entry = self.effective.data[op.uid]
                # 先跑 remove_guard，再 mutate / send(remove)
                for guard in self._remove_guards:
                    await guard(self, op.uid, entry)
                await entry._delete()
                del self.effective.data[op.uid]
                self.effective.order = [
                    item for item in self.effective.order if item.uid != op.uid
                ]
                await type(self).send(
                    sender=self,
                    event=CollectionChangeEvent(
                        kind="remove", collection=self, uid=op.uid, entry=entry
                    ),
                )
            else:
                assert op.order is not None
                old_order = self.effective.order
                old_uids = [item.uid for item in old_order]
                if set(old_uids) != set(op.order) or len(old_uids) != len(op.order):
                    raise ValueError("顺序列表必须与现有成员一致，且无重复")
                by_uid = {item.uid: item for item in old_order}
                new_order = [by_uid[uid] for uid in op.order]
                self.effective.order = new_order
                await type(self).send(
                    sender=self,
                    event=CollectionChangeEvent(
                        kind="set_order",
                        collection=self,
                        old_order=old_order,
                        order=new_order,
                    ),
                )

            if self._staged_ops:
                raise RuntimeError(
                    "信号回调须在返回前 commit 当次 stage，"
                    f"残留 {len(self._staged_ops)} 条"
                )

    # ──────────────── 访问 ────────────────

    def __getitem__(self, uid: UUID | str) -> TEntry:
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if isinstance(uid, str):
            uid = UUID(uid)
        entry = self.effective.data[uid]
        if entry.deleted:
            raise DeletedNodeError(entry.uid)
        return entry

    def __contains__(self, uid: UUID | str) -> bool:
        if isinstance(uid, str):
            try:
                uid = UUID(uid)
            except ValueError:
                return False
        if uid not in self.effective.data:
            return False
        return not self.effective.data[uid].deleted

    def keys(self) -> Iterator[UUID]:
        """可见（未软删）成员 uid，顺序同 ``order``。"""
        for item in self.effective.order:
            entry = self.effective.data.get(item.uid)
            if entry is not None and not entry.deleted:
                yield item.uid

    def __len__(self) -> int:
        return sum(1 for _ in self.keys())

    def values(self) -> Iterator[TEntry]:
        for uid in self.keys():
            yield self[uid]

    def iter_children(self) -> Iterator[ConfigNode]:
        yield from self.values()

    # ── 结构写：同步 stage，运行时须 await commit() ──

    def add(
        self,
        entry_type: type[TEntry] | str,
        *,
        uid: UUID | str | None = None,
        wire: WireDict | None = None,
    ) -> UUID:
        # ACTIVE：运行时追加；INITIALIZING：activate 热化复用本路径（→ init_add）
        if self.activation_state == NodeState.INACTIVE:
            raise ValueError("须先 activate")
        if isinstance(entry_type, str):
            etype = self._entry_types.get(entry_type)
            if etype is None:
                raise ValueError(f"不支持的 Entry 类型: {entry_type}")
        else:
            if entry_type not in self._entry_types.values():
                raise ValueError(
                    f"不支持的 Entry 类型: {getattr(entry_type, '__name__', entry_type)}"
                )
            etype = entry_type
        resolved = uid if isinstance(uid, UUID) else UUID(uid) if uid else uuid4()
        self._stage(StagedOp.collection_add(etype, uid=resolved, wire=wire))
        return resolved

    def remove(self, uid: UUID | str) -> None:
        if self.activation_state != NodeState.ACTIVE:
            raise ValueError("须先 activate")
        if isinstance(uid, str):
            uid = UUID(uid)
        if uid not in self:
            raise KeyError(uid)
        self._stage(StagedOp.collection_remove(uid))

    def set_order(self, order: list[UUID | CollectionOrderItem]) -> None:
        if self.activation_state != NodeState.ACTIVE:
            raise ValueError("须先 activate")
        new_uids = [item if isinstance(item, UUID) else item.uid for item in order]
        self._stage(StagedOp.collection_set_order(new_uids))

    def register_remove_guard(self, guard: RemoveGuard[TEntry]) -> None:
        """注册异步拒删守卫；在 commit 应用 remove 前依次 await。"""
        self._remove_guards.append(guard)

    def unregister_remove_guard(self, guard: RemoveGuard[TEntry]) -> None:
        """移除已注册的拒删守卫。"""
        self._remove_guards.remove(guard)

    # ──────────────── 激活 ────────────────

    async def _activate_from_payload(self, payload: WireDict) -> None:
        payload = payload or {}
        order = payload.get("order")
        if not isinstance(order, list):
            order = []
        data_raw = payload.get("data")
        data: WireDict = cast(WireDict, data_raw) if isinstance(data_raw, dict) else {}

        # 清空冷态残留（写 effective / ws；外层 activate 已建工作区）
        object.__setattr__(self.effective, "order", [])
        object.__setattr__(self.effective, "data", {})

        errors: list[Exception] = []
        for item in order:
            try:
                if not isinstance(item, dict):
                    raise TypeError(
                        f"order 项须为 dict，收到 {type(item).__name__}"
                    )
                uid = UUID(str(item["uid"]))
                type_name = str(item["type"])
                raw = data.get(str(uid))
                if isinstance(raw, ConfigNode):
                    wire = raw._export_wire(
                        ExportContext(if_decrypt=True, include_reactive=False)
                    )
                elif isinstance(raw, dict):
                    wire = cast(WireDict, raw)
                else:
                    wire = {}
                self.add(type_name, uid=uid, wire=wire)
                await self.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        if errors:
            raise ConfigAggregateError(errors)

    # ──────────────── 工作区 ────────────────

    def _make_workspace_shell(self, *, init: bool = False) -> Self:
        if init:
            assert self._workspace is not None
            src = cast(Self, self._workspace)
        else:
            src = self
        ws = src.model_copy()
        object.__setattr__(ws, "order", list(src.order))
        object.__setattr__(ws, "data", dict(src.data))
        ws._entry_types = dict(src._entry_types)
        ws._workspace = None
        ws._deleted = src._deleted
        ws._activation_state = src._activation_state
        ws._pending_wire = src._pending_wire
        ws._is_workspace = True
        return ws

    def _COMMIT(self) -> None:
        if self._workspace is None:
            return
        shell = cast(Self, self._workspace)
        object.__setattr__(self, "order", list(shell.order))
        object.__setattr__(self, "data", dict(shell.data))
        self._deleted = shell._deleted
        self._activation_state = shell._activation_state
        self._pending_wire = shell._pending_wire
        self._workspace = None

    def _COMMIT_init(self) -> None:
        if self._workspace is None or self._workspace._workspace is None:
            return
        init = cast(Self, self._workspace._workspace)
        object.__setattr__(self._workspace, "order", list(init.order))
        object.__setattr__(self._workspace, "data", dict(init.data))
        self._workspace._deleted = init._deleted
        self._workspace._activation_state = init._activation_state
        self._workspace._pending_wire = init._pending_wire
        self._workspace._workspace = None

    # ──────────────── 导出 ────────────────

    def _export_wire(self, ctx: ExportContext) -> WireDict:
        """Wire 导出：读已提交 ``self``，不经 ``effective``；跳过已软删成员。"""
        return {
            "order": [
                {"uid": str(item.uid), "type": item.type}
                for item in self.order
                if (entry := self.data.get(item.uid)) is not None and not entry.deleted
            ],
            "data": {
                str(uid): entry._export_wire(ctx)
                for uid, entry in self.data.items()
                if not entry.deleted
            },
        }
