"""MaaEnd 失败诊断的窗口归属核验，不激活窗口或截取桌面。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

type AdbCapture = Callable[[Path | str, str], Awaitable["Image.Image | None"]]
type Win32Capture = Callable[[int], Awaitable["Image.Image | None"]]


async def capture_game_window(
    game_path: Path, capture_win32: Win32Capture
) -> "Image.Image | None":
    """仅截取 Game.Path 对应的真实进程窗口，拒绝同名的其他安装。"""

    import psutil
    import win32gui
    import win32process

    game_path = game_path.resolve()
    if not game_path.is_file():
        return None

    def find_window() -> tuple[int, psutil.Process] | None:
        candidates: list[tuple[int, int, psutil.Process]] = []

        def collect(hwnd: int, _: int) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                if Path(process.exe()).resolve() != game_path:
                    return True
                left, top, right, bottom = win32gui.GetClientRect(hwnd)
                area = (right - left) * (bottom - top)
                if area > 0:
                    candidates.append((area, hwnd, process))
            except (OSError, psutil.Error):
                pass
            return True

        win32gui.EnumWindows(collect, 0)
        if not candidates:
            return None
        _, hwnd, process = max(candidates, key=lambda item: item[0])
        return hwnd, process

    target = await asyncio.to_thread(find_window)
    if target is None:
        return None
    hwnd, process = target
    # 枚举期间进程可能退出、PID 或 HWND 可能复用；截图前重新确认身份。
    if (
        not process.is_running()
        or not win32gui.IsWindow(hwnd)
        or win32process.GetWindowThreadProcessId(hwnd)[1] != process.pid
        or Path(process.exe()).resolve() != game_path
    ):
        return None
    return await capture_win32(hwnd)
