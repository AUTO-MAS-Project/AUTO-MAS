"""进程能力兼容入口。"""

from .platform.common.process import (
    ProcessInfo,
    activate_window_by_pid,
    has_visible_window,
    is_process_alive,
    ProcessManager,
    ProcessResult,
    ProcessRunner,
    get_main_window_handle,
    get_window_handles,
    is_process_running,
    match_process,
)

__all__ = [
    "ProcessInfo",
    "activate_window_by_pid",
    "has_visible_window",
    "is_process_alive",
    "ProcessManager",
    "ProcessResult",
    "ProcessRunner",
    "get_main_window_handle",
    "get_window_handles",
    "is_process_running",
    "match_process",
]
