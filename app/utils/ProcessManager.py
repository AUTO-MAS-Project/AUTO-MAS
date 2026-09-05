"""进程能力兼容入口。"""

from .platform.common.process import (
    ProcessInfo,
    ProcessManager,
    ProcessResult,
    ProcessRunner,
    get_main_window_handle,
    get_window_handles,
    is_process_alive,
    is_process_running,
    match_process,
)

__all__ = [
    "ProcessInfo",
    "is_process_alive",
    "ProcessManager",
    "ProcessResult",
    "ProcessRunner",
    "get_main_window_handle",
    "get_window_handles",
    "is_process_running",
    "match_process",
]
