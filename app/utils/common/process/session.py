"""桌面分身执行器内的 Windows 进程归属限制。"""

import os
from functools import lru_cache
from time import monotonic

_expected: int | None = None


def bind_process_session(session_id: int) -> None:
    """执行器只允许管理当前子会话的应用进程。"""
    global _expected
    from app.utils.windows.desktop_session.native import process_session

    if session_id <= 0 or session_id != process_session(os.getpid()):
        raise RuntimeError("桌面分身进程会话不匹配")
    _expected = session_id


def restricted_session() -> int | None:
    if _expected is not None or os.name != "nt":
        return _expected
    return _parent_session(int(monotonic()))


@lru_cache(maxsize=1)
def _parent_session(_second: int) -> int | None:
    from app.utils.windows.desktop_session.native import child_session, process_session

    try:
        if child_session() is not None:
            return process_session(os.getpid())
    except OSError:
        return None
    return None


def process_in_scope(pid: int) -> bool:
    session_id = restricted_session()
    if session_id is None:
        return True
    from app.utils.windows.desktop_session.native import process_session

    try:
        return process_session(pid) == session_id
    except OSError:
        return False
