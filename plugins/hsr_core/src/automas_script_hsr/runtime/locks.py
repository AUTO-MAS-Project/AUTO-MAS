from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable


_PATH_LOCKS: dict[str, asyncio.Lock] = {}


async def acquire_external_path_locks(paths: Iterable[str | Path]) -> list[asyncio.Lock]:
    """Acquire deterministic per-upstream-root locks for one HSR run."""

    keys = sorted(
        {
            str(Path(path).expanduser().resolve()).casefold()
            for path in paths
            if str(path).strip()
        }
    )
    acquired: list[asyncio.Lock] = []
    try:
        for key in keys:
            lock = _PATH_LOCKS.setdefault(key, asyncio.Lock())
            await lock.acquire()
            acquired.append(lock)
        return acquired
    except BaseException:
        release_external_path_locks(acquired)
        raise


def release_external_path_locks(locks: Iterable[asyncio.Lock]) -> None:
    for lock in reversed(tuple(locks)):
        if lock.locked():
            lock.release()
