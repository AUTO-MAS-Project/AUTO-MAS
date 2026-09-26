from __future__ import annotations

import os
import threading
from pathlib import Path

_ACTIVE_PROJECT_PATHS: set[str] = set()
_ACTIVE_PROJECT_PATHS_LOCK = threading.Lock()


def normalize_project_path(path: str | Path) -> str:
    """Return the process-wide key used by update and execution reservations."""

    return os.path.normcase(str(Path(path).resolve())).casefold()


async def try_reserve_project_path(path: str | Path) -> str | None:
    """Reserve a project directory without blocking the event loop.

    The critical section only mutates an in-memory set, so a process-wide
    threading lock also keeps separate event loops/worker threads consistent.
    Callers deliberately fail fast instead of waiting: AUTO-MAS already skips a
    second MaaFW run for the same external directory.
    """

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        if key in _ACTIVE_PROJECT_PATHS:
            return None
        _ACTIVE_PROJECT_PATHS.add(key)
    return key


async def release_project_path(key: str | None) -> None:
    release_project_path_sync(key)


def try_reserve_project_path_sync(path: str | Path) -> str | None:
    """同一张表的同步版：给已经在工作线程里跑的服务层代码用（它拿不到事件循环）。"""

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        if key in _ACTIVE_PROJECT_PATHS:
            return None
        _ACTIVE_PROJECT_PATHS.add(key)
    return key


def release_project_path_sync(key: str | None) -> None:
    if not key:
        return
    with _ACTIVE_PROJECT_PATHS_LOCK:
        _ACTIVE_PROJECT_PATHS.discard(key)
