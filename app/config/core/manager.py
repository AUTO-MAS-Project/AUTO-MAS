"""ConfigManager：ref 池、持久化根、事务 / 工作区、防抖落盘。"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Generator
from collections.abc import Callable
from collections.abc import Iterator
from uuid import UUID

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


from app.utils.io import write_file

if TYPE_CHECKING:
    from ..triggers import TriggerDispatcher
    from .node import ConfigNode, NodeState
    from .collection import ConfigCollection

type WorkspaceUnit = ConfigNode | type[ConfigNode]


def _current_task() -> asyncio.Task[Any] | None:
    """同步配置入口也可在尚无事件循环的线程使用。"""
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


@dataclass
class TransactionContext:
    """普通 / Init 事务共用上下文；登记单元在结束时合并或丢弃对应工作区。"""

    registered: list[WorkspaceUnit] = field(default_factory=list)
    _task: asyncio.Task[Any] | None = field(default_factory=_current_task, init=False)
    _thread: int = field(default_factory=threading.get_ident, init=False)
    _active: bool = field(default=True, init=False)
    commands: list[Callable[[], object]] = field(default_factory=list)

    def is_current(self) -> bool:
        """ContextVar 可被子 Task 复制，事务只能由原执行者在有效期内使用。"""
        return (
            self._active
            and self._thread == threading.get_ident()
            and self._task is _current_task()
        )


@dataclass
class RootRecord:
    node: ConfigNode
    path: Path


class ConfigManager:
    """全局配置管理器单例。"""

    def __init__(self) -> None:
        self._collections: dict[str, ConfigCollection[Any]] = {}
        self._roots: dict[UUID, RootRecord] = {}
        self.trigger_dispatcher: TriggerDispatcher | None = None
        self._txn: ContextVar[TransactionContext | None] = ContextVar(
            "config_framework_v2_txn", default=None
        )
        # Init 事务栈：嵌套时压入独立 ctx（与普通事务「嵌套空开」不同）
        self._init_txn: ContextVar[tuple[TransactionContext, ...] | None] = ContextVar(
            "config_framework_v2_init_txn", default=None
        )
        # 本 Task 正在 commit 的节点 id 栈；tuple 不可变，进入 set 新元组、退出 reset
        self._committing_nodes: ContextVar[
            tuple[asyncio.Task[Any] | None, tuple[int, ...]] | None
        ] = ContextVar("config_framework_v2_committing", default=None)
        self._txn_lock = asyncio.Lock()
        self._txn_owner: asyncio.Task[Any] | None = None
        self._sync_lock = threading.RLock()
        self._transaction_owner: TransactionContext | None = None
        self._save_handle: asyncio.Task[None] | None = None
        self._debounce_seconds: float = 0.05

    # ──────────────── ref 池（仅 Collection）────────────────

    def register_collection(self, name: str, col: ConfigCollection[Any]) -> None:
        if name in self._collections:
            raise ValueError(f"Collection 名称已登记: {name}")
        if self.is_registered_collection(col):
            raise ValueError("该 Collection 实例已登记")
        self._collections[name] = col

    def get_collection(self, name: str) -> ConfigCollection[Any]:
        if name not in self._collections:
            raise LookupError(f"ref 目标未登记: {name}")
        return self._collections[name]

    def is_registered_collection(self, col: "ConfigNode") -> bool:
        from .collection import ConfigCollection

        if not isinstance(col, ConfigCollection):
            return False
        return any(c is col for c in self._collections.values())

    # ──────────────── 持久化根（file=）────────────────

    def register_root(self, node: ConfigNode, path: Path) -> None:
        path = Path(path)
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError(f"持久化文件必须是 .yaml / .yml: {path}")
        self._roots[node.uid] = RootRecord(node=node, path=path)

    def unregister_root(self, node: ConfigNode) -> None:
        """解除 ``file=`` 持久化根登记（幂等）。

        与 ref 池 ``register_collection``（不可解除）不同：``_roots`` 允许显式摘掉，
        供插件配置等临时根在禁用后离开 ``flush`` / 防抖扫描集。
        调用方须先 ``commit`` 并完成对该根的落盘，再 unregister。
        """
        rec = self._roots.get(node.uid)
        if rec is not None and rec.node is node:
            del self._roots[node.uid]

    def get_file(self, root: ConfigNode) -> Path | None:
        rec = self._roots.get(root.uid)
        return rec.path if rec is not None and rec.node is root else None

    def is_persist_root(self, node: ConfigNode) -> bool:
        rec = self._roots.get(node.uid)
        return rec is not None and rec.node is node

    def iter_persist_roots(self) -> Iterator[ConfigNode]:
        for rec in list(self._roots.values()):
            yield rec.node

    # ──────────────── 事务 ────────────────

    @property
    def in_transaction(self) -> bool:
        return self.current is not None

    @property
    def current(self) -> TransactionContext | None:
        ctx = self._txn.get()
        return ctx if ctx is not None and ctx.is_current() else None

    @asynccontextmanager
    async def _transaction_gate(self) -> AsyncGenerator[None, None]:
        """全局提交许可先于节点锁获取；同 Task 可重入，不合并各条 op 的事务。"""
        task = _current_task()
        outer = self._txn_owner is not task
        if outer:
            await self._txn_lock.acquire()
            self._txn_owner = task
        try:
            yield
        finally:
            if outer:
                self._txn_owner = None
                self._txn_lock.release()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """外层事务互斥；同 Task 嵌套复用上下文，子 Task 等待独立事务。"""
        if self.in_transaction:
            yield
            return
        async with self._transaction_gate():
            with self.transaction_sync():
                yield

    @contextmanager
    def transaction_sync(self) -> Generator[None, None, None]:
        """同步事务；外层互斥（``_sync_lock``）。"""
        is_outer = not self.in_transaction
        if is_outer:
            self._sync_lock.acquire()
            # RLock 只区分线程；同线程其他 Task 不能借同步入口共享工作区。
            if self._transaction_owner is not None:
                self._sync_lock.release()
                raise RuntimeError(
                    "不能重入其他 Task 的配置事务，请等待异步 transaction"
                )
        token = None
        if is_outer:
            self._transaction_owner = TransactionContext()
            token = self._txn.set(self._transaction_owner)
        committed = False
        commands: list[Callable[[], object]] = []
        try:
            yield
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.COMMIT(ctx)
                    commands = ctx.commands
                    committed = True
        except BaseException:
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.ROLLBACK(ctx)
            raise
        finally:
            if is_outer and token is not None:
                ctx = self._txn.get()
                if ctx is not None:
                    ctx._active = False
                self._txn.reset(token)
            if is_outer:
                self._transaction_owner = None
                self._sync_lock.release()
        if committed:
            for command in commands:
                command()
            commands.clear()

    def _register_workspace(self, unit: WorkspaceUnit) -> None:
        ctx = self.current
        if ctx is None:
            return
        if not any(u is unit for u in ctx.registered):
            ctx.registered.append(unit)

    def COMMIT(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._COMMIT_signal()
            else:
                unit._COMMIT()
        need_save = False
        for unit in ctx.registered:
            if isinstance(unit, type):
                continue
            if self.is_persist_root(unit.root):
                need_save = True
                break
        ctx.registered.clear()
        if need_save:
            self.schedule_debounced_save()

    def ROLLBACK(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._ROLLBACK_signal()
            else:
                unit._ROLLBACK()
        ctx.registered.clear()
        ctx.commands.clear()

    # ──────────────── Init 事务（须嵌在普通事务内）────────────────

    @property
    def in_init_transaction(self) -> bool:
        return self._current_init_ctx() is not None

    def _current_init_ctx(self) -> TransactionContext | None:
        stack = self._init_txn.get()
        ctx = stack[-1] if stack else None
        return ctx if ctx is not None and ctx.is_current() else None

    @asynccontextmanager
    async def init_transaction(self) -> AsyncGenerator[None, None]:
        """须已在普通事务中。每次进入压入独立 ctx；结束只提交/回滚本层（可嵌套）。"""
        if not self.in_transaction:
            raise RuntimeError("init_transaction 须在 transaction 内")
        parent = self._init_txn.get() if self.in_init_transaction else None
        ctx = TransactionContext()
        token = self._init_txn.set((*(parent or ()), ctx))
        try:
            yield
            self.COMMIT_init(ctx)
        except BaseException:
            self.ROLLBACK_init(ctx)
            raise
        finally:
            ctx._active = False
            self._init_txn.reset(token)

    def _register_init_workspace(self, node: "ConfigNode") -> None:
        ctx = self._current_init_ctx()
        if ctx is None:
            return
        if not any(u is node for u in ctx.registered):
            ctx.registered.append(node)

    def COMMIT_init(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if not isinstance(unit, type):
                unit._COMMIT_init()
        ctx.registered.clear()
        stack = self._init_txn.get() or ()
        parent = stack[-2] if len(stack) > 1 else self.current
        if parent is not None:
            parent.commands.extend(ctx.commands)
        ctx.commands.clear()

    def ROLLBACK_init(self, ctx: TransactionContext) -> None:
        ctx.commands.clear()
        for unit in ctx.registered:
            if not isinstance(unit, type):
                unit._ROLLBACK_init()
        ctx.registered.clear()

    # ──────────────── 节点 commit 串行 ────────────────

    def in_node_commit(self, node: "ConfigNode") -> bool:
        """本 Task 是否正在对该节点 ``commit``（含同 Task 嵌套）。"""
        state = self._committing_nodes.get()
        return (
            state is not None and state[0] is _current_task() and id(node) in state[1]
        )

    @asynccontextmanager
    async def node_commit(self, node: "ConfigNode") -> AsyncGenerator[None, None]:
        """先获全局许可再抢节点锁；同 Task 嵌套空过，释放时并入 pending。"""
        async with self._transaction_gate():
            nid = id(node)
            outer = not self.in_node_commit(node)
            token = None
            if outer:
                lock = node._commit_lock
                if lock is None:
                    lock = asyncio.Lock()
                    node._commit_lock = lock
                await lock.acquire()
                state = self._committing_nodes.get()
                owner = _current_task()
                nodes = state[1] if state is not None and state[0] is owner else ()
                token = self._committing_nodes.set((owner, (*nodes, nid)))
            try:
                yield
            finally:
                if outer:
                    if token is not None:
                        self._committing_nodes.reset(token)
                    if node._staged_pending:
                        node._staged_ops.extend(node._staged_pending)
                        node._staged_pending.clear()
                    lock = node._commit_lock
                    if lock is not None and lock.locked():
                        lock.release()

    # ──────────────── 防抖落盘 ────────────────

    def schedule_debounced_save(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._save_handle is not None and not self._save_handle.done():
            self._save_handle.cancel()

        async def debounce_then_save() -> None:
            try:
                await asyncio.sleep(self._debounce_seconds)
            except asyncio.CancelledError:
                return
            await self._debounced_save_impl()

        self._save_handle = loop.create_task(debounce_then_save())

    async def _debounced_save_impl(self) -> None:
        for root in self.iter_persist_roots():
            path = self.get_file(root)
            if path is None:
                continue
            # register_root 在 __init__ 里登记，activate 是后一步，故「已登记未激活」
            # 是正常生命周期状态：AppConfig 分两阶段热化（引导 3 个、领域 6 个），
            # 其间任一次 commit 都会扫到另 6 个还没热化的根；父事务 ROLLBACK 也会把
            # 节点退回 INACTIVE。而 to_dict 对非 ACTIVE 节点上抛，本方法又跑在
            # schedule_debounced_save 的裸 create_task 里 —— 抛出即整轮落盘全灭，
            # 且异常无人接收（只剩一句 never retrieved）。未激活的根本就没有可落盘的
            # 状态，跳过不丢数据：activate 自己会补上该根的首次写。
            if root.activation_state != NodeState.ACTIVE:
                continue
            # to_dict 已是 mode=json 文档；YAML 直接承载 null / 嵌套，无需适配层
            write_file(path, await root.to_dict())

    async def flush(self) -> None:
        """立即全量落盘，跳过防抖等待。"""
        if self._save_handle is not None and not self._save_handle.done():
            self._save_handle.cancel()
        await self._debounced_save_impl()


config_manager = ConfigManager()
"""全局单例。"""

from .node import ConfigNode, NodeState  # noqa: E402
