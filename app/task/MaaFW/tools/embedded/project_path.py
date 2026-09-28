from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
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


# 正在更新的视图（计数：手动更新整段标一次，里面的 run_view_update 再标一次）。
# 只是给「为什么拿不到预约 / 为什么现在不能更新」配文案用的旁证，不参与预约与谱系锁。
_UPDATING_PROJECT_PATHS: dict[str, int] = {}


def begin_project_updating(path: str | Path) -> str:
    """把该视图登记为「正在更新」，返回给 :func:`end_project_updating` 的键；可嵌套。"""

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        _UPDATING_PROJECT_PATHS[key] = _UPDATING_PROJECT_PATHS.get(key, 0) + 1
    return key


def end_project_updating(key: str) -> None:
    with _ACTIVE_PROJECT_PATHS_LOCK:
        remaining = _UPDATING_PROJECT_PATHS.get(key, 0) - 1
        if remaining > 0:
            _UPDATING_PROJECT_PATHS[key] = remaining
        else:
            _UPDATING_PROJECT_PATHS.pop(key, None)


@contextmanager
def mark_project_updating(path: str | Path) -> Iterator[None]:
    """在这段里把该视图登记为「正在更新」；可嵌套。"""

    key = begin_project_updating(path)
    try:
        yield
    finally:
        end_project_updating(key)


def is_project_updating(path: str | Path) -> bool:
    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        return key in _UPDATING_PROJECT_PATHS
