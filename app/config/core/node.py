"""统一基类 ``ConfigNode``：Entry / Collection 共享生命周期、工作区、信号、守卫。

``ConfigNode`` 继承 ``BaseModel``（文档 schema），其上叠加：

- 运行时私有状态（uid / parent / activation_state / deleted / locked / workspace）
- 按事务边界持有工作区：读 ``effective`` / 写 ``_build_workspace``
- blinker 信号：``connect`` / ``disconnect`` / ``send``
- 生命周期：``activate`` / ``delete`` / ``lock_s`` / ``lock_x`` / ``unlock`` / ``to_dict``
"""

from __future__ import annotations

import asyncio
import inspect
import weakref
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, Self, cast, overload
from uuid import UUID, uuid4

from blinker import ANY, Signal
from blinker.base import ANY_ID
from pydantic import BaseModel, ConfigDict, PrivateAttr

from app.utils.io import read_dict_file

from ..errors import ConfigAggregateError, DeletedNodeError
from .manager import (
    ExecutionOwner,
    TransactionContext,
    add_x_token,
    config_manager,
    discard_x_token,
    execution_owner,
    x_tokens,
)
from .staging import StagedOp

# weakref.ref(parent) 的可调用引用；None 表示根节点
ParentRef = Callable[[], "ConfigNode | None"]


@dataclass
class ExportContext:
    """``model_dump`` 序列化上下文：按受众控制解密、响应式字段与 UI 显隐。

    经 pydantic ``context=`` 传入；``encrypted()`` 等 field serializer 读取本对象。
    ``mode="python"`` 导出与 audience **正交**（serializer 不做 audience/UI 裁剪）。
    """

    audience: Literal["api", "persist", "export"] = "api"
    """api：明文、含响应式、尊重 UI；persist：密文完整文档；export：明文完整文档。"""

    @classmethod
    def from_dump(cls, context: object | None) -> ExportContext:
        """从 ``model_dump(context=…)`` 归一化；无 context 时默认 ``audience=api``。"""
        if isinstance(context, ExportContext):
            return context
        if isinstance(context, dict):
            raw = context.get("audience", "api")
            if raw not in ("api", "persist", "export"):
                raw = "api"
            return cls(audience=raw)
        return cls(audience="api")


class NodeState(str, Enum):
    """节点激活状态。

    - ``INACTIVE``：未激活（``model_validate`` / 构造后）
    - ``INITIALIZING``：初始化中（``activate()`` 的 ``_activate_from_payload`` 阶段）
    - ``ACTIVE``：已激活（``activate()`` 完成后）
    """

    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"


@dataclass
class _ActivationState:
    """一次递归激活共用的标记，与各节点自己的 NodeState 分开。"""

    fast_init: bool = False
    active: bool = True
    transaction: weakref.ReferenceType[TransactionContext] | None = None

    @property
    def pending(self) -> bool:
        transaction = self.transaction() if self.transaction is not None else None
        return self.active or (transaction is not None and transaction.active)


@dataclass(frozen=True)
class LockTicket:
    """业务锁凭证；``unlock`` 须原票且在 ``issuer`` 节点调用。"""

    mode: Literal["s", "x"]
    token: UUID
    issuer: UUID
    cascade: bool = True


class _SignalAccessor(Protocol):
    """``connect`` / ``disconnect`` 的访问签名。

    两种调用（按是否传入 ``receiver`` 区分）：

    - 直接订阅 ``connect(receiver, …)`` → 返回 ``SignalCallback``
    - 装饰器 ``@connect(phase=…)`` → 返回装饰器 ``Callable[[SignalCallback], SignalCallback]``
    """

    @overload
    def __call__(
        self,
        receiver: "SignalCallback",
        *,
        phase: str = "runtime",
        kind: str | None = None,
        group: str | None = None,
        field: str | None = None,
    ) -> "SignalCallback": ...

    @overload
    def __call__(
        self,
        receiver: None = None,
        *,
        phase: str = "runtime",
        kind: str | None = None,
        group: str | None = None,
        field: str | None = None,
    ) -> "Callable[[SignalCallback], SignalCallback]": ...


class _SignalDescriptor:
    """``connect`` / ``disconnect`` 的混合描述符：类访问 → 类级；实例访问 → 发送者=实例。"""

    def __init__(self, *, is_disconnect: bool) -> None:
        self._is_disconnect = is_disconnect

    def __get__(
        self, obj: "ConfigNode | None", owner: type["ConfigNode"]
    ) -> _SignalAccessor:
        is_disconnect = self._is_disconnect

        @overload
        def caller(
            receiver: "SignalCallback",
            *,
            phase: str = "runtime",
            kind: str | None = None,
            group: str | None = None,
            field: str | None = None,
        ) -> "SignalCallback": ...

        @overload
        def caller(
            receiver: None = None,
            *,
            phase: str = "runtime",
            kind: str | None = None,
            group: str | None = None,
            field: str | None = None,
        ) -> "Callable[[SignalCallback], SignalCallback]": ...

        def caller(
            receiver: "SignalCallback | None" = None,
            *,
            phase: str = "runtime",
            kind: str | None = None,
            group: str | None = None,
            field: str | None = None,
        ) -> "SignalCallback | Callable[[SignalCallback], SignalCallback]":
            from .collection import ConfigCollection

            if issubclass(owner, ConfigCollection) and (
                group is not None or field is not None
            ):
                raise TypeError("Collection 信号不支持 group/field 过滤")
            sender = obj  # 类访问时为 None

            def register(fn: SignalCallback) -> SignalCallback:
                if sender is not None:
                    sender._require_lifecycle_access()
                if is_disconnect:
                    owner._disconnect_impl(
                        fn,
                        phase=phase,
                        kind=kind,
                        group=group,
                        field=field,
                        sender=sender,
                    )
                else:
                    owner._connect_impl(
                        fn,
                        phase=phase,
                        kind=kind,
                        group=group,
                        field=field,
                        sender=sender,
                    )
                return fn

            if receiver is None:
                return register
            return register(receiver)

        return caller


def _wrap(
    receiver: SignalCallback,
    phase: str,
    kind: str | None,
    group: str | None,
    field: str | None,
) -> WrappedSignal:
    """包装用户 receiver：订阅过滤 + 有条件 deleted 守卫。

    包装函数为 **同步**（blinker 不接受协程函数作为接收者）；若 ``receiver``
    返回 awaitable，则原样返回，由 ``send`` 内统一 ``await``。

    ``kind``：精确匹配 ``event.kind``，或 ``kind="add"`` 同时匹配 ``init_add``
    （再由 ``phase`` 区分 init / runtime）。
    """

    def wrapper(
        sender: object,
        event: object,
        *args: object,
        **kwargs: object,
    ) -> object | Awaitable[object] | None:
        inst = getattr(receiver, "__self__", None)
        if isinstance(inst, ConfigNode) and inst.deleted:
            return None
        event_kind = getattr(event, "kind", "")
        is_init = isinstance(event_kind, str) and event_kind.startswith("init_")
        if phase == "init" and not is_init:
            return None
        if phase == "runtime" and is_init:
            return None
        if kind is not None and event_kind != kind and event_kind != f"init_{kind}":
            return None
        if group is not None and getattr(event, "group", None) != group:
            return None
        if field is not None and getattr(event, "field", None) != field:
            return None
        return receiver(sender, event, *args, **kwargs)

    return wrapper


async def _dispatch(
    signal: Signal, sender: ConfigNode | None, event: ConfigEvent
) -> None:
    """派发信号：blinker 同步 invoke 各 wrapper；返回的 awaitable 逐个 await。"""
    for _receiver, result in signal.send(sender, event=event):
        if inspect.isawaitable(result):
            await result


class ConfigNode(BaseModel):
    """Entry / Collection 统一基类。"""

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
        ignored_types=(_SignalDescriptor,),
    )

    signal: ClassVar[Signal] = Signal()
    _signal_workspace: ClassVar[dict[UUID, Signal]] = {}

    # ── 运行时私有状态 ──
    _uid: UUID = PrivateAttr(default_factory=uuid4)
    _parent_ref: ParentRef | None = PrivateAttr(default=None)
    _activation_state: NodeState = PrivateAttr(default=NodeState.INACTIVE)
    _activation: _ActivationState | None = PrivateAttr(default=None)
    _workspace: dict[UUID, ConfigNode] = PrivateAttr(default_factory=dict)
    _deleted: bool = PrivateAttr(default=False)
    _lock_s: set[UUID] = PrivateAttr(default_factory=set)
    _lock_x: UUID | None = PrivateAttr(default=None)
    _pending_payload: dict[str, Any] | None = PrivateAttr(default=None)
    _is_workspace: bool = PrivateAttr(default=False)
    # Task / Thread 为弱键；作用域只存标识，不把已结束事务或任务强引用进队列。
    _staged_by_owner: weakref.WeakKeyDictionary[
        ExecutionOwner, dict[UUID | None, list[StagedOp]]
    ] = PrivateAttr(default_factory=weakref.WeakKeyDictionary)
    _commit_lock: asyncio.Lock | None = PrivateAttr(default=None)
    # ──────────────── 子类信号隔离 ────────────────

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        # 每个具体子类拥有独立 Signal（Collection 子类共享 ConfigCollection.signal 亦可）
        cls.signal = Signal()
        cls._signal_workspace = {}

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
    def _activation_ready(self) -> bool:
        return self.activation_state == NodeState.ACTIVE and (
            self._activation is None or not self._activation.pending
        )

    def _require_write_access(self) -> None:
        """统一检查受管写入；初始化赋值与入口结束后的关联写入仍可执行。"""
        activation = self._activation
        if activation is not None and activation.pending:
            ctx = config_manager.current
            if (
                ctx is None
                or activation.transaction is None
                or activation.transaction() is not ctx.root
            ):
                raise ValueError("配置仍在激活，其他执行者不能修改")
        if self.activation_state != NodeState.ACTIVE:
            return
        if activation is not None and activation.active:
            raise ValueError("所属激活流程尚未完成，不能执行热态修改")
        if self.deleted:
            raise DeletedNodeError(self.uid)
        # S 锁拒写，X 锁仅允许持票上下文写入；锁状态仍挂在 live 上。
        if self.is_locked and self._lock_x not in x_tokens():
            raise ValueError("配置已锁定, 无法修改")

    def _require_lifecycle_access(self) -> None:
        """声明可在冷态建立；激活尚未发布时禁止修改非字段生命周期状态。"""
        if self._activation is not None and self._activation.pending:
            raise ValueError("激活期间不能修改生命周期状态")

    @property
    def deleted(self) -> bool:
        """读经 ``effective``：事务内见工作区软删标记。"""
        return self.effective._deleted

    @property
    def is_locked(self) -> bool:
        """派生：任一 S 或 X 持有即为真（不经工作区；仅已激活后有意义）。"""
        return bool(self._lock_s) or self._lock_x is not None

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
        """仅持久化根节点有路径；嵌套子节点激活不得误读根文件。"""
        if self.parent is not None:
            return None
        return config_manager.get_file(self)

    # ── 暂存 / 提交：stage 仅记录 op 队列；生效修改只在事务 ws（effective）内 ──

    def _stage_queue(
        self, scope: UUID | None, *, create: bool = False
    ) -> list[StagedOp]:
        """暂存只属于实际提交者及其作用域，不沿 ContextVar 继承给子任务。"""
        owner = execution_owner()
        queues = self._staged_by_owner.get(owner)
        if queues is None:
            if not create:
                return []
            queues = {}
            self._staged_by_owner[owner] = queues
            if isinstance(owner, asyncio.Task):
                node_ref = weakref.ref(self)

                def cleanup(done: asyncio.Task[Any]) -> None:
                    node = node_ref()
                    if node is not None:
                        node._staged_by_owner.pop(done, None)

                owner.add_done_callback(cleanup)
        if create:
            return queues.setdefault(scope, [])
        return queues.get(scope, [])

    def _discard_stage_scope(self, scope: UUID) -> None:
        queues = self._staged_by_owner.get(execution_owner())
        if queues is not None:
            queues.pop(scope, None)

    def _current_staged(self) -> list[StagedOp]:
        return self._stage_queue(config_manager.staging_scope)

    def _stage(self, op: StagedOp) -> None:
        """热态写只登记申请；工作区应用、校验及信号在 commit 的事务内执行。"""
        self._require_write_access()
        self._stage_queue(config_manager.staging_scope, create=True).append(op)
        config_manager._register_staged(self)

    async def commit(self) -> None:
        """按序提交暂存 op；收集全部失败后 ``raise ConfigAggregateError``。

        manager 先取得全局入口再取节点锁；同 Task 嵌套复用入口及事务。
        只快照并清空当前执行者、当前作用域的暂存；默认逐 op，共享边界内复用。
        Cancel 时归还当前已回滚及尚未执行的记录，不自动重试业务修改。
        """
        queue = self._current_staged()
        if not queue:
            queues = self._staged_by_owner.get(execution_owner(), {})
            if any(queues.values()):
                raise RuntimeError(
                    "存在其它作用域的暂存，请在同一作用域内赋值并 commit"
                )
            return
        # 在等待入口前拒绝非法初始化写入；空提交不需要写权限。
        self._require_write_access()
        reentrant_init = (
            self.activation_state == NodeState.INITIALIZING
            and config_manager.in_node_commit(self)
        )
        async with config_manager.node_commit(self):
            if reentrant_init:
                raise RuntimeError("禁止同节点重复开启 init 事务")
            # 等待入口期间锁和删除状态可能变化，取得入口后再复核。
            if self.deleted:
                raise DeletedNodeError(self.uid)
            if self.is_locked and self._lock_x not in x_tokens():
                raise ValueError("配置已锁定, 无法修改")

            batch = list(queue)
            queue.clear()
            errors: list[Exception] = []
            try:
                while batch:
                    op = batch.pop(0)
                    try:
                        await self._commit_op(op)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)
                        self._current_staged().clear()
                    except BaseException:
                        batch.insert(0, op)
                        raise
                if errors:
                    raise ConfigAggregateError(errors)
            except BaseException:
                if batch:
                    queue.extend(batch)
                raise

    async def _commit_op(self, op: StagedOp) -> None:
        raise NotImplementedError(op.kind.value)

    # ──────────────── 工作区 API ────────────────

    @property
    def effective(self) -> Self:
        """读取本节点在当前事务或父事务中的工作区，其他执行者读 live。"""
        ctx = config_manager.current
        workspaces: dict[UUID, ConfigNode] = cast(
            "dict[str, Any]", self.__pydantic_private__
        )["_workspace"]
        while ctx is not None:
            workspace = workspaces.get(ctx.scope_id)
            if workspace is not None:
                return cast(Self, workspace)
            ctx = ctx.parent
        return self

    def _build_workspace(self) -> None:
        ctx = config_manager.current
        if ctx is None:
            return
        if self._is_workspace:
            raise RuntimeError("工作区不可再次创建工作区")
        if self._deleted:
            raise DeletedNodeError(self.uid)
        workspaces: dict[UUID, ConfigNode] = cast(
            "dict[str, Any]", self.__pydantic_private__
        )["_workspace"]
        if ctx.scope_id not in workspaces:
            workspaces[ctx.scope_id] = self._make_workspace_shell(self.effective)
            config_manager._register_workspace(self)

    def _make_workspace_shell(self, source: ConfigNode) -> ConfigNode:
        raise NotImplementedError

    def _COMMIT(self, ctx: TransactionContext) -> None:
        raise NotImplementedError

    def _ROLLBACK(self, ctx: TransactionContext) -> None:
        self._workspace.pop(ctx.scope_id, None)
        if self._activation_state == NodeState.INACTIVE:
            parent = self.effective
            self._activation = parent._activation if parent is not self else None

    @classmethod
    def signal_effective(cls) -> Signal:
        ctx = config_manager.current
        while ctx is not None:
            workspace = cls._signal_workspace.get(ctx.scope_id)
            if workspace is not None:
                return workspace
            ctx = ctx.parent
        return cls.signal

    @classmethod
    def _build_signal_workspace(cls) -> None:
        ctx = config_manager.current
        if ctx is None or ctx.scope_id in cls._signal_workspace:
            return
        source = cls.signal_effective()
        workspace = Signal()
        workspace.is_muted = source.is_muted
        # Blinker 没有公开的完整订阅枚举接口；这里自行读取接收者、发送者及
        # 关联索引，枚举有效订阅，再用 connect 重建独立索引与弱引用清理。
        # 先快照发送者弱引用，避免 GC 清理后把已失效发送者误认为非弱引用发送者。
        senders = source._weak_senders.copy()
        receivers = source.receivers.copy()
        routes = source._by_sender.copy()
        for sender_id, receiver_ids in routes.items():
            if sender_id == ANY_ID:
                sender = ANY
            elif sender_id in senders:
                sender = senders[sender_id]()
                if sender is None:
                    continue
            elif isinstance(sender_id, (str, int)):
                # 不可弱引用的发送者只留下标识；str/int 标识可重建等价路由，
                # 实际发送时，回调收到的仍是 send 传入的原发送者。
                sender = sender_id
            else:
                raise TypeError("无法从信号索引还原发送者，不能完整建立信号工作区")
            for receiver_id in receiver_ids.copy():
                stored = receivers.get(receiver_id)
                weak = isinstance(stored, weakref.ref)
                receiver = stored() if isinstance(stored, weakref.ref) else stored
                if receiver is not None:
                    workspace.connect(receiver, sender=sender, weak=weak)
        cls._signal_workspace[ctx.scope_id] = workspace
        config_manager._register_workspace(cls)

    @classmethod
    def _COMMIT_signal(cls, ctx: TransactionContext) -> None:
        workspace = cls._signal_workspace.pop(ctx.scope_id, None)
        if workspace is not None:
            if ctx.parent is None:
                cls.signal = workspace
            else:
                cls._signal_workspace[ctx.parent.scope_id] = workspace

    @classmethod
    def _ROLLBACK_signal(cls, ctx: TransactionContext) -> None:
        cls._signal_workspace.pop(ctx.scope_id, None)

    # ──────────────── 信号 ────────────────

    connect = _SignalDescriptor(is_disconnect=False)
    disconnect = _SignalDescriptor(is_disconnect=True)

    @classmethod
    def _connect_impl(
        cls,
        receiver: SignalCallback,
        *,
        phase: str,
        kind: str | None,
        group: str | None,
        field: str | None,
        sender: "ConfigNode | None",
        weak: bool = True,
    ) -> WrappedSignal:
        with config_manager._execution_gate_sync():
            if config_manager.in_transaction:
                cls._build_signal_workspace()
            sig = cls.signal_effective()
            key = (
                phase,
                kind,
                group,
                field,
                id(sender) if sender is not None else None,
            )
            probe = sender if sender is not None else ANY
            wrapped: WrappedSignal | None = None
            try:
                raw_store = getattr(receiver, "__signal_wrappers__", None)
                if raw_store is None:
                    store: dict[
                        tuple[str, str | None, str | None, str | None, int | None],
                        WrappedSignal,
                    ] = {}
                    setattr(receiver, "__signal_wrappers__", store)
                else:
                    store = cast(
                        dict[
                            tuple[str, str | None, str | None, str | None, int | None],
                            WrappedSignal,
                        ],
                        raw_store,
                    )
                existing = store.get(key)
                if existing is not None:
                    if existing in sig.receivers_for(probe):
                        raise ValueError(
                            "重复订阅同一 (phase, kind, group, field, sender)；"
                            "请先 disconnect"
                        )
                    wrapped = existing  # 复用挂载点（wrappers 只增不减）
                else:
                    wrapped = _wrap(receiver, phase, kind, group, field)
                    store[key] = wrapped
            except (AttributeError, TypeError):
                # 不可附属性需要以强引用订阅信号, 避免被垃圾回收
                if weak:
                    raise TypeError("receiver 不可附属性，无法以弱引用注册信号")
                wrapped = _wrap(receiver, phase, kind, group, field)
            assert wrapped is not None
            sig.connect(wrapped, sender=probe, weak=weak)
            return wrapped

    @classmethod
    def _disconnect_impl(
        cls,
        receiver: SignalCallback,
        *,
        phase: str,
        kind: str | None,
        group: str | None,
        field: str | None,
        sender: "ConfigNode | None",
    ) -> None:
        with config_manager._execution_gate_sync():
            if config_manager.in_transaction:
                cls._build_signal_workspace()
            sig = cls.signal_effective()
            store = getattr(receiver, "__signal_wrappers__", None)
            if not store:
                return
            key = (
                phase,
                kind,
                group,
                field,
                id(sender) if sender is not None else None,
            )
            # wrappers 只作包装挂载点（防 GC），只增不减；解订仅动 blinker
            wrapped = store.get(key)
            if wrapped is None:
                return
            if sender is not None:
                sig.disconnect(wrapped, sender=sender)
            else:
                sig.disconnect(wrapped)

    @classmethod
    async def send(cls, *, sender: "ConfigNode | None", event: ConfigEvent) -> None:
        if sender is not None and sender.deleted:
            return
        await _dispatch(cls.signal_effective(), sender, event)

    # ──────────────── 生命周期 ────────────────

    async def activate(
        self,
        *,
        regenerate_uuids: bool = False,
        fast_init: bool = False,
    ) -> None:
        """复用构造时关联的激活标记；没有进行中的标记时创建一次。

        可选地在整个字段循环外建立一次事务边界；失败先回退，再逐字段执行。
        Init 信号保持即时，失败尝试与原流程可能重复调用接收者或第三方服务。
        """
        self._require_write_access()
        async with config_manager.execution_gate():
            if self.activation_state != NodeState.INACTIVE:
                raise ValueError("不可重复 activate")
            activation = self._activation
            owns_activation = activation is None or not activation.active
            previous: list[tuple[ConfigNode, _ActivationState | None]] = []
            activate_error: ConfigAggregateError | None = None
            try:
                async with config_manager.transaction():
                    ctx = config_manager.current
                    assert ctx is not None
                    if owns_activation:
                        activation = _ActivationState(
                            fast_init=fast_init, transaction=weakref.ref(ctx.root)
                        )
                    # 已构造但尚未轮到 activate 的子节点也属于本次激活。
                    nodes: list[ConfigNode] = [self]
                    for node in nodes:
                        if node._activation is not activation:
                            previous.append((node, node._activation))
                            node._activation = activation
                        nodes.extend(node.iter_children())
                    if self._pending_payload is not None:
                        payload: dict[str, Any] = self._pending_payload
                    elif self.persist_path is not None:
                        payload = read_dict_file(self.persist_path, allow_empty=True)
                    else:
                        payload = self.model_dump(
                            mode="json", context=ExportContext(audience="persist")
                        )
                    self._build_workspace()
                    self.effective._activation = activation
                    self.effective._activation_state = NodeState.INITIALIZING
                    try:
                        await self._activate_from_payload(
                            payload, regenerate_uuids=regenerate_uuids
                        )
                    except ConfigAggregateError as exc:
                        activate_error = exc
                    self.effective._activation_state = NodeState.ACTIVE
                    self.effective._pending_payload = None
            finally:
                if owns_activation and activation is not None:
                    activation.active = False
                if self.activation_state == NodeState.INACTIVE:
                    for node, old in previous:
                        node._activation = old
            if activate_error is not None:
                raise activate_error

    async def _activate_from_payload(
        self, payload: dict[str, Any], *, regenerate_uuids: bool = False
    ) -> None:
        raise NotImplementedError

    async def _delete(self) -> None:
        """内部软删；外部请用 Collection.remove / 框架生命周期，勿直接调用。"""
        if config_manager.is_registered_collection(self):
            raise RuntimeError("已登记 name 的 Collection 不可 delete")
        assert config_manager.in_transaction, "_delete 须在事务内"
        self._build_workspace()
        if self.deleted:
            raise DeletedNodeError(self.uid)
        # 先递归子节点再给自己打标记：Collection.iter_children 经 values()/__getitem__
        # 取成员，而后者对已软删的集合直接上抛 DeletedNodeError。先打标记的话，带
        # 非空嵌套集合的 Entry（ScriptEntry.users / GameEntry.devices）连自己的成员
        # 都枚举不出来，remove 与 remove_type 的级联会整笔 commit 失败。
        for child in self.iter_children():
            await child._delete()
        self.effective._deleted = True

    async def lock_s(self, *, cascade: bool = True) -> LockTicket:
        """共享锁：可叠加；禁一切热写；与 X 互斥。

        仅已激活节点可取锁。``cascade=True``（默认）覆盖全部子节点；
        ``False`` 只锁本节点。
        """
        nodes: list[ConfigNode] = [self]
        if cascade:
            for node in nodes:
                nodes.extend(node.iter_children())
        # 完整预检后再登记；期间不让出执行，冲突时不留下部分锁。
        if any(not node._activation_ready for node in nodes):
            raise ValueError("配置尚未完成激活，无法加锁")
        if any(node._lock_x is not None for node in nodes):
            raise ValueError("已有 X 锁，无法加 S")
        token = uuid4()
        for node in nodes:
            node._lock_s.add(token)
        return LockTicket(mode="s", token=token, issuer=self.uid, cascade=cascade)

    async def lock_x(self, *, cascade: bool = True) -> LockTicket:
        """独占锁：至多一个；与任一 S 互斥。

        持票上下文可写本锁覆盖的节点（``_stage`` / ``commit`` 认 token）；
        其它上下文与 S 持有者仍禁写。仅已激活节点可取锁；``cascade`` 同 ``lock_s``。
        """
        nodes: list[ConfigNode] = [self]
        if cascade:
            for node in nodes:
                nodes.extend(node.iter_children())
        # 预检和登记复用同一覆盖范围，不能覆盖后代已有的票据。
        if any(not node._activation_ready for node in nodes):
            raise ValueError("配置尚未完成激活，无法加锁")
        if any(node._lock_x is not None or node._lock_s for node in nodes):
            raise ValueError("已有锁，无法加 X")
        token = uuid4()
        for node in nodes:
            node._lock_x = token
        add_x_token(token)
        return LockTicket(mode="x", token=token, issuer=self.uid, cascade=cascade)

    async def try_lock_x(self, *, cascade: bool = True) -> LockTicket | None:
        """非阻塞取 X；冲突返回 ``None``，成功返回票据（语义同 ``lock_x``）。"""
        if self._lock_x is not None or self._lock_s:
            return None
        try:
            return await self.lock_x(cascade=cascade)
        except ValueError:
            return None

    async def unlock(self, ticket: LockTicket) -> None:
        """凭原凭证解锁；须在 ``ticket.issuer`` 节点调用。"""
        self._require_lifecycle_access()
        if ticket.issuer != self.uid:
            raise ValueError("须在签发节点解锁")
        if ticket.mode == "s":
            if ticket.token not in self._lock_s:
                raise ValueError("无效或未持有的 S 锁凭证")

            def unregister(node: ConfigNode) -> None:
                node._lock_s.discard(ticket.token)
                if not ticket.cascade:
                    return
                for child in node.iter_children():
                    unregister(child)

            unregister(self)
            return
        if ticket.mode == "x":
            if self._lock_x != ticket.token:
                raise ValueError("无效或未持有的 X 锁凭证")

            def unregister(node: ConfigNode) -> None:
                # 树结构可能已变化，只释放本票据登记的锁。
                if node._lock_x == ticket.token:
                    node._lock_x = None
                if not ticket.cascade:
                    return
                for child in node.iter_children():
                    unregister(child)

            unregister(self)
            # 差集移除：跨上下文 unlock 合法，勿用 ContextVar.reset
            discard_x_token(ticket.token)
            return
        raise ValueError(f"未知锁模式: {ticket.mode!r}")

    def iter_children(self) -> Iterator["ConfigNode"]:
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    # ──────────────── 导出（pydantic model_dump / model_serializer）────────────────

    def model_dump(
        self,
        *,
        mode: Literal["json", "python"] | str = "json",
        include: Any = None,
        exclude: Any = None,
        context: ExportContext | dict[str, object] | None = None,
        by_alias: bool | None = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: bool | Literal["none", "warn", "error"] = True,
        serialize_as_any: bool = False,
        fallback: Any = None,
    ) -> dict[str, Any]:
        """导出配置文档：默认 ``mode=json``；经子类 ``@model_serializer`` 定形。

        无 ``context`` 时默认 ``audience=api``（FastAPI / 冷态响应）。
        落盘请用 ``to_dict`` 或显式 ``ExportContext(audience="persist")``。
        """
        ctx = ExportContext.from_dump(context)
        return super().model_dump(
            mode=mode,
            include=include,
            exclude=exclude,
            context=ctx,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            round_trip=round_trip,
            warnings=warnings,
            serialize_as_any=serialize_as_any,
            fallback=fallback,
        )

    async def to_dict(self) -> dict[str, Any]:
        """已激活节点导出 / 落盘。

        校验 ``ACTIVE`` 与未软删；固定 ``audience=persist``（密文、无响应式）。
        """
        if not self._activation_ready:
            raise ValueError("to_dict 仅用于已激活节点")
        if self.deleted:
            raise DeletedNodeError(self.uid)
        return self.model_dump(
            mode="json",
            context=ExportContext(audience="persist"),
        )


from ..signals import ConfigEvent, SignalCallback, WrappedSignal  # noqa: E402
