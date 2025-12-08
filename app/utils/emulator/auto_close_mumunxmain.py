import win32gui
import win32process
import win32con
import psutil
import asyncio
from types import CoroutineType
from functools import wraps
from typing import Callable, Any, Coroutine, Optional, TypeVar, ParamSpec


P = ParamSpec("P")
R = TypeVar("R")


def _find_mumu_window() -> Optional[int]:
    """
    同步查找 MuMu 多开器窗口。

    Returns:
        Optional[int]: 窗口句柄 (HWND)，未找到则返回 None。
    """
    target_title: str = "MuMu模拟器"
    target_process: str = "mumunxmain.exe"

    def enum_cb(hwnd: int, result_list: list[Optional[int]]) -> bool:
        if result_list[0] is not None:
            return False  # 已找到，停止枚举
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) != 0:
            return True
        if win32gui.GetWindowText(hwnd) != target_title:
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name().lower()
            if proc_name == target_process:
                result_list[0] = hwnd
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
        return True

    result: list[Optional[int]] = [None]
    try:
        win32gui.EnumWindows(enum_cb, result)
    except:  # noqa: E722
        # EnumWindows 在回调返回 False 时抛出异常，属正常行为
        pass
    return result[0]


def auto_close_mumunxmain(
    max_wait: float = 2.0, interval: float = 0.05
) -> Callable[
    [Callable[P, Coroutine[Any, Any, R]]], Callable[P, CoroutineType[Any, Any, R]]
]:
    """
    异步装饰器工厂：用于装饰 async 函数。

    在函数执行前后检测 MuMu 多开器窗口。
    若执行前无窗口，执行后在 `max_wait` 秒内持续检测；
    一旦窗口出现，立即发送 WM_CLOSE 将其最小化到托盘。

    Args:
        max_wait (float): 最大等待检测时间（秒），默认 2.0
        interval (float): 检测轮询间隔（秒），默认 0.05 (50 毫秒)

    Returns:
        Decorator that wraps an async function.
    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, CoroutineType[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # 执行前：检查窗口是否存在
            existed_before: bool = _find_mumu_window() is not None

            # 执行被装饰的异步函数
            result: R = await func(*args, **kwargs)

            # 如果执行前已有窗口，直接返回
            if existed_before:
                return result

            # 否则：持续检测最多 max_wait 秒
            elapsed: float = 0.0
            hwnd_found: Optional[int] = None
            while elapsed <= max_wait:
                hwnd: Optional[int] = _find_mumu_window()
                if hwnd is not None:
                    hwnd_found = hwnd
                    break
                await asyncio.sleep(interval)
                elapsed += interval

            # 如果在等待期间检测到新窗口，发送 WM_CLOSE
            if hwnd_found is not None:
                win32gui.PostMessage(hwnd_found, win32con.WM_CLOSE, 0, 0)

            return result

        return wrapper

    return decorator
