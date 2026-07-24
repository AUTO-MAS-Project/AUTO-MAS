"""Config v2 transaction, registry, and persistence coordination."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable, Iterator
from uuid import UUID, uuid4

from .errors import ConfigAggregateError
from .node_state import NodeState
from .support.logger import get_logger
from .wire import write_wire_toml

if TYPE_CHECKING:
    from .collection import ConfigCollection
    from .node import ConfigNode
    from .signals import AfterCommitObserverReport

logger = get_logger("manager")

type WorkspaceUnit = ConfigNode | type[ConfigNode]
type TransactionLifecycleHook = Callable[[UUID], Awaitable[None]]
type PrepareCommitHook = Callable[[UUID], Awaitable[None]]
type AfterCommitDispatch = Callable[
    [UUID, int], Awaitable[AfterCommitObserverReport]
]


class TransactionOutcome(str, Enum):
    """Irreversible outcome of one transaction workspace."""

    PENDING = "pending"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


def _current_task() -> asyncio.Task[object] | None:
    """Return the current task without requiring a running event loop."""
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


@dataclass
class TransactionContext:
    """Workspace journal owned by exactly one asyncio task."""

    registered: list[WorkspaceUnit] = field(default_factory=list)
    owner_task: asyncio.Task[object] | None = field(
        default_factory=_current_task,
        repr=False,
    )
    transaction_id: UUID = field(default_factory=uuid4)
    revision: int = 0
    outcome: TransactionOutcome = TransactionOutcome.PENDING
    after_commit_dispatches: list[AfterCommitDispatch] = field(
        default_factory=list,
        repr=False,
    )
    observer_reports: list[AfterCommitObserverReport] = field(
        default_factory=list,
    )
    delegated_tasks: set[asyncio.Task[object]] = field(
        default_factory=set,
        repr=False,
    )
    preparing_commit: bool = field(default=False, repr=False)

    def assert_owner(self) -> None:
        """Reject a context copied into a child task."""
        current = _current_task()
        if current is not self.owner_task and current not in self.delegated_tasks:
            raise RuntimeError(
                "configuration transaction context belongs to another task; "
                "child tasks must start an independent transaction"
            )

    @property
    def committed(self) -> bool:
        return self.outcome == TransactionOutcome.COMMITTED

    @property
    def rolled_back(self) -> bool:
        return self.outcome == TransactionOutcome.ROLLED_BACK

    def mark_outcome(self, outcome: TransactionOutcome) -> None:
        """Set the one-way transaction outcome exactly once."""
        if outcome == TransactionOutcome.PENDING:
            raise ValueError("transaction outcome cannot return to pending")
        if self.outcome != TransactionOutcome.PENDING:
            if self.outcome != outcome:
                raise RuntimeError(
                    f"transaction outcome is already {self.outcome.value}"
                )
            return
        self.outcome = outcome


@dataclass(frozen=True)
class NodeCommitFrame:
    node_id: int
    owner_task: asyncio.Task[object] | None = field(
        default_factory=_current_task,
        repr=False,
    )
    delegated_tasks: set[asyncio.Task[object]] = field(
        default_factory=set,
        repr=False,
        compare=False,
    )

    def assert_owner(self) -> None:
        current = _current_task()
        if current is not self.owner_task and current not in self.delegated_tasks:
            raise RuntimeError(
                "configuration node-commit context belongs to another task; "
                "child tasks must not reuse the parent commit frame"
            )


@dataclass
class RootRecord:
    node: ConfigNode
    path: Path
    owner: str | None = None
    generation: str | None = None


@dataclass
class CollectionRecord:
    collection: ConfigCollection
    owner: str | None = None
    generation: str | None = None


class ConfigManager:
    """Coordinate Config v2 state without allowing cross-task context reuse."""

    def __init__(self) -> None:
        self._collections: dict[str, CollectionRecord] = {}
        self._roots: dict[UUID, RootRecord] = {}
        self._root_paths: dict[str, UUID] = {}
        self._txn: ContextVar[TransactionContext | None] = ContextVar(
            "app_configuration_txn",
            default=None,
        )
        self._init_txn: ContextVar[tuple[TransactionContext, ...] | None] = (
            ContextVar("app_configuration_init_txn", default=None)
        )
        self._committing_nodes: ContextVar[tuple[NodeCommitFrame, ...]] = (
            ContextVar("app_configuration_committing", default=())
        )
        self._txn_lock: asyncio.Lock | None = None
        self._txn_lock_loop: asyncio.AbstractEventLoop | None = None
        self._sync_lock = threading.RLock()
        self._async_transaction_owner: asyncio.Task[object] | None = None
        self._save_lock: asyncio.Lock | None = None
        self._save_lock_loop: asyncio.AbstractEventLoop | None = None
        self._save_handle: asyncio.Task[None] | None = None
        self._save_generation = 0
        self._debounce_seconds = 0.05
        self._prepare_commit_hook: PrepareCommitHook | None = None
        self._post_commit_hook: TransactionLifecycleHook | None = None
        self._post_rollback_hook: TransactionLifecycleHook | None = None
        self._transaction_revision = 0

    def _next_transaction_revision(self) -> int:
        """Allocate a process-local, monotonically increasing commit order."""
        self._transaction_revision += 1
        return self._transaction_revision

    @staticmethod
    def _lock_for_running_loop(
        lock: asyncio.Lock | None,
        bound_loop: asyncio.AbstractEventLoop | None,
        *,
        operation: str,
    ) -> tuple[asyncio.Lock, asyncio.AbstractEventLoop]:
        """Return a lock usable by this loop, recreating only while idle."""
        loop = asyncio.get_running_loop()
        if lock is None or bound_loop is loop:
            return lock or asyncio.Lock(), loop
        if lock.locked():
            raise RuntimeError(
                f"{operation} is active on a different asyncio event loop"
            )
        return asyncio.Lock(), loop

    # Collections and persistence roots

    def register_collection(
        self,
        name: str,
        col: ConfigCollection,
        *,
        owner: str | None = None,
        generation: str | None = None,
    ) -> None:
        if name in self._collections:
            raise ValueError(f"Collection name already registered: {name}")
        if self.is_registered_collection(col):
            raise ValueError("Collection instance is already registered")
        self._collections[name] = CollectionRecord(
            collection=col,
            owner=owner,
            generation=generation,
        )

    def get_collection(self, name: str) -> ConfigCollection:
        try:
            return self._collections[name].collection
        except KeyError as exc:
            raise LookupError(f"ref target is not registered: {name}") from exc

    def is_registered_collection(self, col: ConfigNode) -> bool:
        from .collection import ConfigCollection

        return isinstance(col, ConfigCollection) and any(
            record.collection is col for record in self._collections.values()
        )

    def register_root(
        self,
        node: ConfigNode,
        path: Path,
        *,
        owner: str | None = None,
        generation: str | None = None,
    ) -> None:
        path = Path(path).resolve(strict=False)
        if path.suffix.lower() != ".toml":
            raise ValueError(f"persistent config file must use .toml: {path}")
        path_key = self._root_path_key(path)
        existing = self._roots.get(node.uid)
        if existing is not None and existing.node is not node:
            raise ValueError(f"a different root already uses uid {node.uid}")
        path_owner = self._root_paths.get(path_key)
        if path_owner is not None and path_owner != node.uid:
            raise ValueError(
                "persistent config path is already registered: "
                f"path={path}, uid={path_owner}"
            )
        if existing is not None:
            old_key = self._root_path_key(existing.path)
            if old_key != path_key and self._root_paths.get(old_key) == node.uid:
                self._root_paths.pop(old_key, None)
        self._roots[node.uid] = RootRecord(
            node=node,
            path=path,
            owner=owner,
            generation=generation,
        )
        self._root_paths[path_key] = node.uid

    @staticmethod
    def _root_path_key(path: Path) -> str:
        """Normalize relative/absolute and Windows case aliases."""
        return os.path.normcase(str(Path(path).resolve(strict=False)))

    def get_file(self, root: ConfigNode) -> Path | None:
        record = self._roots.get(root.uid)
        return record.path if record is not None and record.node is root else None

    def is_persist_root(self, node: ConfigNode) -> bool:
        record = self._roots.get(node.uid)
        return record is not None and record.node is node

    def iter_persist_roots(self) -> Iterator[ConfigNode]:
        for record in list(self._roots.values()):
            yield record.node

    def unregister_root(self, node: ConfigNode) -> None:
        """Unregister one root without cancelling saves for unrelated roots."""
        record = self._roots.get(node.uid)
        if record is not None and record.node is node:
            self._roots.pop(node.uid, None)
            path_key = self._root_path_key(record.path)
            if self._root_paths.get(path_key) == node.uid:
                self._root_paths.pop(path_key, None)

    def unregister_collection(self, name: str) -> None:
        self._collections.pop(name, None)

    def disconnect_owner(self, owner: str, *, generation: str | None = None) -> None:
        """Remove registrations explicitly owned by one plugin generation.

        Callers must flush the owner before invoking this synchronous registry
        operation. Registration ownership is metadata, not a name-prefix guess.
        """
        collection_names = [
            name
            for name, record in self._collections.items()
            if record.owner == owner
            and (generation is None or record.generation == generation)
        ]
        for name in collection_names:
            self.unregister_collection(name)

        roots = [
            record.node
            for record in self._roots.values()
            if record.owner == owner
            and (generation is None or record.generation == generation)
        ]
        for root in roots:
            self.unregister_root(root)

    async def dispose_node(self, node: ConfigNode) -> None:
        """Flush a node before removing its registry entries."""
        if (
            self.is_persist_root(node)
            and node.activation_state == NodeState.ACTIVE
            and not node.deleted
        ):
            await self.flush()

        for name, record in list(self._collections.items()):
            if record.collection is node:
                self.unregister_collection(name)
        self.unregister_root(node)

    # Transactions

    def configure_transaction_hooks(
        self,
        *,
        post_commit: TransactionLifecycleHook | None,
        post_rollback: TransactionLifecycleHook | None,
    ) -> None:
        """Install transport-neutral async hooks for outer transactions."""
        self._post_commit_hook = post_commit
        self._post_rollback_hook = post_rollback

    def configure_prepare_commit_hook(
        self,
        prepare_commit: PrepareCommitHook | None,
    ) -> None:
        """Install the durable pre-commit hook independently of WS hooks."""
        self._prepare_commit_hook = prepare_commit

    @staticmethod
    def _transaction_has_changes(context: TransactionContext) -> bool:
        """Return whether a transaction owns at least one node workspace."""
        return any(not isinstance(unit, type) for unit in context.registered)

    @staticmethod
    def _assert_transaction_ready(context: TransactionContext) -> None:
        context.assert_owner()
        if context.delegated_tasks:
            raise RuntimeError(
                "configuration callback task delegation leaked before commit"
            )

    async def _run_prepare_commit_hook(
        self,
        context: TransactionContext,
    ) -> None:
        """Await durable preparation while live state and locks remain intact."""
        hook = self._prepare_commit_hook
        if hook is None or not self._transaction_has_changes(context):
            return
        self._assert_transaction_ready(context)
        context.preparing_commit = True
        try:
            await hook(context.transaction_id)
        finally:
            context.preparing_commit = False

    async def _run_transaction_hook(
        self,
        hook: TransactionLifecycleHook | None,
        transaction_id: UUID,
        *,
        operation: str,
    ) -> None:
        if hook is None:
            return
        try:
            await hook(transaction_id)
        except Exception as exc:
            # The live config has already committed/rolled back. Transport
            # failure must neither reverse it nor hide the original error.
            logger.warning(
                "post-%s hook failed for transaction %s: %s",
                operation,
                transaction_id,
                exc,
            )

    def enqueue_after_commit(self, dispatch: AfterCommitDispatch) -> None:
        """Queue one observer dispatch on the current outer transaction."""
        context = self.current
        if context is None:
            raise RuntimeError(
                "after-commit observer dispatch requires an active transaction"
            )
        context.after_commit_dispatches.append(dispatch)

    async def _run_after_commit_observers(
        self,
        context: TransactionContext,
    ) -> None:
        """Dispatch committed observations after all transaction locks release."""
        dispatches = list(context.after_commit_dispatches)
        context.after_commit_dispatches.clear()
        for dispatch in dispatches:
            try:
                report = await dispatch(
                    context.transaction_id,
                    context.revision,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Dispatch infrastructure errors are isolated just like user
                # observer failures; live configuration is already committed.
                logger.warning(
                    "after-commit dispatch failed for transaction %s: %s",
                    context.transaction_id,
                    type(exc).__name__,
                )
            else:
                context.observer_reports.append(report)

    @property
    def current(self) -> TransactionContext | None:
        context = self._txn.get()
        if context is not None:
            context.assert_owner()
        return context

    @property
    def in_transaction(self) -> bool:
        return self.current is not None

    def _authorize_callback_task(
        self,
        task: asyncio.Task[object],
    ) -> tuple[TransactionContext, tuple[NodeCommitFrame, ...]] | None:
        """Temporarily delegate the current transaction to one owned callback.

        The dispatcher must synchronously await and revoke this task. Existing
        caller-owned Tasks/Futures never enter this path.
        """
        context = self._txn.get()
        if context is None:
            return None
        context.assert_owner()
        frames = self._committing_nodes.get()
        for frame in frames:
            frame.assert_owner()
        context.delegated_tasks.add(task)
        for frame in frames:
            frame.delegated_tasks.add(task)
        return context, frames

    @staticmethod
    def _revoke_callback_task(
        task: asyncio.Task[object],
        authorization: tuple[
            TransactionContext,
            tuple[NodeCommitFrame, ...],
        ]
        | None,
    ) -> None:
        if authorization is None:
            return
        context, frames = authorization
        context.delegated_tasks.discard(task)
        for frame in frames:
            frame.delegated_tasks.discard(task)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        """Open an atomic workspace transaction for the current task."""
        existing = self._txn.get()
        if existing is not None:
            existing.assert_owner()
            yield existing
            return
        if self._async_transaction_owner is _current_task():
            raise RuntimeError(
                "configuration transaction cannot start inside the "
                "snapshot barrier"
            )

        txn_lock, txn_loop = self._lock_for_running_loop(
            self._txn_lock,
            self._txn_lock_loop,
            operation="configuration transaction",
        )
        self._txn_lock = txn_lock
        self._txn_lock_loop = txn_loop
        await txn_lock.acquire()
        self._sync_lock.acquire()
        self._async_transaction_owner = _current_task()
        context = TransactionContext(revision=self._next_transaction_revision())
        token = self._txn.set(context)
        committed = False
        rolled_back = False
        try:
            yield context
            self._assert_transaction_ready(context)
            await self._run_prepare_commit_hook(context)
            self.COMMIT(context)
            committed = True
        except BaseException:
            rolled_back = True
            self.ROLLBACK(context)
            raise
        finally:
            self._txn.reset(token)
            self._async_transaction_owner = None
            self._sync_lock.release()
            txn_lock.release()
            if committed:
                await self._run_transaction_hook(
                    self._post_commit_hook,
                    context.transaction_id,
                    operation="commit",
                )
                await self._run_after_commit_observers(context)
            elif rolled_back:
                await self._run_transaction_hook(
                    self._post_rollback_hook,
                    context.transaction_id,
                    operation="rollback",
                )

    @asynccontextmanager
    async def snapshot_barrier(self) -> AsyncIterator[None]:
        """Hold a stable all-root view across capture and durable publication.

        The barrier shares the transaction locks but does not create a
        transaction workspace or allocate a revision.  It must remain outside
        every live transaction so callers cannot publish uncommitted state.
        """
        if self._txn.get() is not None:
            raise RuntimeError(
                "configuration snapshot barrier cannot run inside a "
                "transaction"
            )
        if self._async_transaction_owner is _current_task():
            raise RuntimeError(
                "configuration snapshot barrier is not re-entrant"
            )

        txn_lock, txn_loop = self._lock_for_running_loop(
            self._txn_lock,
            self._txn_lock_loop,
            operation="configuration snapshot barrier",
        )
        self._txn_lock = txn_lock
        self._txn_lock_loop = txn_loop
        await txn_lock.acquire()

        sync_acquired = False
        owner = _current_task()
        try:
            self._sync_lock.acquire()
            sync_acquired = True
            self._async_transaction_owner = owner
            yield
        finally:
            if self._async_transaction_owner is owner:
                self._async_transaction_owner = None
            if sync_acquired:
                self._sync_lock.release()
            txn_lock.release()

    @contextmanager
    def transaction_sync(self) -> Iterator[TransactionContext]:
        """Open a synchronous transaction and reject copied task contexts."""
        existing = self._txn.get()
        if existing is not None:
            existing.assert_owner()
            yield existing
            return

        # ``threading.RLock`` is re-entrant by OS thread, not asyncio Task.
        # Without this guard another Task on the same event-loop thread can
        # enter here while an async transaction is suspended and observe a
        # second live workspace transaction.  Sync callers cannot wait for an
        # asyncio lock safely, so reject the unsupported overlap immediately.
        if self._async_transaction_owner is not None:
            raise RuntimeError(
                "synchronous configuration transaction cannot overlap an "
                "active asynchronous transaction"
            )

        self._sync_lock.acquire()
        context = TransactionContext(revision=self._next_transaction_revision())
        token = self._txn.set(context)
        try:
            yield context
            if (
                self._prepare_commit_hook is not None
                and self._transaction_has_changes(context)
            ):
                raise RuntimeError(
                    "synchronous configuration transaction cannot commit "
                    "while an async prepare-commit hook is configured"
                )
            self.COMMIT(context)
        except BaseException:
            self.ROLLBACK(context)
            raise
        finally:
            self._txn.reset(token)
            self._sync_lock.release()

    def _register_workspace(self, unit: WorkspaceUnit) -> None:
        context = self.current
        if context is None:
            return
        if not any(registered is unit for registered in context.registered):
            context.registered.append(unit)

    def COMMIT(self, context: TransactionContext) -> None:
        self._assert_transaction_ready(context)
        registered = list(context.registered)
        for unit in registered:
            if isinstance(unit, type):
                unit._COMMIT_signal()
            else:
                unit._COMMIT()

        need_save = any(
            not isinstance(unit, type)
            and isinstance(unit, ConfigNode)
            and self.is_persist_root(unit.root)
            for unit in registered
        )
        context.registered.clear()
        if need_save:
            self.schedule_debounced_save()
        context.mark_outcome(TransactionOutcome.COMMITTED)

    def ROLLBACK(self, context: TransactionContext) -> None:
        context.assert_owner()
        context.preparing_commit = False
        for unit in context.registered:
            if isinstance(unit, type):
                unit._ROLLBACK_signal()
            else:
                unit._ROLLBACK()
        context.registered.clear()
        context.after_commit_dispatches.clear()
        context.delegated_tasks.clear()
        context.mark_outcome(TransactionOutcome.ROLLED_BACK)

    # Init transactions

    def _init_stack(self) -> tuple[TransactionContext, ...]:
        stack = self._init_txn.get() or ()
        for context in stack:
            context.assert_owner()
        return stack

    @property
    def in_init_transaction(self) -> bool:
        return bool(self._init_stack())

    def _current_init_ctx(self) -> TransactionContext | None:
        stack = self._init_stack()
        return stack[-1] if stack else None

    @asynccontextmanager
    async def init_transaction(self) -> AsyncIterator[TransactionContext]:
        if not self.in_transaction:
            raise RuntimeError("init_transaction must run inside transaction")
        parent = self._init_stack()
        context = TransactionContext()
        token = self._init_txn.set((*parent, context))
        try:
            yield context
            self.COMMIT_init(context)
        except BaseException:
            self.ROLLBACK_init(context)
            raise
        finally:
            self._init_txn.reset(token)

    def _register_init_workspace(self, node: ConfigNode) -> None:
        context = self._current_init_ctx()
        if context is None:
            return
        if not any(registered is node for registered in context.registered):
            context.registered.append(node)

    def COMMIT_init(self, context: TransactionContext) -> None:
        context.assert_owner()
        for unit in context.registered:
            if not isinstance(unit, type):
                unit._COMMIT_init()
        context.registered.clear()
        context.mark_outcome(TransactionOutcome.COMMITTED)

    def ROLLBACK_init(self, context: TransactionContext) -> None:
        context.assert_owner()
        for unit in context.registered:
            if not isinstance(unit, type):
                unit._ROLLBACK_init()
        context.registered.clear()
        context.mark_outcome(TransactionOutcome.ROLLED_BACK)

    # Per-node commit serialization

    def _commit_stack(self) -> tuple[NodeCommitFrame, ...]:
        stack = self._committing_nodes.get()
        for frame in stack:
            frame.assert_owner()
        return stack

    def in_node_commit(self, node: ConfigNode) -> bool:
        return any(frame.node_id == id(node) for frame in self._commit_stack())

    @asynccontextmanager
    async def node_commit(self, node: ConfigNode) -> AsyncIterator[None]:
        if not self.in_transaction:
            raise RuntimeError("node_commit must run inside transaction")
        stack = self._commit_stack()
        outer = not any(frame.node_id == id(node) for frame in stack)
        token = None
        lock: asyncio.Lock | None = None
        if outer:
            lock = node._commit_lock
            loop = asyncio.get_running_loop()
            if lock is None or node._commit_lock_loop is not loop:
                if lock is not None and lock.locked():
                    raise RuntimeError(
                        "configuration node commit is active on a different "
                        "asyncio event loop"
                    )
                lock = asyncio.Lock()
                node._commit_lock = lock
                node._commit_lock_loop = loop
            await lock.acquire()
            token = self._committing_nodes.set(
                (*stack, NodeCommitFrame(node_id=id(node)))
            )
        try:
            yield
        finally:
            if outer:
                if token is not None:
                    self._committing_nodes.reset(token)
                if lock is not None and lock.locked():
                    lock.release()

    # Debounced persistence

    def schedule_debounced_save(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        self._save_generation += 1
        if self._save_handle is not None and not self._save_handle.done():
            return

        async def debounce_then_save() -> None:
            try:
                while True:
                    generation = self._save_generation
                    await asyncio.sleep(self._debounce_seconds)
                    if generation != self._save_generation:
                        continue
                    await self._debounced_save_impl()
                    if generation == self._save_generation:
                        return
            finally:
                if self._save_handle is asyncio.current_task():
                    self._save_handle = None

        task = loop.create_task(debounce_then_save())
        self._save_handle = task

        def consume_failure(completed: asyncio.Task[None]) -> None:
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.error("debounced config save failed", exc_info=error)

        task.add_done_callback(consume_failure)

    async def _write_all_roots(self) -> None:
        errors: list[Exception] = []
        for root in self.iter_persist_roots():
            # Registration precedes activation so a failed activation can be
            # retried against the same file.  Such a root has no exportable
            # effective state yet and must not poison shutdown/flush for the
            # healthy roots in the same manager.
            if root.activation_state != NodeState.ACTIVE or root.deleted:
                continue
            path = self.get_file(root)
            if path is None:
                continue
            try:
                payload = await root.to_dict(if_decrypt=False)
                write_wire_toml(path, payload)
            except Exception:
                # Aggregate only registry identity.  Underlying serializer or
                # validator errors may retain sensitive configuration input.
                errors.append(
                    RuntimeError(
                        "configuration root persistence failed: "
                        f"uid={root.uid}, path={path}"
                    )
                )
        if errors:
            raise ConfigAggregateError(errors)

    async def _debounced_save_impl(self) -> None:
        save_lock, save_loop = self._lock_for_running_loop(
            self._save_lock,
            self._save_lock_loop,
            operation="configuration persistence",
        )
        self._save_lock = save_lock
        self._save_lock_loop = save_loop
        async with save_lock:
            await self._write_all_roots()

    async def flush(self) -> None:
        """Cancel and await debounce work, then durably write all roots."""
        task = self._save_handle
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("retrying after debounced save failure: %s", exc)
            finally:
                if self._save_handle is task:
                    self._save_handle = None
        await self._debounced_save_impl()


config_manager = ConfigManager()

# Runtime import after class construction avoids the manager/node cycle.
from .node import ConfigNode  # noqa: E402
