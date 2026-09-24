from __future__ import annotations

import threading
import uuid
from typing import Any


class MaaFWWorkerRegistry:
    """Process registry shared by MaaFW runner service instances."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workers: dict[str, Any] = {}

    def register(self, worker: Any) -> str | None:
        """Register a running worker; an already exited one is not retained."""

        with self._lock:
            if _is_running(worker):
                worker_id = uuid.uuid4().hex
                self._workers[worker_id] = worker
                return worker_id
        return None

    def unregister(self, worker_id: str | None) -> None:
        if worker_id is None:
            return
        with self._lock:
            self._workers.pop(worker_id, None)


def _is_running(worker: Any) -> bool:
    return getattr(worker, "returncode", None) is None


GLOBAL_MAAFW_WORKER_REGISTRY = MaaFWWorkerRegistry()


__all__ = [
    "GLOBAL_MAAFW_WORKER_REGISTRY",
    "MaaFWWorkerRegistry",
]
