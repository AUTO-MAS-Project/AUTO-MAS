"""ConfigManager：ref 池、持久化根、事务 / 工作区、防抖落盘与明文导出。"""

from __future__ import annotations

import asyncio
import os
import threading
import weakref
from collections import deque
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, AsyncGenerator, Generator, Literal
from uuid import UUID, uuid4

from blinker import ANY

from app.utils.io import write_file
from app.utils.logger import get_logger

from ..errors import ConfigAggregateError, ConfigPersistenceError

logger = get_logger("配置持久化")

# 当前 asyncio 上下文持有的 X 锁 token。判定用差集而非 Token.reset：
# 收尾兜底可能在另一个上下文里 unlock，reset 会抛 LookupError。
_x_tokens: ContextVar[frozenset[UUID]] = ContextVar("mas_x_tokens", default=frozenset())


def x_tokens() -> frozenset[UUID]:
    """当前执行上下文持有的 X 锁 token 集合。"""
    return _x_tokens.get()


def add_x_token(token: UUID) -> None:
    _x_tokens.set(_x_tokens.get() | {token})


def discard_x_token(token: UUID) -> None:
    _x_tokens.set(_x_tokens.get() - {token})


if TYPE_CHECKING:
    from blinker import Signal

    from ..signals import WrappedSignal
    from .collection import ConfigCollection
    from .node import ConfigNode, NodeState

type WorkspaceUnit = ConfigNode | type[ConfigNode]


type ExecutionOwner = asyncio.Task[Any] | threading.Thread


def execution_owner() -> ExecutionOwner:
    """使用实际 Task / Thread，避免复制 ContextVar 或复用数字标识造成误判。"""
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return task if task is not None else threading.current_thread()


@dataclass
class TransactionContext:
    """事务工作区与暂存作用域；关闭后即使被子任务继承也不再有效。"""

    registered: list[WorkspaceUnit] = field(default_factory=list)
    owner: ExecutionOwner = field(default_factory=execution_owner)
    scope_id: UUID = field(default_factory=uuid4)
    transaction_id: UUID | None = None
    active: bool = True
    staged_nodes: dict[int, weakref.ReferenceType[ConfigNode]] = field(
        default_factory=dict
    )
    activations: list[_ActivationLifecycle] = field(default_factory=list)
    init_node: ConfigNode | None = None
    pending_roots: dict[UUID, RootRecord | None] | None = None
    pending_collections: dict[str, ConfigCollection[Any]] | None = None
    saved_workspaces: dict[int, _InitWorkspaceBackup] | None = None
    saved_signals: dict[type[ConfigNode], Signal | None] | None = None
    signal_undo: list[_SignalUndo] | None = None
    saved_registry: (
        tuple[
            dict[UUID, RootRecord | None] | None,
            dict[str, ConfigCollection[Any]] | None,
        ]
        | None
    ) = None

    @property
    def is_current(self) -> bool:
        return self.active and self.owner is execution_owner()


@dataclass
class _ActivationLifecycle:
    root: weakref.ReferenceType[ConfigNode]
    owner: weakref.ReferenceType[ExecutionOwner] = field(
        default_factory=lambda: weakref.ref(execution_owner())
    )
    finished: bool = False
    complete: bool = False


@dataclass
class _InitWorkspaceBackup:
    node: ConfigNode
    workspace: ConfigNode | None
    snapshot: ConfigNode | None
    init_workspace: ConfigNode | None
    init_snapshot: ConfigNode | None


@dataclass(frozen=True)
class _SignalUndo:
    cls: type[ConfigNode]
    receiver: WrappedSignal | weakref.ReferenceType[WrappedSignal]
    sender: weakref.ReferenceType[ConfigNode] | None
    weak: bool
    was_connected: bool


@dataclass
class _ActivationMode:
    owner: ExecutionOwner = field(default_factory=execution_owner)
    active: bool = True
    enabled: bool = True
    lifecycle: _ActivationLifecycle | None = None


@dataclass
class _FastInit:
    context: TransactionContext
    node: ConfigNode
    error: BaseException | None = None


class _FastInitFallback(Exception):
    """字段快路径在产生事务外影响之前转回原流程。"""


@dataclass(eq=False)
class _ExecutionWaiter:
    owner: ExecutionOwner
    future: asyncio.Future[None] | None = None
    granted: bool = False


@dataclass
class _NodeCommit:
    node_id: int
    owner: ExecutionOwner = field(default_factory=execution_owner)
    active: bool = True


@dataclass
class RootRecord:
    node: ConfigNode
    path: Path
    revision: int = 0


@dataclass(frozen=True)
class PersistenceFailure:
    """只读保存状态；时间使用单调时钟，不含配置载荷和原始异常文本。"""

    root_id: UUID
    path: Path
    phase: Literal["export", "write"]
    error_type: str
    retry_count: int
    next_retry_at: float | None


@dataclass
class _SaveFailure:
    record: RootRecord
    revision: int
    error: ConfigPersistenceError
    retry_count: int
    next_retry_at: float | None


class ConfigManager:
    """全局配置管理器单例。"""

    def __init__(self) -> None:
        self._collections: dict[str, ConfigCollection[Any]] = {}
        self._roots: dict[UUID, RootRecord] = {}
        self._txn: ContextVar[TransactionContext | None] = ContextVar(
            "config_framework_v2_txn", default=None
        )
        # Init 事务栈：嵌套时压入独立 ctx（与普通事务「嵌套空开」不同）
        self._init_txn: ContextVar[tuple[TransactionContext, ...] | None] = ContextVar(
            "config_framework_v2_init_txn", default=None
        )
        self._fast_init: ContextVar[_FastInit | None] = ContextVar(
            "config_framework_v2_fast_init", default=None
        )
        self._activation_mode: ContextVar[_ActivationMode | None] = ContextVar(
            "config_framework_v2_activation_mode", default=None
        )
        # 提交帧校验实际所有者和生命周期，子 Task 不能继承原任务的重入资格。
        self._committing_nodes: ContextVar[tuple[_NodeCommit, ...]] = ContextVar(
            "config_framework_v2_committing", default=()
        )
        # 同一入口覆盖完整提交批次、显式事务与保存；节点锁必须排在其后。
        # Condition 只保护所有权及等待队列，绝不跨 await 持有。
        self._execution_condition = threading.Condition()
        self._execution_owner: ExecutionOwner | None = None
        self._execution_depth = 0
        self._execution_waiters: deque[_ExecutionWaiter] = deque()
        self._save_handle: asyncio.Task[None] | None = None
        self._debounce_seconds: float = 0.05
        self._clock = monotonic
        self._save_requested = False
        self._save_deadline = 0.0
        self._save_loop: asyncio.AbstractEventLoop | None = None
        self._save_event: asyncio.Event | None = None
        self._save_failures: dict[UUID, _SaveFailure] = {}
        self._save_retry_delays = (1.0, 2.0, 4.0, 8.0, 16.0)

    # ──────────────── ref 池（仅 Collection）────────────────

    def register_collection(self, name: str, col: ConfigCollection[Any]) -> None:
        self._require_registration(col)
        with self._execution_gate_sync():
            self._require_registration(col)
            self._register_collection(name, col)

    def _register_collection(self, name: str, col: ConfigCollection[Any]) -> None:
        if col.deleted:
            raise ValueError("不能登记已删除的集合")
        ctx = self.current
        pending = ctx.pending_collections if ctx is not None else None
        if name in self._collections or (pending is not None and name in pending):
            raise ValueError(f"Collection 名称已登记: {name}")
        if self.is_registered_collection(col):
            raise ValueError("该 Collection 实例已登记")
        if ctx is None:
            self._collections[name] = col
        else:
            self._capture_registry()
            if ctx.pending_collections is None:
                ctx.pending_collections = {}
            ctx.pending_collections[name] = col

    def get_collection(self, name: str) -> ConfigCollection[Any]:
        ctx = self.current
        if ctx is not None and ctx.pending_collections is not None:
            if name in ctx.pending_collections:
                return ctx.pending_collections[name]
        if name not in self._collections:
            raise LookupError(f"ref 目标未登记: {name}")
        return self._collections[name]

    def is_registered_collection(self, col: "ConfigNode") -> bool:
        from .collection import ConfigCollection

        if not isinstance(col, ConfigCollection):
            return False
        ctx = self.current
        return any(c is col for c in self._collections.values()) or (
            ctx is not None
            and ctx.pending_collections is not None
            and any(c is col for c in ctx.pending_collections.values())
        )

    # ──────────────── 持久化根（file=）────────────────

    def register_root(self, node: ConfigNode, path: Path) -> None:
        self._require_registration(node)
        with self._execution_gate_sync():
            self._require_registration(node)
            self._register_root(node, path)

    def _register_root(self, node: ConfigNode, path: Path) -> None:
        if node.deleted:
            raise ValueError("不能登记已删除的节点")
        path = Path(path)
        if not node.is_root:
            raise ValueError("仅根节点可登记持久化文件")
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError(f"持久化文件必须是 .yaml / .yml: {path}")
        self._set_root(node.uid, RootRecord(node=node, path=path))

    def _require_registration(self, node: ConfigNode) -> None:
        if node._is_workspace:
            raise ValueError("登记必须使用 live 节点，不能登记工作区")
        if self._current_activation_mode() is not None or self.in_init_transaction:
            raise ValueError("初始化登记仅允许激活内部执行")
        if not node._activation_ready:
            raise ValueError("公开登记仅用于已完成激活的节点")

    def _check_activation_registration(self, node: ConfigNode) -> None:
        """在建立工作区和生命周期标记前检查全部登记声明。"""
        if node._pending_file is not None:
            if not node.is_root or node._pending_file.suffix.lower() not in {
                ".yaml",
                ".yml",
            }:
                raise ValueError("持久化声明必须是根节点的 YAML 文件")
        if node._pending_name is not None:
            from .collection import ConfigCollection

            if not isinstance(node, ConfigCollection):
                raise ValueError("命名登记仅用于集合")
            ctx = self.current
            pending = ctx.pending_collections if ctx is not None else None
            name = node._pending_name
            if name in self._collections or (pending is not None and name in pending):
                raise ValueError(f"Collection 名称已登记: {name}")
            if self.is_registered_collection(node):
                raise ValueError("该 Collection 实例已登记")

    def _register_activation(self, node: ConfigNode) -> None:
        """激活入口登记声明；只对所属事务可见，随事务发布或回退。"""
        mode = self._current_activation_mode()
        if mode is None or mode.lifecycle is not node._activation_lifecycle:
            raise RuntimeError("初始化登记须由所属激活入口执行")
        if self.current is None or self.in_fast_activation:
            raise RuntimeError("初始化登记不属于字段赋值段")
        self._check_activation_registration(node)
        if node._pending_file is not None:
            self._register_root(node, node._pending_file)
        from .collection import ConfigCollection

        if isinstance(node, ConfigCollection) and node._pending_name is not None:
            self._register_collection(node._pending_name, node)

    def _root_record(self, uid: UUID) -> RootRecord | None:
        ctx = self.current
        if ctx is not None and ctx.pending_roots is not None:
            if uid in ctx.pending_roots:
                return ctx.pending_roots[uid]
        return self._roots.get(uid)

    def _set_root(self, uid: UUID, record: RootRecord | None) -> None:
        ctx = self.current
        if ctx is None:
            with self._execution_condition:
                self._save_failures.pop(uid, None)
                if record is None:
                    self._roots.pop(uid, None)
                else:
                    self._roots[uid] = record
        else:
            self._capture_registry()
            if ctx.pending_roots is None:
                ctx.pending_roots = {}
            ctx.pending_roots[uid] = record

    def unregister_root(self, node: ConfigNode) -> None:
        """解除 ``file=`` 持久化根登记（幂等）。

        与 ref 池 ``register_collection``（不可解除）不同：``_roots`` 允许显式摘掉，
        供插件配置等临时根在禁用后离开 ``flush`` / 防抖扫描集。
        调用方须先 ``commit`` 并完成对该根的落盘，再 unregister。
        """
        if self._root_record(node.uid) is None:
            return
        self._require_registration(node)
        with self._execution_gate_sync():
            self._require_registration(node)
            rec = self._root_record(node.uid)
            if rec is not None and rec.node is node:
                self._set_root(node.uid, None)

    def get_file(self, root: ConfigNode) -> Path | None:
        rec = self._root_record(root.uid)
        return rec.path if rec is not None and rec.node is root else None

    def is_persist_root(self, node: ConfigNode) -> bool:
        rec = self._root_record(node.uid)
        return rec is not None and rec.node is node

    def iter_persist_roots(self) -> Iterator[ConfigNode]:
        records: dict[UUID, RootRecord | None] = dict(self._roots)
        ctx = self.current
        if ctx is not None and ctx.pending_roots is not None:
            records.update(ctx.pending_roots)
        for rec in records.values():
            if rec is not None:
                yield rec.node

    async def export(self, target: Path) -> None:
        """将已激活持久化根的已提交内存状态，以明文 YAML 导出到目标目录。

        不调用 flush，不修改运行文件或保存请求；忽略 UI 显隐，不含响应式字段。
        与提交共用执行入口，事务 / Init 内禁止导出，避免混入未提交工作区。

        Args:
            target: 导出目录，保留注册文件相对公共父目录的路径结构。
        """
        if self.in_transaction:
            raise RuntimeError("事务或初始化内不能导出，请在事务结束后导出")
        async with self.execution_gate():
            records = [
                record
                for record in self._roots.values()
                if record.node.activation_state == NodeState.ACTIVE
            ]
            if not records:
                target.mkdir(parents=True, exist_ok=True)
                return
            paths = [Path(os.path.abspath(record.path)) for record in records]
            base = Path(os.path.commonpath([path.parent for path in paths]))
            destinations = [target / path.relative_to(base) for path in paths]
            if len(set(destinations)) != len(destinations):
                raise ValueError("多个配置根关联同一导出文件")
            source_paths = {path.resolve() for path in paths}
            if any(
                destination.resolve() in source_paths for destination in destinations
            ):
                raise ValueError("明文导出不能覆盖运行中的配置文件")
            # 先完成全部序列化，成功后再写导出文件；始终读取 live，不激活副本。
            payloads = [
                record.node.model_dump(
                    mode="json",
                    context=ExportContext(audience="export"),
                )
                for record in records
            ]
            for destination, payload in zip(destinations, payloads, strict=True):
                write_file(destination, payload)

    # ──────────────── 全局执行入口 ────────────────

    def _enter_execution(self, waiter: _ExecutionWaiter) -> bool:
        """调用方持有 Condition；新申请不得绕过已经排队的等待者。"""
        if self._execution_owner is waiter.owner:
            self._execution_depth += 1
            return True
        if self._execution_owner is None and not self._execution_waiters:
            self._execution_owner = waiter.owner
            self._execution_depth = 1
            return True
        return False

    def _leave_execution(self, owner: ExecutionOwner) -> None:
        with self._execution_condition:
            if self._execution_owner is not owner:
                raise RuntimeError("非执行入口持有者，不能释放")
            self._execution_depth -= 1
            if self._execution_depth:
                return
            self._execution_owner = None
            while self._execution_waiters:
                waiter = self._execution_waiters.popleft()
                future = waiter.future
                if future is not None and (
                    future.done() or future.get_loop().is_closed()
                ):
                    continue
                waiter.granted = True
                self._execution_owner = waiter.owner
                self._execution_depth = 1
                if future is not None:

                    def wake(target: asyncio.Future[None] = future) -> None:
                        if not target.done():
                            target.set_result(None)

                    try:
                        future.get_loop().call_soon_threadsafe(wake)
                    except RuntimeError:
                        waiter.granted = False
                        self._execution_owner = None
                        self._execution_depth = 0
                        continue
                self._execution_condition.notify_all()
                break

    @asynccontextmanager
    async def execution_gate(self) -> AsyncGenerator[None, None]:
        """按真实执行者重入；排队时不持节点锁，取消后归还已交接的资格。"""
        waiter = _ExecutionWaiter(execution_owner())
        with self._execution_condition:
            entered = self._enter_execution(waiter)
            if not entered:
                waiter.future = asyncio.get_running_loop().create_future()
                self._execution_waiters.append(waiter)
        if not entered:
            try:
                assert waiter.future is not None
                await waiter.future
            except BaseException:
                with self._execution_condition:
                    if waiter.granted:
                        self._leave_execution(waiter.owner)
                    elif waiter in self._execution_waiters:
                        self._execution_waiters.remove(waiter)
                raise
        try:
            self._ensure_save_worker()
            yield
        finally:
            self._leave_execution(waiter.owner)

    @contextmanager
    def _execution_gate_sync(self) -> Generator[None, None, None]:
        waiter = _ExecutionWaiter(execution_owner())
        with self._execution_condition:
            if not self._enter_execution(waiter):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError(
                        "执行入口已占用，请使用异步 transaction，不能阻塞事件循环"
                    )
                self._execution_waiters.append(waiter)
                try:
                    self._execution_condition.wait_for(lambda: waiter.granted)
                except BaseException:
                    if waiter.granted:
                        self._leave_execution(waiter.owner)
                    elif waiter in self._execution_waiters:
                        self._execution_waiters.remove(waiter)
                    raise
        try:
            yield
        finally:
            self._leave_execution(waiter.owner)

    # ──────────────── 事务 ────────────────

    @property
    def in_transaction(self) -> bool:
        return self.current is not None

    @property
    def current(self) -> TransactionContext | None:
        ctx = self._txn.get()
        return ctx if ctx is not None and ctx.is_current else None

    @property
    def staging_scope(self) -> UUID | None:
        ctx = self._current_init_ctx() or self.current
        return ctx.scope_id if ctx is not None else None

    def _register_staged(self, node: ConfigNode) -> None:
        ctx = self._current_init_ctx() or self.current
        if ctx is not None:
            ctx.staged_nodes[id(node)] = weakref.ref(node)

    def _check_staged(self, ctx: TransactionContext) -> None:
        count = sum(
            len(node._stage_queue(ctx.scope_id))
            for ref in ctx.staged_nodes.values()
            if (node := ref()) is not None
        )
        if count:
            raise RuntimeError(f"事务返回前须 commit 当次 stage，残留 {count} 条")

    def _close_context(self, ctx: TransactionContext) -> None:
        ctx.active = False
        for ref in ctx.staged_nodes.values():
            if (node := ref()) is not None:
                node._discard_stage_scope(ctx.scope_id)
        ctx.staged_nodes.clear()
        ctx.activations.clear()
        ctx.saved_workspaces = None
        ctx.saved_signals = None
        ctx.signal_undo = None
        ctx.saved_registry = None
        ctx.pending_roots = None
        ctx.pending_collections = None
        ctx.init_node = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """每 op 独立事务；同 Task 嵌套复用当前上下文，不扩大回滚边界。"""
        if self.in_transaction:
            try:
                yield
            except BaseException as exc:
                fast = self._current_fast_init()
                if fast is not None and fast.error is None:
                    fast.error = exc
                raise
            return
        need_save = False
        ctx: TransactionContext | None = None
        try:
            async with self.execution_gate():
                ctx = TransactionContext()
                token = self._txn.set(ctx)
                try:
                    yield
                    need_save = self.COMMIT(ctx)
                except BaseException:
                    self.ROLLBACK(ctx)
                    raise
                finally:
                    self._close_context(ctx)
                    self._txn.reset(token)
        finally:
            if ctx is not None:
                self._transaction_settled(need_save=need_save)

    @contextmanager
    def transaction_sync(self) -> Generator[None, None, None]:
        """同步等价入口；事件循环内竞争时拒绝阻塞，工作线程可以排队。"""
        if self.in_transaction:
            try:
                yield
            except BaseException as exc:
                fast = self._current_fast_init()
                if fast is not None and fast.error is None:
                    fast.error = exc
                raise
            return
        need_save = False
        ctx: TransactionContext | None = None
        try:
            with self._execution_gate_sync():
                ctx = TransactionContext()
                token = self._txn.set(ctx)
                try:
                    yield
                    need_save = self.COMMIT(ctx)
                except BaseException:
                    self.ROLLBACK(ctx)
                    raise
                finally:
                    self._close_context(ctx)
                    self._txn.reset(token)
        finally:
            if ctx is not None:
                self._transaction_settled(need_save=need_save)

    def _register_workspace(self, unit: WorkspaceUnit) -> None:
        ctx = self.current
        if ctx is not None and not any(u is unit for u in ctx.registered):
            ctx.registered.append(unit)

    def _init_rollback_contexts(self) -> Iterator[TransactionContext]:
        transaction = self.current
        if transaction is None:
            return
        fast = self._current_fast_init()
        for ctx in self._init_txn.get() or ():
            if ctx.is_current and ctx.transaction_id == transaction.scope_id:
                yield ctx
                # 快段整体回退；不为内部每次赋值复制这些业务状态。
                if fast is not None and ctx is fast.context:
                    break

    def _capture_workspace(
        self, node: ConfigNode, *, exclude_node_scope: bool = False
    ) -> None:
        for ctx in self._init_rollback_contexts():
            if exclude_node_scope and ctx.init_node is node:
                continue
            if ctx.saved_workspaces is None:
                ctx.saved_workspaces = {}
            if id(node) not in ctx.saved_workspaces:
                workspace = node._workspace
                snapshot = (
                    node._make_workspace_shell(init=True)
                    if workspace is not None
                    else None
                )
                init_workspace = workspace._workspace if workspace is not None else None
                init_snapshot = (
                    node._make_workspace_shell(source=init_workspace)
                    if init_workspace is not None
                    else None
                )
                ctx.saved_workspaces[id(node)] = _InitWorkspaceBackup(
                    node=node,
                    workspace=workspace,
                    snapshot=snapshot,
                    init_workspace=init_workspace,
                    init_snapshot=init_snapshot,
                )

    def _capture_signal(self, cls: type[ConfigNode]) -> None:
        for ctx in self._init_rollback_contexts():
            if ctx.saved_signals is None:
                ctx.saved_signals = {}
            if cls not in ctx.saved_signals:
                ctx.saved_signals[cls] = cls._signal_workspace

    def _record_signal(
        self,
        cls: type[ConfigNode],
        receiver: WrappedSignal,
        sender: ConfigNode | None,
        *,
        weak: bool,
        was_connected: bool,
    ) -> None:
        undo: _SignalUndo | None = None
        for ctx in self._init_rollback_contexts():
            if undo is None:
                undo = _SignalUndo(
                    cls=cls,
                    receiver=weakref.ref(receiver) if weak else receiver,
                    sender=weakref.ref(sender) if sender is not None else None,
                    weak=weak,
                    was_connected=was_connected,
                )
            if ctx.signal_undo is None:
                ctx.signal_undo = []
            ctx.signal_undo.append(undo)

    def _capture_registry(self) -> None:
        transaction = self.current
        assert transaction is not None
        for ctx in self._init_rollback_contexts():
            if ctx.saved_registry is None:
                ctx.saved_registry = (
                    dict(transaction.pending_roots)
                    if transaction.pending_roots is not None
                    else None,
                    dict(transaction.pending_collections)
                    if transaction.pending_collections is not None
                    else None,
                )

    def COMMIT(self, ctx: TransactionContext) -> bool:
        self._check_staged(ctx)
        roots: dict[UUID, RootRecord] = {}
        for unit in ctx.registered:
            if not isinstance(unit, type) and unit._workspace is not None:
                record = self._root_record(unit.root.uid)
                if record is not None and record.node is unit.root:
                    roots[unit.root.uid] = record
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._COMMIT_signal()
            else:
                unit._COMMIT()
        if ctx.pending_collections is not None:
            self._collections.update(ctx.pending_collections)
        if ctx.pending_roots is not None:
            with self._execution_condition:
                for uid, record in ctx.pending_roots.items():
                    self._save_failures.pop(uid, None)
                    if record is None:
                        self._roots.pop(uid, None)
                    else:
                        self._roots[uid] = record
        for record in roots.values():
            record.revision += 1
        # 全部节点合并后才开放热态能力，避免先完成的子节点提前对外可用。
        for lifecycle in ctx.activations:
            lifecycle.complete = lifecycle.finished
        ctx.registered.clear()
        return bool(roots)

    def ROLLBACK(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._ROLLBACK_signal()
            else:
                unit._ROLLBACK()
        for lifecycle in ctx.activations:
            lifecycle.finished = False
            lifecycle.complete = False
        ctx.registered.clear()

    # ──────────────── Init 事务（须嵌在普通事务内）────────────────

    def _current_activation_mode(self) -> _ActivationMode | None:
        mode = self._activation_mode.get()
        return (
            mode
            if mode is not None and mode.active and mode.owner is execution_owner()
            else None
        )

    @property
    def try_fast_activation(self) -> bool:
        mode = self._current_activation_mode()
        return mode is not None and mode.enabled

    @contextmanager
    def _activation_scope(self, *, try_fast: bool) -> Generator[None, None, None]:
        if self._current_activation_mode() is not None:
            yield
            return
        mode = _ActivationMode(enabled=try_fast and not self.in_transaction)
        token = self._activation_mode.set(mode)
        try:
            yield
        finally:
            mode.active = False
            self._activation_mode.reset(token)

    @contextmanager
    def _regular_activation(self) -> Generator[None, None, None]:
        mode = self._current_activation_mode()
        if mode is None:
            yield
            return
        enabled = mode.enabled
        mode.enabled = False
        try:
            yield
        finally:
            mode.enabled = enabled

    def _current_fast_init(self) -> _FastInit | None:
        fast = self._fast_init.get()
        if fast is None:
            return None
        transaction = self.current
        return (
            fast
            if transaction is not None
            and fast.context.is_current
            and fast.context.transaction_id == transaction.scope_id
            else None
        )

    @property
    def in_fast_activation(self) -> bool:
        return self._current_fast_init() is not None

    def _require_regular_activation(self, node: ConfigNode | None = None) -> None:
        fast = self._current_fast_init()
        if fast is None or node is fast.node:
            return
        error = _FastInitFallback("该操作不属于当前 Entry 的字段赋值")
        if fast.error is None:
            fast.error = error
        raise error

    def _reuse_init_workspace(self, node: ConfigNode) -> bool:
        fast = self._current_fast_init()
        if fast is None:
            return False
        # 共享工作区不代表正在处理该节点；再入资格仍按当前操作栈判定。
        return not any(
            unit is node
            for ctx in self._init_txn.get() or ()
            if ctx is not fast.context and ctx.is_current
            for unit in ctx.registered
        )

    @asynccontextmanager
    async def _fast_init_transaction(
        self, node: ConfigNode
    ) -> AsyncGenerator[_FastInit, None]:
        transaction = self.current
        if (
            transaction is None
            or self.in_fast_activation
            or node.init_workspace is not None
        ):
            raise RuntimeError("快速赋值须在普通工作区内独立建立 Init 工作区")
        ctx = TransactionContext(transaction_id=transaction.scope_id, init_node=node)
        fast = _FastInit(context=ctx, node=node)
        parent = self._init_txn.get() if self.in_init_transaction else None
        init_token = self._init_txn.set((*(parent or ()), ctx))
        fast_token = self._fast_init.set(fast)
        try:
            yield fast
            self.COMMIT_init(ctx)
        except BaseException:
            self.ROLLBACK_init(ctx)
            raise
        finally:
            try:
                self._close_context(ctx)
            finally:
                fast.error = None
                self._fast_init.reset(fast_token)
                self._init_txn.reset(init_token)

    @property
    def in_init_transaction(self) -> bool:
        return self._current_init_ctx() is not None

    def _current_init_ctx(self) -> TransactionContext | None:
        transaction = self.current
        stack = self._init_txn.get()
        if transaction is None or not stack:
            return None
        ctx = stack[-1]
        return (
            ctx
            if ctx.is_current and ctx.transaction_id == transaction.scope_id
            else None
        )

    @asynccontextmanager
    async def init_transaction(
        self, *, node: ConfigNode | None = None
    ) -> AsyncGenerator[None, None]:
        """须已在普通事务中。每次进入压入独立 ctx；结束只提交/回滚本层（可嵌套）。"""
        if not self.in_transaction:
            raise RuntimeError("init_transaction 须在 transaction 内")
        transaction = self.current
        assert transaction is not None
        fast = self._current_fast_init()
        parent = self._init_txn.get() if self.in_init_transaction else None
        ctx = TransactionContext(transaction_id=transaction.scope_id, init_node=node)
        token = self._init_txn.set((*(parent or ()), ctx))
        try:
            yield
            if fast is None:
                self.COMMIT_init(ctx)
            else:
                # 保留逐操作的暂存作用域及退出检查，工作区只在快速尝试末尾合并。
                self._check_staged(ctx)
        except BaseException as exc:
            if fast is None:
                self.ROLLBACK_init(ctx)
            elif fast.error is None:
                fast.error = exc
            raise
        finally:
            self._close_context(ctx)
            self._init_txn.reset(token)

    def _register_init_workspace(self, node: "ConfigNode") -> None:
        ctx = self._current_init_ctx()
        if ctx is None:
            return
        if not any(u is node for u in ctx.registered):
            ctx.registered.append(node)
        fast = self._current_fast_init()
        if fast is not None and not any(u is node for u in fast.context.registered):
            fast.context.registered.append(node)

    def COMMIT_init(self, ctx: TransactionContext) -> None:
        self._check_staged(ctx)
        for unit in ctx.registered:
            if not isinstance(unit, type):
                unit._COMMIT_init()
        ctx.registered.clear()

    def ROLLBACK_init(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if not isinstance(unit, type):
                unit._ROLLBACK_init()
        if ctx.saved_workspaces is not None:
            for backup in reversed(list(ctx.saved_workspaces.values())):
                node = backup.node
                if backup.workspace is None:
                    node._ROLLBACK()
                else:
                    assert backup.snapshot is not None
                    # 回填原壳，保留外层仍在使用的 Init 层和分组引用。
                    backup.workspace._apply_workspace(backup.snapshot)
                    backup.workspace._workspace = backup.init_workspace
                    if backup.init_workspace is not None:
                        assert backup.init_snapshot is not None
                        backup.init_workspace._apply_workspace(backup.init_snapshot)
                    node._workspace = backup.workspace
                    if node._activation_state == NodeState.INACTIVE:
                        node._activation_lifecycle = (
                            backup.workspace._activation_lifecycle
                        )
        if ctx.saved_signals is not None:
            for cls, previous_signal in ctx.saved_signals.items():
                cls._signal_workspace = previous_signal
        if ctx.signal_undo is not None:
            for undo in reversed(ctx.signal_undo):
                signal = undo.cls._signal_workspace
                if signal is None:
                    continue
                receiver = (
                    undo.receiver()
                    if isinstance(undo.receiver, weakref.ReferenceType)
                    else undo.receiver
                )
                sender = undo.sender() if undo.sender is not None else ANY
                if receiver is None or sender is None:
                    continue
                if undo.was_connected:
                    signal.connect(receiver, sender=sender, weak=undo.weak)
                else:
                    signal.disconnect(receiver, sender=sender)
        if ctx.saved_registry is not None:
            transaction = self.current
            assert transaction is not None
            transaction.pending_roots, transaction.pending_collections = (
                ctx.saved_registry
            )
        ctx.registered.clear()

    # ──────────────── 节点 commit 串行 ────────────────

    def in_node_commit(self, node: ConfigNode) -> bool:
        owner = execution_owner()
        return any(
            frame.active and frame.owner is owner and frame.node_id == id(node)
            for frame in self._committing_nodes.get()
        )

    @asynccontextmanager
    async def node_commit(self, node: ConfigNode) -> AsyncGenerator[None, None]:
        """完整批次先取得全局入口，再取节点锁；同执行者嵌套重入。"""
        async with self.execution_gate():
            if self.in_node_commit(node):
                yield
                return
            lock = node._commit_lock
            if lock is None:
                lock = asyncio.Lock()
                node._commit_lock = lock
            await lock.acquire()
            frame = _NodeCommit(id(node))
            token = self._committing_nodes.set((*self._committing_nodes.get(), frame))
            try:
                yield
            finally:
                frame.active = False
                self._committing_nodes.reset(token)
                lock.release()

    # ──────────────── 防抖落盘 ────────────────

    @property
    def persistence_errors(self) -> tuple[PersistenceFailure, ...]:
        with self._execution_condition:
            return tuple(
                PersistenceFailure(
                    root_id=uid,
                    path=failure.record.path,
                    phase=failure.error.phase,
                    error_type=type(failure.error.cause).__name__,
                    retry_count=failure.retry_count,
                    next_retry_at=failure.next_retry_at,
                )
                for uid, failure in self._save_failures.items()
            )

    def _transaction_settled(self, *, need_save: bool) -> None:
        with self._execution_condition:
            if need_save:
                self._save_requested = True
            if self._save_requested or self._save_failures:
                self._save_deadline = self._clock() + self._debounce_seconds
        self._notify_save_worker()

    def schedule_debounced_save(self) -> None:
        """登记请求；重置计时，不取消正在执行的写入。"""
        self._transaction_settled(need_save=True)

    def _next_save_due(self) -> float | None:
        with self._execution_condition:
            for uid, failure in tuple(self._save_failures.items()):
                if self._roots.get(uid) is not failure.record:
                    del self._save_failures[uid]
            deadlines = [self._save_deadline] if self._save_requested else []
            deadlines.extend(
                max(failure.next_retry_at, self._save_deadline)
                for failure in self._save_failures.values()
                if failure.next_retry_at is not None
            )
        return min(deadlines) if deadlines else None

    def _ensure_save_worker(self) -> None:
        if self._next_save_due() is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        with self._execution_condition:
            if self._save_handle is not None and not self._save_handle.done():
                return
            self._save_loop = loop
            self._save_event = asyncio.Event()
            # 只移除配置执行上下文；保留日志追踪等其它 ContextVar。
            context = copy_context()
            context.run(self._txn.set, None)
            context.run(self._init_txn.set, None)
            context.run(self._fast_init.set, None)
            context.run(self._activation_mode.set, None)
            context.run(self._committing_nodes.set, ())
            self._save_handle = loop.create_task(self._save_worker(), context=context)
            self._save_handle.add_done_callback(self._save_worker_done)

    def _notify_save_worker(self) -> None:
        self._ensure_save_worker()
        with self._execution_condition:
            loop, event = self._save_loop, self._save_event
            if loop is not None and event is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(event.set)
                except RuntimeError:
                    # 其它线程提交时，所属循环可能刚刚退出；请求留待后续入口处理。
                    pass

    def _save_worker_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(f"配置保存执行器异常：{type(error).__name__}")
        else:
            # 其它线程可能在执行器退出与 Task 标记 done 之间登记了新请求。
            self._ensure_save_worker()

    async def _save_worker(self) -> None:
        event = self._save_event
        assert event is not None
        while True:
            event.clear()
            # 先清唤醒位再读取期限，避免其它线程的新请求被随后 clear 吞掉。
            deadline = self._next_save_due()
            if deadline is None:
                return
            delay = deadline - self._clock()
            if delay > 0:
                try:
                    await asyncio.wait_for(event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                else:
                    continue
            async with self.execution_gate():
                due = self._next_save_due()
                if due is None or due > self._clock():
                    continue
                with self._execution_condition:
                    full = self._save_requested and self._save_deadline <= self._clock()
                    if full:
                        self._save_requested = False
                try:
                    await self._debounced_save_impl(full=full)
                except BaseException:
                    # 退出 / 取消不能把尚未完成的一轮误记为已经保存。
                    with self._execution_condition:
                        self._save_requested = True
                    raise

    def _record_save_failure(
        self,
        record: RootRecord,
        error: ConfigPersistenceError,
        *,
        force: bool,
    ) -> None:
        with self._execution_condition:
            previous = self._save_failures.get(record.node.uid)
            count = previous.retry_count if previous is not None else 0
            if (
                previous is not None
                and not force
                and isinstance(previous.error.cause, OSError)
            ):
                count += 1
            next_retry = None
            if isinstance(error.cause, OSError) and count < len(
                self._save_retry_delays
            ):
                next_retry = self._clock() + self._save_retry_delays[count]
            self._save_failures[record.node.uid] = _SaveFailure(
                record=record,
                revision=record.revision,
                error=error,
                retry_count=count,
                next_retry_at=next_retry,
            )
        if previous is None:
            logger.warning(
                f"配置保存失败：{record.path}（{type(error.cause).__name__}）"
            )
        if (
            isinstance(error.cause, OSError)
            and count >= len(self._save_retry_delays)
            and (
                previous is None or previous.retry_count < len(self._save_retry_delays)
            )
        ):
            logger.error(f"配置保存自动重试已耗尽：{record.path}")

    async def _debounced_save_impl(
        self, *, full: bool = True, force: bool = False
    ) -> list[ConfigPersistenceError]:
        """调用方持执行入口；逐根隔离失败，同步原子写入期间不让出稳定状态。"""
        errors: list[ConfigPersistenceError] = []
        for root in self.iter_persist_roots():
            record = self._roots.get(root.uid)
            if record is None or record.node is not root:
                continue
            failure = self._save_failures.get(root.uid)
            if not force:
                if failure is not None:
                    if isinstance(failure.error.cause, OSError):
                        if (
                            failure.next_retry_at is None
                            or failure.next_retry_at > self._clock()
                        ):
                            continue
                    elif failure.revision == record.revision:
                        continue
                elif not full:
                    continue
            # 构造先登记、激活在后；未激活根没有可保存状态。
            if root.activation_state != NodeState.ACTIVE:
                continue
            phase: Literal["export", "write"] = "export"
            try:
                payload = await root.to_dict()
                if self._roots.get(root.uid) is not record:
                    continue
                phase = "write"
                write_file(record.path, payload)
            except Exception as exc:
                if self._roots.get(root.uid) is not record:
                    continue
                error = ConfigPersistenceError(path=record.path, phase=phase, cause=exc)
                self._record_save_failure(record, error, force=force)
                errors.append(error)
            else:
                with self._execution_condition:
                    recovered = self._save_failures.pop(root.uid, None)
                if recovered is not None:
                    logger.info(f"配置保存已恢复：{record.path}")
        return errors

    async def flush(self) -> None:
        """跳过防抖并尝试全部根；成功代表本轮已写盘，区别于内存 commit。"""
        if self.in_transaction:
            raise RuntimeError("事务或信号回调内不能 flush，请在事务结束后保存")
        try:
            async with self.execution_gate():
                with self._execution_condition:
                    self._save_requested = False
                try:
                    errors = await self._debounced_save_impl(force=True)
                except BaseException:
                    with self._execution_condition:
                        self._save_requested = True
                    raise
                if errors:
                    raise ConfigAggregateError(list(errors))
        finally:
            self._notify_save_worker()


config_manager = ConfigManager()
"""全局单例。"""


# core/__init__.py 先加载本模块；单例就绪后再导入依赖它的节点类型。
from .node import ConfigNode, ExportContext, NodeState  # noqa: E402
