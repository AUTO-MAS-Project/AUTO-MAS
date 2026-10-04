#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-NTE（异环）经启动器带 /autoplay 参数静默拉起游戏。

异环客户端直接运行 HTGame.exe 会卡界面，必须经启动器（NTELauncher 下的
NTEGame.exe / NTEGlobalGame.exe / NTETWGame.exe）启动。启动器接受 /autoplay
参数：带该参数启动时启动器自行拉起游戏并完成登录，无需 OCR 找「开始游戏」
按钮再点击，本模块因此只保留「静默拉起 + 等游戏窗口」这一条路径（启动器是
严格单实例，它已在运行时参数传不进去，由调用方先结束旧实例）。

流程::

    带 /autoplay 拉起启动器 → 轮询 HTGame.exe 可见窗口出现（游戏就绪，停在标题界面）
"""

import asyncio
import ctypes
import time
from collections.abc import Callable
from pathlib import Path

import psutil

from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    # pyautogui 与 pywin32 仅 Windows 可用（无图形会话导入即失败），随入口的
    # IS_WINDOWS 检查一并惰性导入
    import pyautogui
    import win32gui
    import win32process

logger = get_logger("OK-NTE 启动器启动")

# 游戏客户端与启动器进程名（对齐 ok-nte 上游 src/__init__.py）
_GAME_PROCESS = "HTGame.exe"

# 启动器静默启动参数：带 /autoplay 时启动器自行拉起游戏，无需点击「开始游戏」
AUTOPLAY_ARG = "/autoplay"
# 静默启动后等游戏窗口出现的上限（本机实测 36-40s 出窗，留足余量）
_AUTOPLAY_START_TIMEOUT = 180.0
# 静默启动等待期间的进度日志间隔：长时间无输出会让用户以为卡死
_AUTOPLAY_PROGRESS_SECONDS = 15.0


# ── 窗口 / 进程定位 ─────────────────────────────────────────────────────


def _process_name(pid: int) -> str | None:
    """按 pid 读取进程名；提权进程可能被拒，返回 None 而非抛错。"""
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _window_area(hwnd: int) -> int:
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (right - left) * (bottom - top)
    except Exception:
        return 0


def _find_process_hwnd(process_name: str) -> int | None:
    """按所属进程名找最大可见窗口；不存在返回 None（区别于切号的必存抛错）。"""
    candidates: list[int] = []

    def _enum(hwnd: int, _lparam: int) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid and _process_name(pid) == process_name:
            candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_enum, 0)
    return max(candidates, key=_window_area) if candidates else None


def _find_game_hwnd() -> int | None:
    return _find_process_hwnd(_GAME_PROCESS)


# ── 屏保退出（对齐 ok-nte 上游开工前的 dismiss_screensaver）──────────────
_SPI_GETSCREENSAVERRUNNING = 0x0072


def _screensaver_running() -> bool:
    running = ctypes.c_int(0)
    if not ctypes.windll.user32.SystemParametersInfoW(
        _SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(running), 0
    ):
        return False
    return bool(running.value)


def dismiss_screensaver() -> None:
    """屏保运行时轻推鼠标将其退出（旁路：失败仅记日志，不阻断启动流程）。

    屏保全屏覆盖会让窗口截图变成黑屏，OCR 找不到任何按钮；挂机定时任务几乎
    必然带屏保运行，开工前先退出一次（对齐 ok-nte 上游 LauncherTask 行为）。
    """
    if not _screensaver_running():
        return
    logger.info("检测到屏幕保护程序正在运行，轻推鼠标退出...")
    try:
        x, y = pyautogui.position()
        deadline = time.monotonic() + 10
        offset = 50
        while _screensaver_running() and time.monotonic() < deadline:
            pyautogui.moveTo(x + offset, y)
            offset = -offset
            time.sleep(1)
        pyautogui.moveTo(x, y)
    except Exception as error:
        logger.warning(f"退出屏幕保护程序失败（忽略，继续启动流程）: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def wait_autoplay_game(
    launcher_path: Path,
    *,
    timeout: float | None = None,
    on_log: Callable[[str], None] | None = None,
) -> bool:
    """轮询等待带 /autoplay 静默拉起的异环游戏窗口出现。

    启动器带 /autoplay 参数时无需点击与 OCR 交互，「游戏已就绪」等价于
    HTGame.exe 出现可见窗口，轮询该窗口即可判定；超时返回 False（调用方按
    启动失败处理），仅非 Windows 平台抛 RuntimeError。

    Args:
        launcher_path: 启动器 exe 路径（用于日志标明是哪个启动器静默拉起）。
        timeout: 等待上限（秒），默认 _AUTOPLAY_START_TIMEOUT。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        游戏窗口出现返回 True；超时返回 False。

    Raises:
        RuntimeError: 非 Windows 平台（窗口轮询依赖 win32gui，退屏保依赖 pyautogui）。
    """

    if not IS_WINDOWS:
        raise RuntimeError("OK-NTE 启动器启动仅支持 Windows 平台")
    # 开工前退出屏保：屏保全屏覆盖会让后续窗口截图变成黑屏（沿用旧点击启动路径与
    # ok-nte 上游 LauncherTask 的行为）
    dismiss_screensaver()
    on_log = on_log or (lambda msg: logger.info(msg))
    limit = _AUTOPLAY_START_TIMEOUT if timeout is None else timeout
    started = time.monotonic()
    deadline = started + limit
    next_progress = started + _AUTOPLAY_PROGRESS_SECONDS
    on_log(
        f"启动器 {launcher_path.name} 已带 {AUTOPLAY_ARG} 静默拉起，"
        f"正在等待游戏窗口出现（最迟 {limit:g}s）..."
    )
    while True:
        if _find_game_hwnd() is not None:
            on_log("已检测到异环游戏窗口")
            return True
        now = time.monotonic()
        if now >= deadline:
            on_log(f"{AUTOPLAY_ARG} 静默启动等待游戏窗口超时（{limit:g}s）")
            return False
        if now >= next_progress:
            on_log(f"正在等待 {AUTOPLAY_ARG} 拉起游戏窗口（{int(now - started)}s）...")
            next_progress = now + _AUTOPLAY_PROGRESS_SECONDS
        time.sleep(2)


async def async_wait_autoplay_game(
    launcher_path: Path,
    *,
    timeout: float | None = None,
    on_log: Callable[[str], None] | None = None,
) -> bool:
    """async 版本：在后台线程轮询游戏窗口，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        wait_autoplay_game, launcher_path, timeout=timeout, on_log=on_log
    )
