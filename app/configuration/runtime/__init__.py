"""Runtime transaction facade and transport-neutral post-commit hooks."""

from __future__ import annotations

import contextvars
import copy
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol
from uuid import UUID

from pydantic_core import to_jsonable_python

from ..v2.manager import TransactionContext, config_manager
from ..v2.support.logger import get_logger

logger = get_logger("runtime")

type OutboxHook = Callable[[str], Awaitable[None]]

if TYPE_CHECKING:
    from ..v2.signals import FieldChangeEvent


class OutboxEnqueueHook(Protocol):
    """Narrow shape implemented by the core-owned WS publisher."""

    def __call__(
        self,
        id: str,
        type: str,
        data: dict[str, Any],
        *,
        transaction_id: str | None = None,
    ) -> Awaitable[None]: ...


CONFIG_CHANGED = "config.changed"

_current_transaction: contextvars.ContextVar[RuntimeTransactionContext | None] = (
    contextvars.ContextVar("auto_mas_config_runtime_transaction", default=None)
)
_enqueue_outbox: OutboxEnqueueHook | None = None
_flush_outbox: OutboxHook | None = None
_discard_outbox: OutboxHook | None = None


class RuntimeTransactionContext:
    """Transport-facing view of the Manager-owned transaction context."""

    def __init__(self, manager_context: TransactionContext) -> None:
        self._manager_context = manager_context

    @property
    def owner_task(self):
        return self._manager_context.owner_task

    @property
    def transaction_id(self) -> UUID:
        return self._manager_context.transaction_id

    def assert_owner(self) -> None:
        self._manager_context.assert_owner()


def configure_outbox_hooks(
    *,
    enqueue: OutboxEnqueueHook | None = None,
    flush: OutboxHook | None = None,
    discard: OutboxHook | None = None,
) -> None:
    """Inject core-owned outbox operations without importing ``app.core``."""
    global _enqueue_outbox, _flush_outbox, _discard_outbox
    _enqueue_outbox = enqueue
    _flush_outbox = flush
    _discard_outbox = discard
    config_manager.configure_transaction_hooks(
        post_commit=_flush_transaction if flush is not None else None,
        post_rollback=_discard_transaction if discard is not None else None,
    )


async def _run_outbox_hook(
    hook: OutboxHook | None,
    transaction_id: UUID,
    *,
    operation: str,
) -> None:
    if hook is None:
        return
    try:
        await hook(str(transaction_id))
    except Exception as exc:
        # Config state is already committed/rolled back. Transport failure must
        # not reverse it or hide the original transaction exception.
        logger.warning("outbox %s failed for %s: %s", operation, transaction_id, exc)


async def _flush_transaction(transaction_id: UUID) -> None:
    await _run_outbox_hook(
        _flush_outbox,
        transaction_id,
        operation="flush",
    )


async def _discard_transaction(transaction_id: UUID) -> None:
    await _run_outbox_hook(
        _discard_outbox,
        transaction_id,
        operation="discard",
    )


async def enqueue_field_change(event: FieldChangeEvent) -> bool:
    """Queue one stable ``config.changed`` event in the exact config txn.

    The explicit transaction ID prevents the WS layer from falling back to a
    task-derived bucket when no ``RuntimeTransactionContext`` facade is active.
    """
    hook = _enqueue_outbox
    manager_context = config_manager.current
    if hook is None or manager_context is None:
        return False

    runtime_context = _current_transaction.get()
    if runtime_context is not None:
        runtime_context.assert_owner()
        if runtime_context.transaction_id != manager_context.transaction_id:
            raise RuntimeError("runtime and manager transaction IDs do not match")

    transaction_id = str(manager_context.transaction_id)
    try:
        root_id = str(event.node.root.uid)
        data: dict[str, Any] = {
            "rootId": root_id,
            "nodeId": str(event.node.uid),
            "group": event.group,
            "field": event.field,
            "changed": bool(event.changed),
            "encrypted": bool(event.encrypted),
            "transactionId": transaction_id,
            "revision": manager_context.revision,
        }
        if not event.encrypted:
            data["oldValue"] = to_jsonable_python(event.old_value)
            data["value"] = to_jsonable_python(event.value)
        await hook(
            root_id,
            CONFIG_CHANGED,
            data,
            transaction_id=transaction_id,
        )
    except Exception as exc:
        # WS availability is not part of configuration consistency.
        logger.warning(
            "outbox enqueue failed for transaction %s: %s",
            transaction_id,
            exc,
        )
        return False
    return True


@asynccontextmanager
async def transaction() -> AsyncIterator[RuntimeTransactionContext]:
    """Open one runtime transaction; nested calls share its transaction ID."""
    existing = _current_transaction.get()
    if existing is not None:
        existing.assert_owner()
        yield existing
        return

    async with config_manager.transaction() as manager_context:
        context = RuntimeTransactionContext(manager_context)
        token = _current_transaction.set(context)
        try:
            yield context
        finally:
            _current_transaction.reset(token)


def get_current_transaction() -> RuntimeTransactionContext | None:
    context = _current_transaction.get()
    if context is not None:
        context.assert_owner()
    return context


class ConfigNodeDTO:
    """A defensive transport DTO; callers must provide already-safe values."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = copy.deepcopy(data)

    def to_dict(self) -> dict[str, Any]:
        return {"data": copy.deepcopy(self._data)}


def sanitize_field_event(
    field_name: str,
    old_value: Any,
    new_value: Any,
    *,
    is_encrypted: bool = False,
) -> dict[str, Any]:
    """Build a transport-safe field delta."""
    if is_encrypted:
        # Do not invoke EncryptedValue equality here: it decrypts.  The
        # transport only needs a change bit and must never retain either value.
        old_ciphertext = getattr(old_value, "ciphertext", lambda: old_value)()
        new_ciphertext = getattr(new_value, "ciphertext", lambda: new_value)()
        return {
            "field": field_name,
            "changed": old_ciphertext != new_ciphertext,
            "encrypted": True,
        }
    changed = old_value != new_value
    return {
        "field": field_name,
        "changed": changed,
        "encrypted": False,
        "old_value": old_value,
        "new_value": new_value,
    }


async def shutdown_runtime() -> None:
    """Durably flush Config v2; failures propagate to the lifecycle owner."""
    await config_manager.flush()
    logger.info("config flush completed")


__all__ = [
    "CONFIG_CHANGED",
    "ConfigNodeDTO",
    "OutboxEnqueueHook",
    "RuntimeTransactionContext",
    "configure_outbox_hooks",
    "enqueue_field_change",
    "get_current_transaction",
    "sanitize_field_event",
    "shutdown_runtime",
    "transaction",
]
