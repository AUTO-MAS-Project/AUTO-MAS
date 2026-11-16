"""尚无实现的平台窗口操作；调用时明确报告不支持。"""

from ..common.errors import UnsupportedPlatformError

WindowError = RuntimeError


def get_window_handles(pid: int) -> list[int]:
    raise UnsupportedPlatformError("window")


def get_main_window_handle(
    pid: int, window_title: str | None = None, window_class_name: str | None = None
) -> int | None:
    raise UnsupportedPlatformError("window")


def is_visible(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def is_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def show_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def hide_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def minimize_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def close_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def activate_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def get_dpi_scaling() -> float | None:
    raise UnsupportedPlatformError("window")


def find_window_by_title(title: str) -> tuple[int, str] | None:
    raise UnsupportedPlatformError("window")


def get_foreground_window() -> int:
    raise UnsupportedPlatformError("window")


def get_window_text(hwnd: int) -> str:
    raise UnsupportedPlatformError("window")


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    raise UnsupportedPlatformError("window")


def is_minimized(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def restore_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def force_activate_window(hwnd: int) -> bool:
    raise UnsupportedPlatformError("window")


def visible_owned_windows(owner: int) -> list[int]:
    raise UnsupportedPlatformError("window")


def get_window_owner(hwnd: int) -> int:
    raise UnsupportedPlatformError("window")


def get_window_class(hwnd: int) -> str:
    raise UnsupportedPlatformError("window")


def set_window_visible_async(hwnd: int, *, visible: bool) -> None:
    raise UnsupportedPlatformError("window")


def find_window_by_process(title: str, process_name: str) -> int | None:
    raise UnsupportedPlatformError("window")
