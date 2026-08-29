import ctypes
from contextlib import suppress

import win32api
import win32con
import win32gui
import win32process


def get_window_handles(pid: int) -> list[int]:
    """获取指定进程的所有窗口句柄"""

    window_handles = []

    def enum_callback(hwnd: int, lparam: int) -> bool:
        """枚举窗口的回调函数"""
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        if process_id == pid:
            window_handles.append(hwnd)
        return True

    win32gui.EnumWindows(enum_callback, 0)
    return window_handles


def get_main_window_handle(
    pid: int,
    window_title: str | None = None,
    window_class_name: str | None = None,
) -> int | None:
    """获取指定进程的主窗口句柄

    优先按标题或类名定位, 若未命中则回退到 PID 下最合适的顶层窗口。
    """

    # 候选过滤: 仅保留可作为主窗口的顶层窗口
    handles: list[int] = []
    for hwnd in get_window_handles(pid):
        try:
            if not win32gui.IsWindow(hwnd):
                continue
            if win32gui.GetParent(hwnd) not in (0, None):
                continue
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                continue

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                continue
        except Exception:
            continue

        handles.append(hwnd)

    # 主流程: 无候选直接失败
    if not handles:
        return None

    # 提示匹配: 按标题或类名进一步过滤
    hinted_handles: list[int] = []
    if window_title is not None or window_class_name is not None:
        for hwnd in handles:
            try:
                if window_title is not None:
                    title = win32gui.GetWindowText(hwnd)
                    if not title or window_title.lower() not in title.lower():
                        continue

                if window_class_name is not None:
                    class_name = win32gui.GetClassName(hwnd)
                    if (
                        not class_name
                        or window_class_name.lower() not in class_name.lower()
                    ):
                        continue
            except Exception:
                continue

            hinted_handles.append(hwnd)

    # 候选排序: 可见优先, 面积次之, 句柄值作为稳定兜底
    candidates = hinted_handles if hinted_handles else handles
    best_hwnd: int | None = None
    best_score: tuple[int, int, int] | None = None

    for hwnd in candidates:
        try:
            visible_score = 1 if win32gui.IsWindowVisible(hwnd) else 0
        except Exception:
            visible_score = 0

        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            area_score = max(0, right - left) * max(0, bottom - top)
        except Exception:
            area_score = -1

        score = (visible_score, area_score, -hwnd)
        if best_score is None or score > best_score:
            best_score = score
            best_hwnd = hwnd

    return best_hwnd


def is_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))


def show_window(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    return True


def hide_window(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    return True


def minimize_window(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    return True


def activate_window(hwnd: int) -> bool:
    attached = False
    current_tid = 0
    foreground_tid = 0

    try:
        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd:
            foreground_tid, _ = win32process.GetWindowThreadProcessId(
                foreground_hwnd
            )
        current_tid = win32api.GetCurrentThreadId()
        if foreground_tid not in (0, current_tid):
            win32process.AttachThreadInput(current_tid, foreground_tid, True)
            attached = True

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
            win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False
    finally:
        if attached:
            with suppress(Exception):
                win32process.AttachThreadInput(current_tid, foreground_tid, False)


def get_dpi_scaling() -> float | None:
    """查询主显示器 DPI 缩放比例，失败返回 None 由调用方决定默认值。"""

    with suppress(AttributeError, OSError):
        # Windows 8.1 以下没有该函数，跳过即可
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

    try:
        hdc = win32gui.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        finally:
            win32gui.ReleaseDC(0, hdc)
    except Exception:
        return None

    return dpi / 96.0


def find_window_by_title(title: str) -> tuple[int, str] | None:
    """按标题模糊匹配可见窗口，返回 (句柄, 实际标题)，未找到返回 None。"""

    found: list[tuple[int, str]] = []

    def enum_callback(hwnd: int, results: list[tuple[int, str]]) -> None:
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            if title.lower() in window_title.lower():
                results.append((hwnd, window_title))

    try:
        win32gui.EnumWindows(enum_callback, found)
    except Exception:
        return None

    return found[0] if found else None


def get_foreground_window() -> int:
    return win32gui.GetForegroundWindow()


def get_window_text(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd)


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    return win32gui.GetWindowRect(hwnd)


def is_minimized(hwnd: int) -> bool:
    return win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED


def restore_window(hwnd: int) -> bool:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    return True


def force_activate_window(hwnd: int) -> bool:
    """用线程输入附着强制激活窗口（前台线程 -> 目标线程）。

    与 activate_window 的附着方向不同，供需要抢占前台的调用方使用。
    """

    attached = False
    foreground_thread_id = 0
    target_thread_id = 0

    try:
        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd == hwnd:
            return True

        if foreground_hwnd:
            foreground_thread_id, _ = win32process.GetWindowThreadProcessId(
                foreground_hwnd
            )
        target_thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)

        if foreground_thread_id not in (0, target_thread_id):
            with suppress(Exception):
                win32process.AttachThreadInput(
                    foreground_thread_id, target_thread_id, True
                )
                attached = True

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            with suppress(Exception):
                win32gui.SetFocus(hwnd)
            with suppress(Exception):
                win32gui.BringWindowToTop(hwnd)
        finally:
            if attached:
                with suppress(Exception):
                    win32process.AttachThreadInput(
                        foreground_thread_id, target_thread_id, False
                    )
        return True
    except Exception:
        return False
