"""配置变更信号：提交前 validator 与提交后 observer 分离。

- 发送者（sender）：订阅所绑定的 entry / collection；回调首参同义。
- validator：在事务工作区内执行，抛错或超时会拒绝并回滚提交。
- observer：仅在 live 状态已提交、事务锁已释放后执行；失败只记录报告。
- 守卫：发送者 deleted 由 ``emit_change`` 检查；``_wrap`` 仅对 ConfigNode 实例方法查 deleted。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from blinker import Signal

from .node import ConfigNode
from .support.logger import get_logger
from .wire import CollectionOrderItem

if TYPE_CHECKING:
    from .entry import ConfigEntry

type ConfigEvent = FieldChangeEvent | CollectionChangeEvent
type SignalCallback = Callable[..., object | Awaitable[object] | None]
type WrappedSignal = Callable[..., object | Awaitable[object] | None]
type ObserverOutcome = Literal["completed", "failed", "timed_out"]

logger = get_logger("signals")

# Validators are part of the atomic validation/ref-integrity chain. They must
# be side-effect free because a later validator can still reject the workspace.
SIGNAL_CALLBACK_TIMEOUT_SECONDS = 5.0

# Observers run after the transaction becomes irreversible. Keep them bounded
# so one integration cannot hold the caller indefinitely.
OBSERVER_CALLBACK_TIMEOUT_SECONDS = 5.0

_SIGNAL_SKIPPED = object()


class _CallbackTimeoutError(TimeoutError):
    """Deadline raised by the framework, distinct from receiver exceptions."""


def _caller_is_cancelling() -> bool:
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


@dataclass(frozen=True)
class FieldChangeEvent:
    """Entry 字段变更事件。

    加密字段只暴露 ``changed`` 与 ``encrypted``；其 ``value`` 和
    ``old_value`` 固定为 ``None``，因此事件本身可以安全交给 DTO mapper。
    """

    kind: Literal["init_set", "set"]
    node: ConfigEntry
    group: str
    field: str
    changed: bool
    encrypted: bool = False
    value: object | None = None
    old_value: object | None = None

    @property
    def config(self) -> ConfigEntry:
        """兼容别名：发送该事件的 Entry。"""
        return self.node

    @property
    def config_uid(self) -> UUID:
        return self.node.uid


@dataclass(frozen=True)
class CollectionChangeEvent:
    """Collection 结构变更事件。回调首参 ``sender`` 为发送者 Collection。"""

    kind: Literal["init_add", "add", "remove", "set_order"]
    collection: ConfigNode
    uid: UUID | None = None
    entry: ConfigNode | None = None
    old_order: list[CollectionOrderItem] | None = None
    order: list[CollectionOrderItem] | None = None


@dataclass(frozen=True)
class ObserverCallbackResult:
    """One after-commit observer outcome without exception payload leakage."""

    receiver: str
    outcome: ObserverOutcome
    error_type: str | None = None


@dataclass(frozen=True)
class AfterCommitObserverReport:
    """Structured, transport-neutral report for one committed change event."""

    transaction_id: UUID
    revision: int
    event_kind: str
    sender_uid: UUID | None
    group: str | None
    field: str | None
    results: tuple[ObserverCallbackResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(result.outcome == "completed" for result in self.results)


def _receiver_label(receiver: object) -> str:
    """Return a stable diagnostic label without calling ``repr(receiver)``."""
    function = getattr(receiver, "__func__", None)
    if function is not None:
        module = getattr(function, "__module__", type(receiver).__module__)
        qualname = getattr(function, "__qualname__", type(receiver).__qualname__)
        return f"{module}.{qualname}"
    if inspect.isfunction(receiver):
        return f"{receiver.__module__}.{receiver.__qualname__}"
    receiver_type = type(receiver)
    return f"{receiver_type.__module__}.{receiver_type.__qualname__}"


def _wrap(
    receiver_ref: Callable[[], object | None],
    phase: str,
    group: str | None,
    field: str | None,
    receiver_label: str,
) -> WrappedSignal:
    """包装用户 receiver：订阅过滤 + 有条件 deleted 守卫。

    包装函数为 **同步**（blinker 不接受协程函数作为接收者）；若 ``receiver``
    返回 awaitable，则原样返回，由 dispatcher 统一 ``await``。
    """

    def wrapper(
        sender: object,
        event: object,
        *args: object,
        **kwargs: object,
    ) -> object | Awaitable[object] | None:
        receiver = receiver_ref()
        if receiver is None:
            return _SIGNAL_SKIPPED
        if not callable(receiver):
            return _SIGNAL_SKIPPED
        inst = getattr(receiver, "__self__", None)
        if isinstance(inst, ConfigNode) and inst.deleted:
            return _SIGNAL_SKIPPED
        kind = getattr(event, "kind", "")
        is_init = kind.startswith("init_")
        if phase == "init" and not is_init:
            return _SIGNAL_SKIPPED
        if phase == "runtime" and is_init:
            return _SIGNAL_SKIPPED
        if group is not None and getattr(event, "group", None) != group:
            return _SIGNAL_SKIPPED
        if field is not None and getattr(event, "field", None) != field:
            return _SIGNAL_SKIPPED
        return receiver(sender, event, *args, **kwargs)

    setattr(wrapper, "__config_receiver_label__", receiver_label)
    return wrapper


async def _cancel_owned_awaitable(task: asyncio.Future[object]) -> None:
    """Cancel and join only an awaitable task created by this dispatcher."""
    if task.done():
        return
    task.cancel()
    try:
        await task
    except BaseException:
        pass


async def _run_owned_awaitable(awaitable: Awaitable[object]) -> object:
    """Drive one callback coroutine while shielding its awaited dependencies.

    Cancelling the dispatcher-owned task injects ``CancelledError`` into the
    callback so its ``finally`` blocks run, but does not propagate ``cancel()``
    into an existing Task/Future that the callback happens to await.
    """
    iterator = awaitable.__await__()
    send_value: object | None = None
    pending_error: BaseException | None = None

    while True:
        try:
            if pending_error is None:
                yielded = iterator.send(send_value)
            else:
                error = pending_error
                pending_error = None
                yielded = iterator.throw(error)
        except StopIteration as completed:
            return completed.value

        send_value = None
        if yielded is None:
            try:
                await asyncio.sleep(0)
            except BaseException as exc:
                pending_error = exc
            continue

        # ``Task`` normally clears this private hand-off marker before waiting
        # on a yielded Future. This small driver must do the same before it can
        # await that Future through ``shield``.
        if getattr(yielded, "_asyncio_future_blocking", False):
            setattr(yielded, "_asyncio_future_blocking", False)
        dependency = asyncio.ensure_future(yielded)
        try:
            send_value = await asyncio.shield(dependency)
        except BaseException as exc:
            pending_error = exc


async def _await_callback_result(
    result: object,
    *,
    timeout: float,
    callback_kind: str,
) -> None:
    """Await one callback result without cancelling caller-owned futures.

    Coroutine/custom awaitable results are converted into a dispatcher-owned
    task and are cancelled and joined on timeout or caller cancellation.
    Existing ``Task`` / ``Future`` instances remain owned by their creator and
    are therefore never cancelled by a configuration transaction.
    """
    if not inspect.isawaitable(result):
        return

    owns_task = not asyncio.isfuture(result)
    authorization = None
    if owns_task:
        task = asyncio.create_task(
            _run_owned_awaitable(cast(Awaitable[object], result))
        )
        from .manager import config_manager

        try:
            authorization = config_manager._authorize_callback_task(task)
        except BaseException:
            await _cancel_owned_awaitable(task)
            raise
    else:
        task = cast(asyncio.Future[object], result)

    try:
        try:
            done, _pending = await asyncio.wait((task,), timeout=timeout)
        except BaseException:
            if owns_task:
                await _cancel_owned_awaitable(task)
            raise

        if not done:
            if owns_task:
                await _cancel_owned_awaitable(task)
            raise _CallbackTimeoutError(
                f"configuration {callback_kind} timed out"
            )

        try:
            task.result()
        except asyncio.CancelledError as exc:
            # A callback returning an already-cancelled awaitable is a failed
            # callback, not cancellation of the transaction's caller.
            raise RuntimeError(
                f"configuration {callback_kind} returned a cancelled awaitable"
            ) from exc
    finally:
        if owns_task:
            config_manager._revoke_callback_task(task, authorization)


async def _dispatch_validators(
    signal: Signal, sender: ConfigNode | None, event: ConfigEvent
) -> None:
    """Run pre-commit validators sequentially and fail closed."""
    for receiver in list(signal.receivers_for(sender)):
        try:
            result = receiver(sender, event=event)
        except asyncio.CancelledError as exc:
            if _caller_is_cancelling():
                raise
            raise RuntimeError(
                "configuration validator raised CancelledError"
            ) from exc
        if result is _SIGNAL_SKIPPED:
            continue
        try:
            await _await_callback_result(
                result,
                timeout=SIGNAL_CALLBACK_TIMEOUT_SECONDS,
                callback_kind="validator",
            )
        except _CallbackTimeoutError:
            raise TimeoutError(
                "configuration pre-commit validator timed out; validators "
                "must not wait for unrelated tasks or I/O"
            ) from None


async def _dispatch_observers(
    signal: Signal,
    sender: ConfigNode | None,
    event: ConfigEvent,
    *,
    transaction_id: UUID,
    revision: int,
) -> AfterCommitObserverReport:
    """Run all after-commit observers and report failures without rollback."""
    results: list[ObserverCallbackResult] = []
    for receiver in list(signal.receivers_for(sender)):
        receiver_label = cast(
            str,
            getattr(
                receiver,
                "__config_receiver_label__",
                f"{type(receiver).__module__}.{type(receiver).__qualname__}",
            ),
        )
        try:
            result = receiver(sender, event=event)
            if result is _SIGNAL_SKIPPED:
                continue
            await _await_callback_result(
                result,
                timeout=OBSERVER_CALLBACK_TIMEOUT_SECONDS,
                callback_kind="after-commit observer",
            )
        except _CallbackTimeoutError:
            results.append(
                ObserverCallbackResult(
                    receiver=receiver_label,
                    outcome="timed_out",
                    error_type="TimeoutError",
                )
            )
            logger.warning(
                "after-commit observer timed out: transaction=%s "
                "revision=%s receiver=%s",
                transaction_id,
                revision,
                receiver_label,
            )
        except asyncio.CancelledError:
            if _caller_is_cancelling():
                raise
            error_type = "CancelledError"
            results.append(
                ObserverCallbackResult(
                    receiver=receiver_label,
                    outcome="failed",
                    error_type=error_type,
                )
            )
            logger.warning(
                "after-commit observer failed: transaction=%s "
                "revision=%s receiver=%s error=%s",
                transaction_id,
                revision,
                receiver_label,
                error_type,
            )
        except Exception as exc:
            error_type = type(exc).__name__
            results.append(
                ObserverCallbackResult(
                    receiver=receiver_label,
                    outcome="failed",
                    error_type=error_type,
                )
            )
            logger.warning(
                "after-commit observer failed: transaction=%s "
                "revision=%s receiver=%s error=%s",
                transaction_id,
                revision,
                receiver_label,
                error_type,
            )
        else:
            results.append(
                ObserverCallbackResult(
                    receiver=receiver_label,
                    outcome="completed",
                )
            )

    return AfterCommitObserverReport(
        transaction_id=transaction_id,
        revision=revision,
        event_kind=event.kind,
        sender_uid=sender.uid if sender is not None else None,
        group=getattr(event, "group", None),
        field=getattr(event, "field", None),
        results=tuple(results),
    )
