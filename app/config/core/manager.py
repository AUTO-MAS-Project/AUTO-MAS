"""ConfigManager：ref 池、持久化根、事务 / 工作区、防抖落盘。"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Generator
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
    from .node import ConfigNode, NodeState
    from .collection import ConfigCollection

type WorkspaceUnit = ConfigNode | type[ConfigNode]


@dataclass
class TransactionContext:
    """普通 / Init 事务共用上下文；登记单元在结束时合并或丢弃对应工作区。"""

    registered: list[WorkspaceUnit] = field(default_factory=list)


@dataclass
class RootRecord:
    node: ConfigNode
    path: Path


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
        # 本 Task 正在 commit 的节点 id 栈；tuple 不可变，进入 set 新元组、退出 reset
        self._committing_nodes: ContextVar[tuple[int, ...]] = ContextVar(
            "config_framework_v2_committing", default=()
        )
        self._txn_lock = asyncio.Lock()
        self._sync_lock = threading.RLock()
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
        return self._txn.get() is not None

    @property
    def current(self) -> TransactionContext | None:
        return self._txn.get()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """外层事务互斥（``_txn_lock``）；同 Task 嵌套复用同一 ``ctx``。"""
        is_outer = not self.in_transaction
        if is_outer:
            await self._txn_lock.acquire()
            self._sync_lock.acquire()
        token = None
        if is_outer:
            token = self._txn.set(TransactionContext())
        try:
            yield
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.COMMIT(ctx)
        except BaseException:
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.ROLLBACK(ctx)
            raise
        finally:
            if is_outer and token is not None:
                self._txn.reset(token)
            if is_outer:
                self._sync_lock.release()
                self._txn_lock.release()

    @contextmanager
    def transaction_sync(self) -> Generator[None, None, None]:
        """同步事务；外层互斥（``_sync_lock``）。"""
        is_outer = not self.in_transaction
        if is_outer:
            self._sync_lock.acquire()
        token = None
        if is_outer:
            token = self._txn.set(TransactionContext())
        try:
            yield
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.COMMIT(ctx)
        except BaseException:
            if is_outer:
                ctx = self._txn.get()
                if ctx is not None:
                    self.ROLLBACK(ctx)
            raise
        finally:
            if is_outer and token is not None:
                self._txn.reset(token)
            if is_outer:
                self._sync_lock.release()

    def _register_workspace(self, unit: WorkspaceUnit) -> None:
        ctx = self._txn.get()
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

    # ──────────────── Init 事务（须嵌在普通事务内）────────────────

    @property
    def in_init_transaction(self) -> bool:
        return bool(self._init_txn.get())

    def _current_init_ctx(self) -> TransactionContext | None:
        stack = self._init_txn.get()
        return stack[-1] if stack else None

    @asynccontextmanager
    async def init_transaction(self) -> AsyncGenerator[None, None]:
        """须已在普通事务中。每次进入压入独立 ctx；结束只提交/回滚本层（可嵌套）。"""
        if not self.in_transaction:
            raise RuntimeError("init_transaction 须在 transaction 内")
        parent = self._init_txn.get()
        ctx = TransactionContext()
        token = self._init_txn.set((*(parent or ()), ctx))
        try:
            yield
            self.COMMIT_init(ctx)
        except BaseException:
            self.ROLLBACK_init(ctx)
            raise
        finally:
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

    def ROLLBACK_init(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if not isinstance(unit, type):
                unit._ROLLBACK_init()
        ctx.registered.clear()

    # ──────────────── 节点 commit 串行 ────────────────

    def in_node_commit(self, node: "ConfigNode") -> bool:
        """本 Task 是否正在对该节点 ``commit``（含同 Task 嵌套）。"""
        return id(node) in self._committing_nodes.get()

    @asynccontextmanager
    async def node_commit(self, node: "ConfigNode") -> AsyncGenerator[None, None]:
        """外层抢节点 commit 锁；同 Task 嵌套空过；释放时并入 ``_staged_pending``。"""
        nid = id(node)
        outer = not self.in_node_commit(node)
        token = None
        if outer:
            lock = node._commit_lock
            if lock is None:
                lock = asyncio.Lock()
                node._commit_lock = lock
            await lock.acquire()
            token = self._committing_nodes.set((*self._committing_nodes.get(), nid))
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
