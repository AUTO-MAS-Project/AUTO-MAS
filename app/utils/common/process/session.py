"""Windows 进程会话的归属核验。"""

import os
from collections.abc import Callable

_expected: int | None = None
_parent_scope: Callable[[], int | None] | None = None


def bind_process_session(session_id: int) -> None:
    """执行器只允许管理当前子会话的应用进程。"""
    global _expected
    from app.utils.windows.desktop_session.native import process_session

    if session_id <= 0 or session_id != process_session(os.getpid()):
        raise RuntimeError("桌面分身进程会话不匹配")
    _expected = session_id


def configure_parent_scope(resolve: Callable[[], int | None]) -> None:
    global _parent_scope
    _parent_scope = resolve


def restricted_session() -> int | None:
    if _expected is not None:
        return _expected
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
