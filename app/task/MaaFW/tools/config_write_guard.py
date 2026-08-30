from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from weakref import WeakValueDictionary


@dataclass
class _ActiveWrite:
    script_id: str
    owner: str
    parent: _ActiveWrite | None = None
    released: bool = False


_ACTIVE_WRITE: ContextVar[_ActiveWrite | None] = ContextVar(
    "maafw_active_config_write", default=None
)
_WRITE_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


class MaaFWConfigCorruptionError(RuntimeError):
    """Raised when a v1 snapshot/journal cannot be trusted."""


@dataclass(frozen=True)
class MaaFWConfigSnapshot:
    path: str
    revision: str
    payload: dict


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_active_write() -> _ActiveWrite | None:
    """Skip released frames left behind in a copied Context."""

    active = _ACTIVE_WRITE.get()
    visible = active
    while visible is not None and visible.released:
        visible = visible.parent
    if visible is not active:
        _ACTIVE_WRITE.set(visible)
    return visible


def read_maafw_config_snapshot(path: str | os.PathLike[str]) -> MaaFWConfigSnapshot:
    """Read a JSON v1 snapshot; malformed data fails closed."""

    target = os.fspath(path)
    try:
        with open(target, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaaFWConfigCorruptionError(f"MaaFW 配置快照不可读取: {target}") from exc
    if not isinstance(payload, dict):
        raise MaaFWConfigCorruptionError("MaaFW 配置快照根节点必须是对象")
    return MaaFWConfigSnapshot(path=target, revision=_digest(payload), payload=payload)


def atomic_write_maafw_config(
    path: str | os.PathLike[str],
    payload: dict,
    *,
    expected_revision: str | None = None,
    journal: bool = True,
) -> MaaFWConfigSnapshot:
    """Atomically write a v1 JSON object with optional CAS and journal."""

    if not isinstance(payload, dict):
        raise TypeError("MaaFW 配置只能写入对象")
    target = os.path.abspath(os.fspath(path))
    parent = os.path.dirname(target) or os.curdir
    os.makedirs(parent, exist_ok=True)
    try:
        current = read_maafw_config_snapshot(target) if os.path.exists(target) else None
    except MaaFWConfigCorruptionError:
        # Never overwrite an unreadable live record; an operator must recover it.
        raise
    if expected_revision is not None and (current is None or current.revision != expected_revision):
        raise RuntimeError("MaaFW 配置版本已变化，请刷新后重试")

    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        if journal:
            journal_path = f"{target}.journal"
            with open(journal_path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            directory_fd = -1
        if directory_fd >= 0:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return MaaFWConfigSnapshot(path=target, revision=_digest(payload), payload=dict(payload))


@asynccontextmanager
async def maafw_config_write_scope(
    script_id: str,
    *,
    owner: str | None = None,
    fail_if_busy: bool = False,
) -> AsyncIterator[None]:
    """Serialize MaaFW-only writes without changing other Config semantics."""

    normalized_id = str(script_id)
    active = _get_active_write()
    if active is not None and active.script_id == normalized_id:
        yield
        return

    lock = _WRITE_LOCKS.setdefault(normalized_id, asyncio.Lock())
    if fail_if_busy and lock.locked():
        raise RuntimeError("MaaFW 配置正在被其他操作修改，请刷新后重试")
    await lock.acquire()
    state = _ActiveWrite(
        script_id=normalized_id,
        owner=owner or uuid.uuid4().hex,
        parent=active,
    )
    _ACTIVE_WRITE.set(state)
    try:
        yield
    finally:
        state.released = True
        try:
            if _ACTIVE_WRITE.get() is state:
                _ACTIVE_WRITE.set(state.parent)
        finally:
            lock.release()


__all__ = [
    "MaaFWConfigCorruptionError",
    "MaaFWConfigSnapshot",
    "atomic_write_maafw_config",
    "maafw_config_write_scope",
    "read_maafw_config_snapshot",
]
