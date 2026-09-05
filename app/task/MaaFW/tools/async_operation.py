from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def run_blocking_to_completion(
    function: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run mutating blocking work without abandoning it on cancellation.

    Project updates and isolated Python environment preparation may still be
    writing files when the awaiting task is cancelled.  Keep the worker alive
    and wait for its final state before the caller releases the project-path
    reservation.
    """

    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if worker.done() and not worker.cancelled():
            try:
                worker.result()
            except Exception:
                pass
        raise


__all__ = ["run_blocking_to_completion"]
