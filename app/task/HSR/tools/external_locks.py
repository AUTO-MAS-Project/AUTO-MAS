"""HSR 外部脚本安装目录的进程内互斥锁。

M7A 的 ``config.yaml`` 与 SRA 的用户目录都可能被多个 HSR 脚本配置
共享。旧 dev 没有插件 registry，因此用同一事件循环中的规范化路径锁
保护配置备份、外部运行和恢复，也供原生配置器 API 在 session 生命周期内
复用。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .native_control import resolve_script_path
from .sra_runtime import get_sra_app_data_dir


_PATH_LOCKS: dict[str, asyncio.Lock] = {}


class HSRExternalPathBusyError(RuntimeError):
    """一个或多个 HSR 外部脚本路径已被其他任务或配置器占用。"""


def normalize_external_path_keys(
    paths: Iterable[str | Path],
) -> tuple[str, ...]:
    """规范化、去重并排序外部路径，保证多路径获取顺序恒定。"""

    keys: set[str] = set()
    for raw_path in paths:
        if raw_path is None:
            continue
        text = str(raw_path).strip()
        if not text:
            continue
        keys.add(str(Path(text).expanduser().resolve()).casefold())
    return tuple(sorted(keys))


def resolve_external_lock_paths(
    script_config: Any,
    engines: Iterable[str] = ("SRA", "M7A"),
) -> tuple[str, ...]:
    """返回指定引擎会读写的安装根和用户配置根。

    SRA 同时修改安装目录进程以及 ``%APPDATA%/SRA`` 下的 settings/cache/
    configs；M7A 修改安装目录下的 ``config.yaml``。空路径不会出现在结果中。
    """

    paths: list[str | Path] = []
    for raw_engine in engines:
        engine = str(raw_engine or "").strip().upper()
        if engine not in {"SRA", "M7A"}:
            continue
        root = resolve_script_path(script_config, engine)
        if root:
            paths.append(root)
        if engine == "SRA" and root:
            paths.append(get_sra_app_data_dir())
    return normalize_external_path_keys(paths)


class HSRExternalPathLockLease:
    """One ownership handle for all locks acquired by an HSR operation."""

    __slots__ = ("_keys", "_locks", "_released")

    def __init__(self, keys: tuple[str, ...], locks: tuple[asyncio.Lock, ...]) -> None:
        self._keys = keys
        self._locks = locks
        self._released = False

    @property
    def keys(self) -> tuple[str, ...]:
        return self._keys

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        """释放全部路径锁；可重复调用，适合 session/finally 收尾。"""

        if self._released:
            return
        self._released = True
        for lock in reversed(self._locks):
            if lock.locked():
                lock.release()

    async def __aenter__(self) -> "HSRExternalPathLockLease":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


async def acquire_external_path_locks(
    paths: Iterable[str | Path],
    *,
    wait: bool = True,
) -> HSRExternalPathLockLease:
    """按规范化路径顺序获取一组锁。

    ``wait=False`` 用于 API 配置器等非阻塞入口：任一 key 已占用时立即
    抛出 :class:`HSRExternalPathBusyError`。获取过程中被取消时，已获取
    的前缀锁会自动释放。
    """

    keys = normalize_external_path_keys(paths)
    locks = tuple(_PATH_LOCKS.setdefault(key, asyncio.Lock()) for key in keys)
    if not wait:
        busy = [key for key, lock in zip(keys, locks, strict=True) if lock.locked()]
        if busy:
            raise HSRExternalPathBusyError(
                "HSR 原生配置器或任务正在使用外部脚本目录，请先结束当前会话"
            )

    acquired: list[asyncio.Lock] = []
    try:
        for lock in locks:
            await lock.acquire()
            acquired.append(lock)
    except BaseException:
        for lock in reversed(acquired):
            if lock.locked():
                lock.release()
        raise
    return HSRExternalPathLockLease(keys, tuple(acquired))


__all__ = [
    "HSRExternalPathBusyError",
    "HSRExternalPathLockLease",
    "acquire_external_path_locks",
    "normalize_external_path_keys",
    "resolve_external_lock_paths",
]
