"""Windows 进程会话的归属核验。"""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

_parent_scope: Callable[[], int | None] | None = None


@dataclass(frozen=True)
class DesktopProcessTarget:
    session_id: int
    source: Path
    root: Path


desktop_process_target: ContextVar[DesktopProcessTarget | None] = ContextVar(
    "desktop_process_target", default=None
)


def configure_parent_scope(resolve: Callable[[], int | None]) -> None:
    global _parent_scope
    _parent_scope = resolve


def desktop_process_session_id() -> int | None:
    """返回当前任务选定的分身会话；主桌面操作返回 None。"""
    target = desktop_process_target.get()
    return target.session_id if target is not None else None


def restricted_session() -> int | None:
    session_id = desktop_process_session_id()
    if session_id is not None:
        return session_id
    return _parent_scope() if _parent_scope is not None else None


def process_in_scope(pid: int) -> bool:
    return matches_session(pid, restricted_session())


def matches_session(pid: int, session_id: int | None) -> bool:
    if session_id is None:
        return True
    from app.utils.windows.desktop_session.native import process_session

    try:
        return process_session(pid) == session_id
    except OSError:
        return False
