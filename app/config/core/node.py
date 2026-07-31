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
import inspect
from collections.abc import Awaitable, Callable
from enum import Enum
from pathlib import Path
from typing import ClassVar, Iterator, Self, cast
from uuid import UUID, uuid4

from blinker import ANY, Signal
from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..errors import ConfigAggregateError, DeletedNodeError
from .manager import config_manager
from .staging import StagedOp
from app.utils.io import read_toml
from ..wire import ExportContext, WireDict

# weakref.ref(parent) 的可调用引用；None 表示根节点
ParentRef = Callable[[], "ConfigNode | None"]


class NodeState(str, Enum):
    """节点激活状态。

    - ``INACTIVE``：未激活（``model_validate`` / 构造后）
    - ``INITIALIZING``：初始化中（``activate()`` 的 ``_activate_from_payload`` 阶段）
    - ``ACTIVE``：已激活（``activate()`` 完成后）
    """

    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"


class _SignalDescriptor:
    """``connect`` / ``disconnect`` 的混合描述符：类访问 → 类级；实例访问 → 发送者=实例。"""

    def __init__(self, *, is_disconnect: bool) -> None:
        self._is_disconnect = is_disconnect

    def __get__(self, obj: "ConfigNode | None", owner: type["ConfigNode"]) -> Callable[
        ...,
        "SignalCallback | Callable[[SignalCallback], SignalCallback]",
    ]:
        is_disconnect = self._is_disconnect

        def caller(
            receiver: SignalCallback | None = None,
            *,
            phase: str = "runtime",
            kind: str | None = None,
            group: str | None = None,
            field: str | None = None,
        ) -> SignalCallback | Callable[[SignalCallback], SignalCallback]:
            from .collection import ConfigCollection

            if issubclass(owner, ConfigCollection) and (
                group is not None or field is not None
            ):
                raise TypeError("Collection 信号不支持 group/field 过滤")
            sender = obj  # 类访问时为 None

            def register(fn: SignalCallback) -> SignalCallback:
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
    _signal_workspace: ClassVar[Signal | None] = None

    # ── 运行时私有状态 ──
    _uid: UUID = PrivateAttr(default_factory=uuid4)
    _parent_ref: ParentRef | None = PrivateAttr(default=None)
    _activation_state: NodeState = PrivateAttr(default=NodeState.INACTIVE)
    _deleted: bool = PrivateAttr(default=False)
    _is_locked: bool = PrivateAttr(default=False)
    _workspace: "ConfigNode | None" = PrivateAttr(default=None)
    _pending_wire: WireDict | None = PrivateAttr(default=None)
    _is_workspace: bool = PrivateAttr(default=False)
    _staged_ops: list[StagedOp] = PrivateAttr(default_factory=list)
    # 其它 Task 在本节点 commit 持锁期间的 stage；外层释放锁时并入 _staged_ops
    _staged_pending: list[StagedOp] = PrivateAttr(default_factory=list)
    _commit_lock: asyncio.Lock | None = PrivateAttr(default=None)
    # ──────────────── 子类信号隔离 ────────────────

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        # 每个具体子类拥有独立 Signal（Collection 子类共享 ConfigCollection.signal 亦可）
        cls.signal = Signal()
        cls._signal_workspace = None

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
        """仅持久化根节点有路径；嵌套子节点激活不得误读根文件。"""
        if self.parent is not None:
            return None
        return config_manager.get_file(self)

    # ── 暂存 / 提交：stage 仅记录 op 队列；生效修改只在事务 ws（effective）内 ──

    def _stage(self, op: StagedOp) -> None:
        """记录待提交的操作。

        本 Task 已在该节点 ``commit`` 中（含嵌套）→ 入 ``_staged_ops``。
        其它 Task 正逢本节点持锁 → 入 ``_staged_pending``，外层释放后再并入。
        """
        if self.deleted:
            raise DeletedNodeError(self.uid)
        if self.is_locked:
            raise ValueError("配置已锁定, 无法修改")
        lock = self._commit_lock
        if (
            lock is not None
            and lock.locked()
            and not config_manager.in_node_commit(self)
        ):
            self._staged_pending.append(op)
            return
        self._staged_ops.append(op)

    async def commit(self) -> None:
        """按序提交暂存 op；收集全部失败后 ``raise ConfigAggregateError``。

        经 ``manager.node_commit``：外层持锁，同 Task 嵌套空过；其它 Task 等待。
        持锁期间其它 Task 的 ``_stage`` 进 pending，外层释放时并入。
        入口快照并清空 ``_staged_ops``；``while`` 排空本批；Cancel 时归还未执行记录。
        """
        async with config_manager.node_commit(self):
            if not self._staged_ops:
                return
            if self.deleted:
                raise DeletedNodeError(self.uid)
            if self.is_locked:
                raise ValueError("配置已锁定, 无法修改")

            batch = list(self._staged_ops)
            self._staged_ops.clear()
            errors: list[Exception] = []
            try:
                while batch:
                    op = batch.pop(0)
                    try:
                        await self._commit_op(op)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)
                        self._staged_ops.clear()
                    except BaseException:
                        batch.insert(0, op)
                        raise
                if errors:
                    raise ConfigAggregateError(errors)
            except BaseException:
                if batch:
                    self._staged_ops.extend(batch)
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
        """信号读入口：事务内见信号工作区，否则 ``cls.signal``。"""
        ws = cls._signal_workspace
        if config_manager.in_transaction and ws is not None:
            return ws
        return cls.signal

    @classmethod
    def _build_signal_workspace(cls) -> None:
        if not config_manager.in_transaction:
            return
        if cls._signal_workspace is not None:
            return
        cls._signal_workspace = copy.deepcopy(cls.signal)
        config_manager._register_workspace(cls)

    @classmethod
    def _COMMIT_signal(cls) -> None:
        ws = cls._signal_workspace
        if ws is None:
            return
        cls.signal = ws
        cls._signal_workspace = None

    @classmethod
    def _ROLLBACK_signal(cls) -> None:
        cls._signal_workspace = None

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

    async def activate(self) -> None:
        """未激活 → 已激活；热化尽量落地，聚合错误在事务提交后上抛。

        外层事务：成功字段/成员写入 ws；结束时标 ``ACTIVE`` 并清 ws 上 pending。
        若本次为外层事务则 ``COMMIT`` 后实例可用；聚合错误再抛给调用方处理。
        若嵌套在父事务中，父 ``ROLLBACK`` 时本节点随 ws 回到 ``INACTIVE``，live pending 仍保留。
        """
        if self.activation_state != NodeState.INACTIVE:
            raise ValueError("不可重复 activate")
        if self._pending_wire is not None:
            payload = self._pending_wire
        elif self.persist_path is not None:
            payload = read_toml(self.persist_path)
        else:
            payload = self._export_wire(
                ExportContext(if_decrypt=True, include_reactive=False)
            )
        activate_error: ConfigAggregateError | None = None
        async with config_manager.transaction():
            self._build_workspace()
            self.effective._activation_state = NodeState.INITIALIZING
            try:
                await self._activate_from_payload(payload or {})
            except ConfigAggregateError as exc:
                activate_error = exc
            self.effective._activation_state = NodeState.ACTIVE
            self.effective._pending_wire = None
        if activate_error is not None:
            raise activate_error

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
        self.effective._deleted = True
        for child in self.iter_children():
            await child._delete()

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

    def model_dump(self, *, context: ExportContext | dict[str, object] | None = None, **kwargs: object) -> WireDict:  # type: ignore[override]
        """FastAPI / 冷态响应导出。

        默认：明文（``if_decrypt=True``）、携带响应式字段；读已提交 ``self``。
        """
        if isinstance(context, ExportContext):
            ctx = context
        elif isinstance(context, dict):
            ctx = ExportContext(
                if_decrypt=bool(context.get("if_decrypt", True)),
                include_reactive=bool(context.get("include_reactive", True)),
            )
        else:
            ctx = ExportContext(if_decrypt=True, include_reactive=True)
        return self._export_wire(ctx)

    async def to_dict(
        self,
        *,
        if_decrypt: bool = False,
        include_reactive: bool = False,
    ) -> WireDict:
        """已激活节点导出 / 落盘。

        校验 ``ACTIVE`` 与未软删；默认密文、不携带响应式字段。
        """
        if self.activation_state != NodeState.ACTIVE:
            raise ValueError("to_dict 仅用于已激活节点")
        if self.deleted:
            raise DeletedNodeError(self.uid)
        ctx = ExportContext(
            if_decrypt=if_decrypt,
            include_reactive=include_reactive,
        )
        return self._export_wire(ctx)


from ..signals import ConfigEvent, SignalCallback, WrappedSignal  # noqa: E402
