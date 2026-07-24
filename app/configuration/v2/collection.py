"""L1 配置集合 ``ConfigCollection``：管理多个 ConfigEntry 成员。

公开 Wire 字段仅 ``order`` + ``data``（§3.9）。
"""

from __future__ import annotations

import weakref
from pathlib import Path
from typing import ClassVar, Generic, Iterator, Self, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import Field, PrivateAttr

from .errors import ConfigAggregateError, DeletedNodeError
from .manager import config_manager
from .node import ConfigNode, NodeState
from .signals import CollectionChangeEvent
from .staging import StageKind, StagedOp
from .wire import CollectionOrderItem, ExportContext, WireDict

TEntry = TypeVar("TEntry", bound=ConfigNode)


class ConfigCollection(ConfigNode, Generic[TEntry]):
    """L1 配置集合。"""

    # 类型化子类（如 FastAPI response_model）可声明默认成员类型用于热态调度
    _default_entry_types: ClassVar[tuple[type, ...]] = ()
    # 本实例允许的成员类型：类名 → 类型（构造 / collection() 传入）
    _entry_types: dict[str, type] = PrivateAttr(default_factory=dict)

    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[UUID, TEntry] = Field(default_factory=dict)

    def __getattribute__(self, name: str) -> object:
        if name == "order":
            raw = cast(
                list[CollectionOrderItem],
                object.__getattribute__(self, "__dict__")["order"],
            )
            return [item.model_copy(deep=True) for item in raw]
        if name == "data":
            raw = cast(
                dict[UUID, TEntry],
                object.__getattribute__(self, "__dict__")["data"],
            )
            return dict(raw)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"order", "data"} and name in self.__dict__:
            raise AttributeError(
                f"Collection.{name} 只读；请使用 add/remove/set_order + commit"
            )
        super().__setattr__(name, value)

    def _raw_order(self) -> list[CollectionOrderItem]:
        return cast(list[CollectionOrderItem], self.__dict__["order"])

    def _raw_data(self) -> dict[UUID, TEntry]:
        return cast(dict[UUID, TEntry], self.__dict__["data"])

    @staticmethod
    def _copy_order(
        order: list[CollectionOrderItem],
    ) -> list[CollectionOrderItem]:
        return [item.model_copy(deep=True) for item in order]

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
        if uid is not None:
            self._uid = uid if isinstance(uid, UUID) else UUID(uid)
        if entry_types is None:
            entry_types = list(type(self)._default_entry_types)
        elif isinstance(entry_types, type):
            entry_types = [entry_types]
        types_by_name: dict[str, type] = {}
        for entry_cls in entry_types:
            type_name = entry_cls.__name__
            prev = types_by_name.get(type_name)
            if prev is not None and prev is not entry_cls:
                raise ValueError(
                    f"Entry 类型名冲突: {type_name!r} 对应多个类型，"
                    f"add(str) 无法区分（{prev!r} vs {entry_cls!r}）"
                )
            types_by_name[type_name] = entry_cls
        self._entry_types = types_by_name
        self._validate_materialized_state()

        # Register only after constructor-provided order/data have passed all
        # invariants, otherwise a failed constructor would leak registrations.
        if file is not None:
            if not self.is_root:
                raise ValueError("仅根节点可 file=")
            config_manager.register_root(self, Path(file))
        if name is not None:
            if not self.is_root:
                raise ValueError(
                    "嵌套 Collection 禁止 name=；请事后 register_collection"
                )
            config_manager.register_collection(name, self)
        self._pending_wire = wire

    def _validate_materialized_state(self) -> None:
        """Validate an already materialized order/data pair."""
        order = self._raw_order()
        data = self._raw_data()
        order_uids = [item.uid for item in order]
        if len(order_uids) != len(set(order_uids)):
            raise ValueError("Collection order 包含重复 uid")

        order_set = set(order_uids)
        data_set = set(data)
        if order_set != data_set:
            missing = sorted(str(uid) for uid in order_set - data_set)
            orphaned = sorted(str(uid) for uid in data_set - order_set)
            raise ValueError(
                "Collection order/data uid 不一致: "
                f"missing={missing}, orphaned={orphaned}"
            )

        for item in order:
            expected_type = self._entry_types.get(item.type)
            entry = data[item.uid]
            if entry.uid != item.uid:
                raise ValueError(
                    "Collection entry uid mismatch: "
                    f"key={item.uid}, data={entry.uid}"
                )
            if expected_type is None or type(entry) is not expected_type:
                raise ValueError(
                    "Collection entry type mismatch: "
                    f"uid={item.uid}, order={item.type}, "
                    f"data={type(entry).__name__}"
                )

    def _validate_wire_payload(
        self,
        payload: WireDict,
    ) -> list[tuple[UUID, str, WireDict]]:
        """Validate Wire structure before constructing any child Entry."""
        unknown_top = sorted(str(key) for key in set(payload) - {"order", "data"})
        if unknown_top:
            raise ValueError(
                "unknown configuration paths: "
                + ", ".join(f"$.{key}" for key in unknown_top)
            )
        order_raw = payload.get("order", [])
        data_raw = payload.get("data", {})
        if not isinstance(order_raw, list):
            raise TypeError("Collection Wire order 必须是 list")
        if not isinstance(data_raw, dict):
            raise TypeError("Collection Wire data 必须是 dict")

        order_items: list[tuple[UUID, str]] = []
        order_uids: set[UUID] = set()
        for index, item in enumerate(order_raw):
            if not isinstance(item, dict):
                raise TypeError(
                    f"order 项须为 dict，收到 {type(item).__name__}"
                )
            unknown_item = sorted(str(key) for key in set(item) - {"uid", "type"})
            if unknown_item:
                raise ValueError(
                    "unknown configuration paths: "
                    + ", ".join(
                        f"$.order[{index}].{key}" for key in unknown_item
                    )
                )
            try:
                uid = UUID(str(item["uid"]))
                type_name = str(item["type"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Collection order 项缺少有效 uid/type") from exc
            if uid in order_uids:
                raise ValueError(f"Collection order 包含重复 uid: {uid}")
            if type_name not in self._entry_types:
                raise ValueError(f"不支持的 Entry 类型: {type_name}")
            order_uids.add(uid)
            order_items.append((uid, type_name))

        data_by_uid: dict[UUID, object] = {}
        for raw_uid, raw_value in data_raw.items():
            try:
                uid = UUID(str(raw_uid))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Collection data key 不是有效 uid: {raw_uid}") from exc
            if uid in data_by_uid:
                raise ValueError(f"Collection data 包含重复 uid: {uid}")
            data_by_uid[uid] = raw_value

        data_uids = set(data_by_uid)
        if order_uids != data_uids:
            missing = sorted(str(uid) for uid in order_uids - data_uids)
            orphaned = sorted(str(uid) for uid in data_uids - order_uids)
            raise ValueError(
                "Collection Wire order/data uid 不一致: "
                f"missing={missing}, orphaned={orphaned}"
            )

        validated: list[tuple[UUID, str, WireDict]] = []
        for uid, type_name in order_items:
            raw = data_by_uid[uid]
            expected_type = self._entry_types[type_name]
            if isinstance(raw, ConfigNode):
                if raw.uid != uid:
                    raise ValueError(
                        "Collection Wire entry uid mismatch: "
                        f"key={uid}, data={raw.uid}"
                    )
                if type(raw) is not expected_type:
                    raise ValueError(
                        "Collection Wire entry type mismatch: "
                        f"uid={uid}, order={type_name}, "
                        f"data={type(raw).__name__}"
                    )
                wire = raw._export_wire(
                    ExportContext(if_decrypt=True, include_reactive=False)
                )
            elif isinstance(raw, dict):
                wire = cast(WireDict, raw)
            else:
                raise TypeError(
                    "Collection Wire data 项须为 dict 或 ConfigNode: "
                    f"uid={uid}, received={type(raw).__name__}"
                )
            validated.append((uid, type_name, wire))
        return validated

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
            effective = self.effective
            effective_order = effective._raw_order()
            effective_data = effective._raw_data()

            if op.kind == StageKind.COLLECTION_ADD:
                assert op.entry_type is not None and op.uid is not None
                if op.uid in effective_data:
                    raise ValueError(f"成员 uid 已存在: {op.uid}")
                entry = cast(
                    TEntry,
                    op.entry_type(  # pyright: ignore[reportCallIssue]
                        uid=op.uid, wire=op.wire, parent=self
                    ),
                )
                await entry.activate()
                effective_data[entry.uid] = entry
                effective_order.append(
                    CollectionOrderItem(uid=entry.uid, type=op.entry_type.__name__)
                )
                await type(self).emit_change(
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
                entry = effective_data[op.uid]
                await entry._delete()
                del effective_data[op.uid]
                object.__setattr__(
                    effective,
                    "order",
                    [item for item in effective_order if item.uid != op.uid],
                )
                await type(self).emit_change(
                    sender=self,
                    event=CollectionChangeEvent(
                        kind="remove", collection=self, uid=op.uid, entry=entry
                    ),
                )
            else:
                assert op.order is not None
                old_order = effective_order
                old_uids = [item.uid for item in old_order]
                if set(old_uids) != set(op.order) or len(old_uids) != len(op.order):
                    raise ValueError("顺序列表必须与现有成员一致，且无重复")
                by_uid = {item.uid: item for item in old_order}
                new_order = [by_uid[uid] for uid in op.order]
                object.__setattr__(effective, "order", new_order)
                await type(self).emit_change(
                    sender=self,
                    event=CollectionChangeEvent(
                        kind="set_order",
                        collection=self,
                        old_order=self._copy_order(old_order),
                        order=self._copy_order(new_order),
                    ),
                )

            staged_count = len(self._current_staged_ops())
            if staged_count:
                raise RuntimeError(
                    "信号回调须在返回前 commit 当次 stage，"
                    f"残留 {staged_count} 条"
                )

    # ──────────────── 访问 ────────────────

    def __getitem__(self, uid: UUID | str) -> TEntry:
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if isinstance(uid, str):
            uid = UUID(uid)
        entry = cast(TEntry, self.effective._raw_data()[uid])
        if entry.deleted:
            raise DeletedNodeError(entry.uid)
        return entry

    def __contains__(self, uid: UUID | str) -> bool:
        if isinstance(uid, str):
            try:
                uid = UUID(uid)
            except ValueError:
                return False
        effective_data = self.effective._raw_data()
        if uid not in effective_data:
            return False
        return not effective_data[uid].deleted

    def keys(self) -> Iterator[UUID]:
        """可见（未软删）成员 uid，顺序同 ``order``。"""
        effective = self.effective
        for item in effective._raw_order():
            entry = effective._raw_data().get(item.uid)
            if entry is not None and not entry.deleted:
                yield item.uid

    def __len__(self) -> int:
        return sum(1 for _ in self.keys())

    def values(self) -> Iterator[TEntry]:
        for uid in self.keys():
            yield self[uid]

    def items(self) -> Iterator[tuple[UUID, TEntry]]:
        """Yield visible members in collection order."""

        for uid in self.keys():
            yield uid, self[uid]

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

    # ──────────────── 激活 ────────────────

    async def _activate_from_payload(self, payload: WireDict) -> None:
        payload = payload or {}
        validated_items = self._validate_wire_payload(payload)

        # 清空冷态残留（写 effective / ws；外层 activate 已建工作区）
        object.__setattr__(self.effective, "order", [])
        object.__setattr__(self.effective, "data", {})

        errors: list[Exception] = []
        for uid, type_name, wire in validated_items:
            try:
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
        object.__setattr__(ws, "order", list(src._raw_order()))
        object.__setattr__(ws, "data", dict(src._raw_data()))
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
        object.__setattr__(self, "order", list(shell._raw_order()))
        object.__setattr__(self, "data", dict(shell._raw_data()))
        self._deleted = shell._deleted
        self._activation_state = shell._activation_state
        self._pending_wire = shell._pending_wire
        self._workspace = None

    def _COMMIT_init(self) -> None:
        if self._workspace is None or self._workspace._workspace is None:
            return
        init = cast(Self, self._workspace._workspace)
        object.__setattr__(self._workspace, "order", list(init._raw_order()))
        object.__setattr__(self._workspace, "data", dict(init._raw_data()))
        self._workspace._deleted = init._deleted
        self._workspace._activation_state = init._activation_state
        self._workspace._pending_wire = init._pending_wire
        self._workspace._workspace = None

    # ──────────────── 导出 ────────────────

    def _export_wire(self, ctx: ExportContext) -> WireDict:
        """Export committed state or one recursively consistent workspace."""
        source = cast(
            ConfigCollection[TEntry],
            self.effective if ctx.include_staged else self,
        )
        source._validate_materialized_state()
        order = source._raw_order()
        data = source._raw_data()

        def is_visible(entry: ConfigNode) -> bool:
            selected = entry.effective if ctx.include_staged else entry
            return not selected._deleted

        return {
            "order": [
                {"uid": str(item.uid), "type": item.type}
                for item in order
                if (entry := data.get(item.uid)) is not None
                and is_visible(entry)
            ],
            "data": {
                str(uid): entry._export_wire(ctx)
                for uid, entry in data.items()
                if is_visible(entry)
            },
        }
