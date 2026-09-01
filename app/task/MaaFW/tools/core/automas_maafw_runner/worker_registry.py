from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MaaFWWorkerShutdownReport:
    """Outcome of one best-effort MaaFW worker shutdown sweep."""

    requested: int
    terminated: int
    killed: int
    errors: tuple[str, ...] = field(default_factory=tuple)


class MaaFWWorkerRegistry:
    """Process registry shared by MaaFW runner service instances.

    A plugin shutdown closes the registry before taking its worker snapshot.
    That prevents a worker racing with teardown from escaping the stop request:
    late registrations are terminated immediately and are never retained.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workers: dict[str, Any] = {}
        self._accepting_workers = True

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._workers)

    @property
    def accepting_workers(self) -> bool:
        with self._lock:
            return self._accepting_workers

    def reopen(self) -> None:
        """Allow a newly activated runner plugin to accept worker processes."""

        with self._lock:
            self._accepting_workers = True

    def register(self, worker: Any) -> str | None:
        """Register a worker, or terminate it immediately during shutdown."""

        with self._lock:
            if self._accepting_workers and _is_running(worker):
                worker_id = uuid.uuid4().hex
                self._workers[worker_id] = worker
                return worker_id

        # Do not let a process that was spawned concurrently with plugin stop
        # survive merely because the shutdown snapshot was already captured.
        _request_terminate(worker)
        return None

    def unregister(self, worker_id: str | None) -> None:
        if worker_id is None:
            return
        with self._lock:
            self._workers.pop(worker_id, None)

    async def shutdown_all(
        self,
        *,
        graceful_timeout_seconds: float = 5.0,
    ) -> MaaFWWorkerShutdownReport:
        """Terminate every active worker and clear the registry atomically.

        Shutdown is best-effort so one uncooperative child cannot prevent the
        host from completing plugin teardown.  Every worker is removed from the
        registry before it is signalled, and new workers are rejected until a
        subsequent plugin activation calls :meth:`reopen`.
        """

        with self._lock:
            self._accepting_workers = False
            workers = tuple(self._workers.items())
            self._workers.clear()

        terminated = 0
        killed = 0
        errors: list[str] = []
        for worker_id, worker in workers:
            outcome, error = await _stop_worker(
                worker,
                graceful_timeout_seconds=graceful_timeout_seconds,
            )
            if outcome == "terminated":
                terminated += 1
            elif outcome == "killed":
                killed += 1
            if error is not None:
                errors.append(f"{worker_id}: {error}")

        return MaaFWWorkerShutdownReport(
            requested=len(workers),
            terminated=terminated,
            killed=killed,
            errors=tuple(errors),
        )


def _is_running(worker: Any) -> bool:
    return getattr(worker, "returncode", None) is None


def _request_terminate(worker: Any) -> str | None:
    if not _is_running(worker):
        return None
    try:
        worker.terminate()
    except ProcessLookupError:
        return None
    except Exception as exc:  # noqa: BLE001 - worker boundary must be best-effort.
        return str(exc)
    return None


async def _stop_worker(
    worker: Any,
    *,
    graceful_timeout_seconds: float,
) -> tuple[str, str | None]:
    termination_error = _request_terminate(worker)
    if termination_error is not None:
        return "error", termination_error
    if not _is_running(worker):
        return "terminated", None

    if await _wait_for_exit(worker, graceful_timeout_seconds):
        return "terminated", None

    try:
        worker.kill()
    except ProcessLookupError:
        return "killed", None
    except Exception as exc:  # noqa: BLE001 - worker boundary must be best-effort.
        return "error", str(exc)

    if await _wait_for_exit(worker, graceful_timeout_seconds):
        return "killed", None
    return "error", "worker did not exit after terminate and kill"


async def _wait_for_exit(worker: Any, timeout_seconds: float) -> bool:
    if not _is_running(worker):
        return True
    wait = getattr(worker, "wait", None)
    if not callable(wait):
        return not _is_running(worker)

    try:
        if inspect.iscoroutinefunction(wait):
            await asyncio.wait_for(wait(), timeout=timeout_seconds)
        else:

            def blocking_wait() -> Any:
                try:
                    return wait(timeout=timeout_seconds)
                except TypeError:
                    return wait()

            await asyncio.wait_for(
                asyncio.to_thread(blocking_wait),
                timeout=timeout_seconds + 0.5,
            )
    except (asyncio.TimeoutError, TimeoutError):
        return False
    except ProcessLookupError:
        return True
    except Exception:
        return not _is_running(worker)
    return not _is_running(worker)


GLOBAL_MAAFW_WORKER_REGISTRY = MaaFWWorkerRegistry()


__all__ = [
    "GLOBAL_MAAFW_WORKER_REGISTRY",
    "MaaFWWorkerRegistry",
    "MaaFWWorkerShutdownReport",
]
