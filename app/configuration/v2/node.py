"""统一基类 ``ConfigNode``：Entry / Collection 共享生命周期、工作区、信号、守卫。

``ConfigNode`` 继承 ``BaseModel``（Wire schema），其上叠加：

- 运行时私有状态（uid / parent / activation_state / deleted / locked / workspace）
- 工作区两层 API：读 ``effective`` / 写 ``_build_workspace``
- blinker 信号：``connect`` / ``disconnect`` / ``send``
- 生命周期：``activate`` / ``delete`` / ``lock`` / ``to_dict``
"""

from __future__ import annotations

import asyncio
import copy
import gc
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Iterator, Literal, Self, cast
from uuid import UUID, uuid4
from weakref import ReferenceType, WeakKeyDictionary, WeakMethod, ref

from blinker import ANY, Signal
from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    SerializationInfo,
    model_serializer,
)

from .errors import ConfigAggregateError, DeletedNodeError
from .manager import config_manager
from .node_state import NodeState
from .staging import StagedOp
from .wire import ExportContext, WireDict, read_wire_toml

if TYPE_CHECKING:
    from .group import ConfigGroup

# weakref.ref(parent) 的可调用引用；None 表示根节点
ParentRef = Callable[[], "ConfigNode | None"]
type StageTask = asyncio.Task[object]
type SignalRole = Literal["validator", "observer"]
type ReceiverKey = tuple[
    SignalRole,
    object | None,
    str,
    str | None,
    str | None,
    int | None,
]


@dataclass
class _SignalReceiverRecord:
    """Framework-owned wrappers keyed by receiver identity.

    ``target_ref`` never keeps a default-weak receiver alive.  ``wrappers`` do
    keep the wrapper functions alive while the target exists, because blinker
    itself stores them weakly.
    """

    target_ref: Callable[[], object | None]
    wrappers: dict[ReceiverKey, "WrappedSignal"] = dataclass_field(
        default_factory=dict
    )


def _current_stage_task() -> StageTask | None:
    try:
        return cast(StageTask | None, asyncio.current_task())
    except RuntimeError:
        return None


class _SignalDescriptor:
    """``connect`` / ``disconnect`` 的混合描述符：类访问 → 类级；实例访问 → 发送者=实例。"""

    def __init__(
        self,
        *,
        role: SignalRole,
        is_disconnect: bool,
        deprecated: bool = False,
    ) -> None:
        self._role = role
        self._is_disconnect = is_disconnect
        self._deprecated = deprecated

    def __get__(self, obj: "ConfigNode | None", owner: type["ConfigNode"]) -> Callable[
        ...,
        "SignalCallback | Callable[[SignalCallback], SignalCallback]",
    ]:
        role = self._role
        is_disconnect = self._is_disconnect
        deprecated = self._deprecated

        def caller(
            receiver: SignalCallback | None = None,
            *,
            phase: str = "runtime",
            group: str | None = None,
            field: str | None = None,
            weak: bool = True,
        ) -> SignalCallback | Callable[[SignalCallback], SignalCallback]:
            from .collection import ConfigCollection

            if deprecated:
                replacement = (
                    "disconnect_validator"
                    if is_disconnect
                    else "connect_validator"
                )
                warnings.warn(
                    f"ConfigNode.{'disconnect' if is_disconnect else 'connect'} "
                    f"已弃用；请迁移到 {replacement}，提交后的副作用请使用 "
                    "connect_observer",
                    DeprecationWarning,
                    stacklevel=2,
                )
            if issubclass(owner, ConfigCollection) and (
                group is not None or field is not None
            ):
                raise TypeError("Collection 信号不支持 group/field 过滤")
            sender = obj  # 类访问时为 None

            def register(fn: SignalCallback) -> SignalCallback:
                if is_disconnect:
                    owner._disconnect_impl(
                        fn,
                        role=role,
                        phase=phase,
                        group=group,
                        field=field,
                        sender=sender,
                    )
                else:
                    owner._connect_impl(
                        fn,
                        role=role,
                        phase=phase,
                        group=group,
                        field=field,
                        sender=sender,
                        weak=weak,
                    )
                return fn

            if receiver is None:
                return register
            return register(receiver)

        return caller


class ConfigNode(BaseModel):
    """Entry / Collection 统一基类。"""

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
        ignored_types=(_SignalDescriptor,),
        extra="forbid",
    )

    signal: ClassVar[Signal] = Signal()
    _signal_workspace: ClassVar[Signal | None] = None
    observer_signal: ClassVar[Signal] = Signal()
    _observer_signal_workspace: ClassVar[Signal | None] = None
    _signal_receiver_records: ClassVar[dict[int, _SignalReceiverRecord]] = {}

    # ── 运行时私有状态 ──
    _uid: UUID = PrivateAttr(default_factory=uuid4)
    _parent_ref: ParentRef | None = PrivateAttr(default=None)
    _activation_state: NodeState = PrivateAttr(default=NodeState.INACTIVE)
    _deleted: bool = PrivateAttr(default=False)
    _is_locked: bool = PrivateAttr(default=False)
    _workspace: "ConfigNode | None" = PrivateAttr(default=None)
    _pending_wire: WireDict | None = PrivateAttr(default=None)
    _is_workspace: bool = PrivateAttr(default=False)
    # 每个 asyncio Task 独占一条暂存队列；无 event loop 的同步 stage
    # 单独保留，直到首个 async commit 明确认领。
    _staged_ops_by_task: WeakKeyDictionary[StageTask, list[StagedOp]] = PrivateAttr(
        default_factory=WeakKeyDictionary
    )
    _staged_sync_ops: list[StagedOp] = PrivateAttr(default_factory=list)
    _commit_lock: asyncio.Lock | None = PrivateAttr(default=None)
    _commit_lock_loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)
    # ──────────────── 子类信号隔离 ────────────────

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        # 每个具体子类拥有独立 Signal（Collection 子类共享 ConfigCollection.signal 亦可）
        cls.signal = Signal()
        cls._signal_workspace = None
        cls.observer_signal = Signal()
        cls._observer_signal_workspace = None
        cls._signal_receiver_records = {}

    # ──────────────── 身份与层级 ────────────────

    @property
    def uid(self) -> UUID:
        return self._uid

    @property
    def parent(self) -> "ConfigNode | None":
        """解析后的父节点；无父或 weakref 已失效时为 ``None``。"""
        return self._parent_ref() if self._parent_ref is not None else None

    @property
    def activation_state(self) -> NodeState:
        """读经 ``effective``：事务内见工作区。"""
        return self.effective._activation_state

    @property
    def deleted(self) -> bool:
        """读经 ``effective``：事务内见工作区软删标记。"""
        return self.effective._deleted

    @property
    def is_locked(self) -> bool:
        """已激活后的即时锁定（不经工作区）；未激活无锁概念（由 ``INACTIVE`` 禁止热写）。"""
        return self._is_locked

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def root(self) -> "ConfigNode":
        node: ConfigNode = self
        while True:
            parent = node.parent
            if parent is None:
                return node
            node = parent

    @property
    def persist_path(self) -> Path | None:
        return config_manager.get_file(self.root)

    # ── 暂存 / 提交：stage 仅记录 op 队列；生效修改只在事务 ws（effective）内 ──

    def _current_staged_ops(self, *, create: bool = False) -> list[StagedOp]:
        """Return only the staging queue owned by the current Task."""
        task = _current_stage_task()
        if task is None:
            return self._staged_sync_ops
        ops = self._staged_ops_by_task.get(task)
        if ops is None:
            if not create:
                return []
            ops = []
            self._staged_ops_by_task[task] = ops
        return ops

    @property
    def _staged_ops(self) -> list[StagedOp]:
        """Compatibility view of the current task's pending operations.

        The reference framework exposed this private list and its own example
        listeners use it only as a truthiness check before nested ``commit``.
        Preserve that behavior without reintroducing one queue shared by all
        asyncio tasks.
        """
        task = _current_stage_task()
        if task is None:
            return self._staged_sync_ops
        task_ops = self._current_staged_ops()
        if not self._staged_sync_ops:
            return task_ops
        return [*self._staged_sync_ops, *task_ops]

    def _take_current_staged_ops(self) -> list[StagedOp]:
        """Claim the current Task batch plus legacy synchronous staging."""
        task = _current_stage_task()
        if task is None:
            batch = list(self._staged_sync_ops)
            self._staged_sync_ops.clear()
            return batch

        task_ops = self._staged_ops_by_task.pop(task, [])
        if not self._staged_sync_ops:
            return list(task_ops)
        batch = [*self._staged_sync_ops, *task_ops]
        self._staged_sync_ops.clear()
        return batch

    def _clear_current_staged_ops(self) -> None:
        task = _current_stage_task()
        if task is None:
            self._staged_sync_ops.clear()
        else:
            self._staged_ops_by_task.pop(task, None)

    def _restore_current_staged_ops(self, ops: list[StagedOp]) -> None:
        queue = self._current_staged_ops(create=True)
        queue.clear()
        queue.extend(ops)

    def _stage(self, op: StagedOp) -> None:
        """Append an operation only to the current Task's staging queue."""
        context = config_manager.current
        if context is not None and context.preparing_commit:
            raise RuntimeError(
                "configuration cannot be staged during prepare-commit"
            )
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")
        self._current_staged_ops(create=True).append(op)

    async def commit(self) -> None:
        """将当前暂存批次作为一个原子事务提交。

        任一字段、ref 或 listener 失败都会回滚本批已经成功的操作；
        child task 不能继承 owner 的事务或节点提交上下文。
        """
        context = config_manager.current
        if context is not None and context.preparing_commit:
            raise RuntimeError(
                "configuration cannot commit during prepare-commit"
            )
        if not self._current_staged_ops() and not self._staged_sync_ops:
            return
        # Guard failures happen before claiming the batch so callers may
        # unlock/restore the node and retry the exact same staged operations.
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")

        original_batch: list[StagedOp] = []
        transaction_context = None
        try:
            # Global transaction always precedes a node lock. This single lock
            # order also applies to listener-driven cross-node commits.
            async with config_manager.transaction() as context:
                transaction_context = context
                async with config_manager.node_commit(self):
                    if self.deleted:
                        raise DeletedNodeError(self.uid)
                    if self.is_locked:
                        raise ValueError("配置已锁定, 无法修改")
                    batch = self._take_current_staged_ops()
                    if not batch:
                        return
                    original_batch = list(batch)
                    while batch:
                        op = batch.pop(0)
                        await self._commit_op(op)
                        if self._current_staged_ops():
                            raise RuntimeError(
                                "signal callback 返回前必须提交它暂存的操作"
                            )
        except Exception as exc:
            if original_batch:
                self._clear_current_staged_ops()
            if isinstance(exc, ConfigAggregateError):
                raise
            raise ConfigAggregateError([exc]) from exc
        except BaseException:
            if original_batch:
                if transaction_context is not None and transaction_context.committed:
                    # Cancellation may arrive while awaiting a post-commit
                    # transport hook.  Live state is already irreversible, so
                    # restoring the batch would apply it a second time.
                    self._clear_current_staged_ops()
                else:
                    # Pre-commit cancellation rolls the workspace back; retain
                    # the whole owner batch rather than losing its prefix.
                    self._restore_current_staged_ops(original_batch)
            raise

    async def _commit_op(self, op: StagedOp) -> None:
        raise NotImplementedError(op.kind.value)

    # ──────────────── 工作区 API ────────────────

    @property
    def init_workspace(self) -> Self | None:
        """普通 ws 上的 init 层：``live._workspace._workspace``。"""
        if self._workspace is None or self._workspace._workspace is None:
            return None
        return cast(Self, self._workspace._workspace)

    @property
    def effective(self) -> Self:
        """读入口：init 层（``ws.ws``）→ 普通 ws → live。"""
        if config_manager.in_init_transaction and self.init_workspace is not None:
            return self.init_workspace
        if config_manager.in_transaction and self._workspace is not None:
            return cast(Self, self._workspace)
        return self

    def _build_workspace(self) -> None:
        if not config_manager.in_transaction:
            return
        if self._is_workspace:
            raise RuntimeError("工作区不可再次创建工作区")
        if self._deleted:
            raise DeletedNodeError(self.uid)
        if self._workspace is not None:
            return
        self._workspace = self._make_workspace_shell(init=False)
        config_manager._register_workspace(self)

    def _build_init_workspace(self) -> None:
        """在 ``self._workspace._workspace`` 挂载 init 壳并登记。

        禁止同节点在已有 init 壳时再次建立（禁止同节点重复开启 init 事务）。
        跨节点嵌套 init（如集合 ADD 与成员字段）各自建壳，不受影响。
        """
        if not config_manager.in_init_transaction:
            return
        if self._is_workspace:
            raise RuntimeError("须在 live 上调用 _build_init_workspace")
        if self._workspace is None:
            raise RuntimeError("init 须先建立普通工作区")
        if self._workspace._workspace is not None:
            raise RuntimeError("禁止同节点重复开启 init 事务")
        self._workspace._workspace = self._make_workspace_shell(init=True)
        config_manager._register_init_workspace(self)

    def _make_workspace_shell(self, *, init: bool = False) -> "ConfigNode":
        """``init=False`` 从 live 建普通 ws；``init=True`` 从 ``self._workspace`` 建 init 层。"""
        raise NotImplementedError

    def _COMMIT(self) -> None:
        raise NotImplementedError

    def _COMMIT_init(self) -> None:
        raise NotImplementedError

    def _ROLLBACK(self) -> None:
        self._workspace = None

    def _ROLLBACK_init(self) -> None:
        if self._workspace is not None:
            self._workspace._workspace = None

    @classmethod
    def signal_effective(cls) -> Signal:
        """Validator 信号读入口：事务内见工作区，否则见 live。"""
        ws = cls._signal_workspace
        if config_manager.in_transaction and ws is not None:
            return ws
        return cls.signal

    @classmethod
    def observer_signal_effective(cls) -> Signal:
        """Observer 信号读入口：事务内见工作区，否则见 live。"""
        ws = cls._observer_signal_workspace
        if config_manager.in_transaction and ws is not None:
            return ws
        return cls.observer_signal

    @staticmethod
    def _copy_signal_for_workspace(signal: Signal) -> Signal:
        """复制 Signal；处理弱订阅清理与 deepcopy 的瞬态竞争。"""

        try:
            return copy.deepcopy(signal)
        except RuntimeError as exc:
            if str(exc) != "dictionary changed size during iteration":
                raise
            # Blinker 的弱 receiver 在垃圾回收时会同步移除自身。若该回调
            # 恰好发生在 deepcopy 遍历 receivers 时，先完成回收再取快照。
            gc.collect()
            return copy.deepcopy(signal)

    @classmethod
    def _build_signal_workspace(cls) -> None:
        if not config_manager.in_transaction:
            return
        if cls._signal_workspace is not None:
            return
        cls._signal_workspace = cls._copy_signal_for_workspace(cls.signal)
        cls._observer_signal_workspace = cls._copy_signal_for_workspace(
            cls.observer_signal
        )
        config_manager._register_workspace(cls)

    @classmethod
    def _COMMIT_signal(cls) -> None:
        ws = cls._signal_workspace
        observer_ws = cls._observer_signal_workspace
        if ws is None or observer_ws is None:
            return
        cls.signal = ws
        cls.observer_signal = observer_ws
        cls._signal_workspace = None
        cls._observer_signal_workspace = None

    @classmethod
    def _ROLLBACK_signal(cls) -> None:
        cls._signal_workspace = None
        cls._observer_signal_workspace = None

    # ──────────────── 信号 ────────────────

    connect_validator = _SignalDescriptor(
        role="validator",
        is_disconnect=False,
    )
    disconnect_validator = _SignalDescriptor(
        role="validator",
        is_disconnect=True,
    )
    connect_observer = _SignalDescriptor(
        role="observer",
        is_disconnect=False,
    )
    disconnect_observer = _SignalDescriptor(
        role="observer",
        is_disconnect=True,
    )
    # Alpha compatibility: old ``connect`` callbacks were pre-commit and
    # therefore remain validators. New side effects must use observers.
    connect = _SignalDescriptor(
        role="validator",
        is_disconnect=False,
        deprecated=True,
    )
    disconnect = _SignalDescriptor(
        role="validator",
        is_disconnect=True,
        deprecated=True,
    )

    @staticmethod
    def _receiver_identity(
        receiver: SignalCallback,
    ) -> tuple[object, object | None]:
        """Return a stable identity for functions, bound methods and callables."""
        bound_self = getattr(receiver, "__self__", None)
        bound_function = getattr(receiver, "__func__", None)
        if bound_self is not None and bound_function is not None:
            return bound_self, bound_function
        return receiver, None

    @classmethod
    def _get_receiver_record(
        cls,
        receiver: SignalCallback,
        *,
        weak: bool,
        create: bool,
    ) -> tuple[
        _SignalReceiverRecord | None,
        object | None,
        Callable[[], object | None] | None,
    ]:
        """Resolve the framework-side wrapper registry without mutating receivers."""
        target, callable_token = cls._receiver_identity(receiver)
        target_id = id(target)
        record = cls._signal_receiver_records.get(target_id)
        if record is not None and record.target_ref() is not target:
            # A stale id can only remain for an explicitly strong record that
            # was externally corrupted; never reuse it for another object.
            cls._signal_receiver_records.pop(target_id, None)
            record = None
        if record is None and create:
            if weak:
                cls_ref = ref(cls)

                def forget_target(
                    dead_ref: ReferenceType[object],
                    *,
                    record_id: int = target_id,
                    owner_ref: ReferenceType[type[ConfigNode]] = cls_ref,
                ) -> None:
                    owner = owner_ref()
                    if owner is None:
                        return
                    current = owner._signal_receiver_records.get(record_id)
                    if current is not None and current.target_ref is dead_ref:
                        owner._signal_receiver_records.pop(record_id, None)

                try:
                    target_ref: Callable[[], object | None] = ref(
                        target, forget_target
                    )
                except TypeError:
                    raise TypeError(
                        "receiver 不支持弱引用；请传 weak=False 显式选择强订阅"
                    ) from None
            else:
                target_ref = lambda target=target: target
            record = _SignalReceiverRecord(target_ref=target_ref)
            cls._signal_receiver_records[target_id] = record

        if not create:
            return record, callable_token, None
        if weak:
            try:
                resolver: Callable[[], object | None]
                if callable_token is not None:
                    resolver = WeakMethod(receiver)  # type: ignore[arg-type]
                else:
                    resolver = ref(receiver)
            except TypeError:
                raise TypeError(
                    "receiver 不支持弱引用；请传 weak=False 显式选择强订阅"
                ) from None
        else:
            resolver = lambda receiver=receiver: receiver
        return record, callable_token, resolver

    @classmethod
    def _connect_impl(
        cls,
        receiver: SignalCallback,
        *,
        role: SignalRole = "validator",
        phase: str,
        group: str | None,
        field: str | None,
        sender: "ConfigNode | None",
        weak: bool = True,
    ) -> WrappedSignal:
        if config_manager.in_transaction:
            cls._build_signal_workspace()
        sig = (
            cls.signal_effective()
            if role == "validator"
            else cls.observer_signal_effective()
        )
        record, callable_token, resolver = cls._get_receiver_record(
            receiver,
            weak=weak,
            create=True,
        )
        assert record is not None and resolver is not None
        key: ReceiverKey = (
            role,
            callable_token,
            phase,
            group,
            field,
            id(sender) if sender is not None else None,
        )
        probe = sender if sender is not None else ANY
        wrapped = record.wrappers.get(key)
        if wrapped is not None:
            if wrapped in sig.receivers_for(probe):
                raise ValueError(
                    "重复订阅同一 (phase, group, field, sender)；请先 disconnect"
                )
        else:
            wrapped = _wrap(
                resolver,
                phase,
                group,
                field,
                receiver_label=_receiver_label(receiver),
            )
            record.wrappers[key] = wrapped
        sig.connect(wrapped, sender=probe, weak=weak)
        return wrapped

    @classmethod
    def _disconnect_impl(
        cls,
        receiver: SignalCallback,
        *,
        role: SignalRole = "validator",
        phase: str,
        group: str | None,
        field: str | None,
        sender: "ConfigNode | None",
    ) -> None:
        if config_manager.in_transaction:
            cls._build_signal_workspace()
        sig = (
            cls.signal_effective()
            if role == "validator"
            else cls.observer_signal_effective()
        )
        record, callable_token, _resolver = cls._get_receiver_record(
            receiver,
            weak=True,
            create=False,
        )
        if record is None:
            return
        key: ReceiverKey = (
            role,
            callable_token,
            phase,
            group,
            field,
            id(sender) if sender is not None else None,
        )
        # Keep the framework wrapper as a rollback-safe reconnect point.
        wrapped = record.wrappers.get(key)
        if wrapped is None:
            return
        probe = sender if sender is not None else ANY
        if wrapped not in sig.receivers_for(probe):
            # An activation transaction may have rolled back after registering
            # the receiver record.  Disconnect is intentionally idempotent so
            # final runtime disposal can still release its retained handle.
            return
        if sender is not None:
            sig.disconnect(wrapped, sender=sender)
        else:
            sig.disconnect(wrapped)

    @classmethod
    async def emit_change(
        cls,
        *,
        sender: "ConfigNode | None",
        event: ConfigEvent,
    ) -> None:
        """Validate a staged event, then queue its after-commit observation."""
        if sender is not None and sender.deleted:
            return
        await _dispatch_validators(cls.signal_effective(), sender, event)

        observer_signal = cls.observer_signal_effective()
        if not observer_signal.receivers:
            return

        async def dispatch_after_commit(
            transaction_id: UUID,
            revision: int,
            *,
            signal: Signal = observer_signal,
        ) -> AfterCommitObserverReport:
            return await _dispatch_observers(
                signal,
                sender,
                event,
                transaction_id=transaction_id,
                revision=revision,
            )

        config_manager.enqueue_after_commit(dispatch_after_commit)

    @classmethod
    async def send(cls, *, sender: "ConfigNode | None", event: ConfigEvent) -> None:
        """兼容入口；新代码使用 ``emit_change``。"""
        warnings.warn(
            "ConfigNode.send 已弃用；请使用 emit_change",
            DeprecationWarning,
            stacklevel=2,
        )
        await cls.emit_change(sender=sender, event=event)

    # ──────────────── 生命周期 ────────────────

    async def activate(self) -> None:
        """原子激活；任何失败都会让 live 节点保持 ``INACTIVE``。"""
        async with config_manager.transaction():
            async with config_manager.node_commit(self):
                # Re-check after acquiring the node lock so two callers cannot
                # initialize from stale INACTIVE observations.
                if self.activation_state != NodeState.INACTIVE:
                    raise ValueError("不可重复 activate")
                if self._pending_wire is not None:
                    payload = self._pending_wire
                elif self.persist_path is not None:
                    payload = read_wire_toml(self.persist_path)
                else:
                    payload = self._export_wire(
                        ExportContext(if_decrypt=True, include_reactive=False)
                    )
                self._build_workspace()
                self.effective._activation_state = NodeState.INITIALIZING
                await self._activate_from_payload(payload or {})
                self.effective._activation_state = NodeState.ACTIVE
                self.effective._pending_wire = None

    async def _activate_from_payload(self, payload: WireDict) -> None:
        raise NotImplementedError

    async def _delete(self) -> None:
        """内部软删；外部请用 Collection.remove / 框架生命周期，勿直接调用。"""
        if config_manager.is_registered_collection(self):
            raise RuntimeError("已登记 name 的 Collection 不可 delete")
        assert config_manager.in_transaction, "_delete 须在事务内"
        self._build_workspace()
        if self.deleted:
            raise DeletedNodeError(self.uid)
        for child in self.iter_children():
            await child._delete()
        self.effective._deleted = True

    async def lock(self) -> None:
        self._is_locked = True
        for child in self.iter_children():
            await child.lock()

    async def unlock(self) -> None:
        self._is_locked = False
        for child in self.iter_children():
            await child.unlock()

    def iter_children(self) -> Iterator["ConfigNode"]:
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    # ──────────────── 导出 ────────────────

    def _export_wire(self, ctx: ExportContext) -> WireDict:
        """实际导出业务逻辑；由 ``ctx`` 控制解密与响应式字段。"""
        raise NotImplementedError

    @staticmethod
    def _export_context(
        context: ExportContext | dict[str, object] | None,
    ) -> ExportContext:
        """Map Pydantic transport context to the explicit Wire boundary."""
        if isinstance(context, ExportContext):
            resolved = context
        elif isinstance(context, dict):
            resolved = ExportContext(
                if_decrypt=bool(context.get("if_decrypt", True)),
                include_reactive=bool(context.get("include_reactive", True)),
                include_staged=bool(context.get("include_staged", False)),
            )
        else:
            resolved = ExportContext(
                if_decrypt=True,
                include_reactive=True,
                include_staged=False,
            )
        ConfigNode._assert_staged_export_owner(resolved)
        return resolved

    @staticmethod
    def _assert_staged_export_owner(context: ExportContext) -> None:
        """Require staged export to run in its owning active transaction."""
        if context.include_staged and config_manager.current is None:
            raise RuntimeError(
                "staged configuration export requires an active owner "
                "transaction"
            )

    @model_serializer(mode="plain")
    def _serialize_for_transport(self, info: SerializationInfo) -> WireDict:
        """Pydantic/FastAPI default boundary: logical plaintext + reactive fields."""
        return self._export_wire(self._export_context(info.context))

    def model_dump(
        self,
        *,
        context: ExportContext | dict[str, object] | None = None,
        **kwargs: object,
    ) -> WireDict:  # type: ignore[override]
        """导出 FastAPI / 前端响应；默认解密并携带响应式字段。"""
        del kwargs
        return self._export_wire(self._export_context(context))

    async def to_dict(
        self,
        *,
        if_decrypt: bool = False,
        include_reactive: bool = False,
        include_staged: bool = False,
    ) -> WireDict:
        """已激活节点导出 / 落盘。

        校验 ``ACTIVE`` 与未软删；默认密文、不携带响应式字段。
        """
        ctx = ExportContext(
            if_decrypt=if_decrypt,
            include_reactive=include_reactive,
            include_staged=include_staged,
        )
        self._assert_staged_export_owner(ctx)
        source = self.effective if include_staged else self
        if source._activation_state != NodeState.ACTIVE:
            raise ValueError("to_dict 仅用于已激活节点")
        if source._deleted:
            raise DeletedNodeError(self.uid)
        return self._export_wire(ctx)


from .signals import (
    AfterCommitObserverReport,
    ConfigEvent,
    SignalCallback,
    WrappedSignal,
    _dispatch_observers,
    _dispatch_validators,
    _receiver_label,
    _wrap,
)  # noqa: E402
