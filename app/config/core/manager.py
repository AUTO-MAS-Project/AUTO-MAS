"""ConfigManager：ref 池、持久化根、事务 / 工作区、防抖落盘与明文导出。"""

from __future__ import annotations

import asyncio
import os
import threading
import weakref
from collections import deque
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, AsyncGenerator, Generator, Literal
from uuid import UUID, uuid4

from app.utils import get_logger
from app.utils import io as _utils_io

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
    """一个事务提交与回退边界；普通嵌套调用直接复用当前上下文。"""

    parent: TransactionContext | None = None
    registered: list[WorkspaceUnit] = field(default_factory=list)
    owner: ExecutionOwner = field(default_factory=execution_owner)
    scope_id: UUID = field(default_factory=uuid4)
    active: bool = True
    staged_nodes: dict[int, weakref.ReferenceType[ConfigNode]] = field(
        default_factory=dict
    )

    @property
    def is_current(self) -> bool:
        return self.active and self.owner is execution_owner()

    @property
    def root(self) -> TransactionContext:
        ctx = self
        while ctx.parent is not None:
            ctx = ctx.parent
        return ctx


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
            if col.deleted:
                raise ValueError("不能登记已删除的集合")
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
        self._require_registration(node)
        with self._execution_gate_sync():
            if node.deleted:
                raise ValueError("不能登记已删除的节点")
            if not node.is_root:
                raise ValueError("仅根节点可登记持久化文件")
            path = Path(path)
            if path.suffix.lower() not in {".yaml", ".yml"}:
                raise ValueError(f"持久化文件必须是 .yaml / .yml: {path}")
            with self._execution_condition:
                self._save_failures.pop(node.uid, None)
                self._roots[node.uid] = RootRecord(node=node, path=path)

    def _require_registration(self, node: ConfigNode) -> None:
        if node._is_workspace:
            raise ValueError("登记必须使用 live 节点")
        node._require_lifecycle_access()

    def unregister_root(self, node: ConfigNode) -> None:
        """解除 ``file=`` 持久化根登记（幂等）。

        与 ref 池 ``register_collection``（不可解除）不同：``_roots`` 允许显式摘掉，
        供插件配置等临时根在禁用后离开 ``flush`` / 防抖扫描集。
        调用方须先 ``commit`` 并完成对该根的落盘，再 unregister。
        """
        self._require_registration(node)
        with self._execution_gate_sync():
            with self._execution_condition:
                rec = self._roots.get(node.uid)
                if rec is not None and rec.node is node:
                    del self._roots[node.uid]
                    self._save_failures.pop(node.uid, None)

    def get_file(self, root: ConfigNode) -> Path | None:
        rec = self._roots.get(root.uid)
        return rec.path if rec is not None and rec.node is root else None

    def is_persist_root(self, node: ConfigNode) -> bool:
        rec = self._roots.get(node.uid)
        return rec is not None and rec.node is node

    def iter_persist_roots(self) -> Iterator[ConfigNode]:
        for rec in list(self._roots.values()):
            yield rec.node

    async def export(self, target: Path) -> None:
        """将已激活持久化根的已提交内存状态，以明文 YAML 导出到目标目录。

        不调用 flush，不修改运行文件或保存请求；忽略 UI 显隐，不含响应式字段。
        与提交共用执行入口，事务内禁止导出，避免混入未提交工作区。

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
                _utils_io.write_file(destination, payload)

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
        ctx = self.current
        return ctx.scope_id if ctx is not None else None

    def _register_staged(self, node: ConfigNode) -> None:
        ctx = self.current
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
        ctx.registered.clear()

    @asynccontextmanager
    async def transaction(
        self, *, new_boundary: bool = False
    ) -> AsyncGenerator[None, None]:
        """默认加入当前事务；新边界成功向父层合并，只有根事务发布 live。"""
        parent = self.current
        if parent is not None and not new_boundary:
            yield
            return
        need_save = False
        ctx: TransactionContext | None = None
        try:
            async with self.execution_gate() if parent is None else nullcontext():
                ctx = TransactionContext(parent=parent)
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
            if ctx is not None and parent is None:
                self._transaction_settled(need_save=need_save)

    @contextmanager
    def transaction_sync(
        self, *, new_boundary: bool = False
    ) -> Generator[None, None, None]:
        """同步等价入口；事件循环内竞争时拒绝阻塞，工作线程可以排队。"""
        parent = self.current
        if parent is not None and not new_boundary:
            yield
            return
        need_save = False
        ctx: TransactionContext | None = None
        try:
            with self._execution_gate_sync() if parent is None else nullcontext():
                ctx = TransactionContext(parent=parent)
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
            if ctx is not None and parent is None:
                self._transaction_settled(need_save=need_save)

    def _register_workspace(self, unit: WorkspaceUnit) -> None:
        ctx = self.current
        if ctx is not None and not any(item is unit for item in ctx.registered):
            ctx.registered.append(unit)

    def COMMIT(self, ctx: TransactionContext) -> bool:
        self._check_staged(ctx)
        roots: dict[UUID, RootRecord] = {}
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._COMMIT_signal(ctx)
            else:
                if ctx.parent is None:
                    record = self._roots.get(unit.root.uid)
                    if record is not None and record.node is unit.root:
                        roots[unit.root.uid] = record
                unit._COMMIT(ctx)
            if ctx.parent is not None and not any(
                item is unit for item in ctx.parent.registered
            ):
                ctx.parent.registered.append(unit)
        for record in roots.values():
            record.revision += 1
        return bool(roots)

    def ROLLBACK(self, ctx: TransactionContext) -> None:
        for unit in ctx.registered:
            if isinstance(unit, type):
                unit._ROLLBACK_signal(ctx)
            else:
                unit._ROLLBACK(ctx)

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
                _utils_io.write_file(record.path, payload)
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
