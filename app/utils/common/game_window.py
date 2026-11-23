#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""按进程归属定位窗口、前置窗口，以及按客户区截图。

各专项的启动器交互与账号切换此前各存一份逐字相同的实现（原神 / 终末地 /
异环 / 鸣潮共七处），这里按统一语义各留一份：

- ``find_window`` 负责定位：进程名必选，窗口类、候选 pid 集合、exe 路径、
  自定义归属判定都是可选收窄条件
- ``wait_window`` 在它上面加重试与「进程已退出」的快速失败
- ``activate_window`` / ``capture_window`` 是前置与截图，空等由调用方给

窗口能力只有 Windows 有，调用方仍在自己的入口做 ``IS_WINDOWS`` 检查；本模块
的 win32 依赖惰性导入，在其它平台导入本模块不会失败。
"""

import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import psutil
from PIL import Image

from app.utils import get_logger

logger = get_logger("窗口工具")

# 截图基准分辨率（16:9），OCR 与点击都在此坐标空间计算后再映射回真实窗口
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080

# 前置窗口后的空等：ShowWindow 与前台切换都要一拍才生效
_SHOW_SETTLE_SECONDS = 0.15
_FOREGROUND_SETTLE_SECONDS = 0.1

# 客户区比例偏离 16:9 的容忍度；超出只告警，不阻断（切号坐标可能偏移）
_RATIO_TOLERANCE = 0.02


def _win32():
    """惰性导入 win32 模块组；调用方已确认在 Windows 上。"""

    import win32api
    import win32con
    import win32gui
    import win32process

    return win32api, win32con, win32gui, win32process


def process_name(pid: int) -> str | None:
    """按 pid 读取进程名；提权进程可能被拒，返回 None 而非抛错。"""

    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def process_exe(pid: int) -> str | None:
    """按 pid 读取进程 exe 完整路径；被拒时返回 None 而非抛错。"""

    try:
        return psutil.Process(pid).exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def window_area(hwnd: int) -> int:
    """窗口外框面积，用于「同进程多个窗口取最大」；取不到按 0 处理。"""

    _, _, win32gui, _ = _win32()
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (right - left) * (bottom - top)
    except Exception:
        return 0


def find_window(
    process_names: str | tuple[str, ...] | None = None,
    window_class: str | None = None,
    *,
    pids: set[int] | None = None,
    exe_path: Path | str | None = None,
    owner: Callable[[int], bool] | None = None,
) -> int | None:
    """按所属进程找最大可见窗口；不存在返回 None。

    Args:
        process_names: 进程名，接受单个或多个候选，比较不区分大小写。给了
            ``owner`` 时可以不填
        window_class: 只认这个窗口类（精确匹配），同进程多窗口时用来区分主界面
        pids: 只认这些进程的窗口。``Client-Win64-Shipping.exe`` 这类通用进程名
            同机可能有其它同名游戏，给了集合才不会认错对象
        exe_path: 只认 exe 路径完全一致的那个进程，收窄同名的不同安装
        owner: 自定义归属判定。启动器家族这类「进程名 + 安装根目录」的双条件
            无法用进程名表达，由调用方传入

    Returns:
        命中的最大可见窗口句柄；没有命中返回 None
    """

    _, _, win32gui, win32process = _win32()
    wanted: set[str] = set()
    if process_names is not None:
        names = (
            (process_names,) if isinstance(process_names, str) else tuple(process_names)
        )
        wanted = {name.casefold() for name in names}
    wanted_exe = Path(exe_path) if exe_path is not None else None
    candidates: list[int] = []

    def _enum(hwnd: int, _lparam: int) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if window_class is not None and win32gui.GetClassName(hwnd) != window_class:
                return True
        except Exception:
            # 枚举途中窗口被销毁属常态，跳过它，不作废整轮枚举
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid or (pids is not None and pid not in pids):
            return True
        if owner is not None:
            if not owner(pid):
                return True
        else:
            name = process_name(pid)
            if name is None or name.casefold() not in wanted:
                return True
        if wanted_exe is not None:
            exe = process_exe(pid)
            if exe is None or Path(exe) != wanted_exe:
                return True
        candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_enum, 0)
    return max(candidates, key=window_area) if candidates else None


def wait_window(
    process_names: str | tuple[str, ...] | None = None,
    window_class: str | None = None,
    *,
    pids: set[int] | None = None,
    exe_path: Path | str | None = None,
    owner: Callable[[int], bool] | None = None,
    alive: Callable[[], bool],
    timeout: float,
    label: str,
    poll_interval: float = 1.0,
    gone_grace: float | None = None,
) -> int:
    """轮询等窗口出现；超时或进程已退出时抛错。

    单次枚举会瞬时把「刚拉起、窗口还没建好」误判成失败，所以这里按间隔重试。
    进程先出现、随后全部消失时不必等满上限：持续 ``gone_grace`` 秒仍无进程
    也无窗口就判永久退出，如实快速失败。

    Args:
        process_names ... owner: 同 ``find_window``，描述要找哪个窗口
        alive: 目标进程是否仍有存活实例；用于判断「已退出」与进度日志
        timeout: 等待上限（秒）
        label: 异常与进度日志里的窗口称呼，如「原神游戏窗口」
        poll_interval: 轮询间隔（秒）
        gone_grace: 进程消失多久后判为永久退出。``None`` 表示不据此失败
            （允许游戏退出并重启的调用方传 ``None``）

    Returns:
        命中的窗口句柄

    Raises:
        RuntimeError: 超过上限仍未找到窗口，或进程持续消失超过宽限期
    """

    deadline = time.monotonic() + timeout
    seen_alive = False
    gone_since: float | None = None
    while True:
        hwnd = find_window(
            process_names,
            window_class,
            pids=pids,
            exe_path=exe_path,
            owner=owner,
        )
        if hwnd is not None:
            return hwnd
        if time.monotonic() >= deadline:
            break
        if alive():
            seen_alive = True
            gone_since = None
            logger.info(
                f"{label}进程已启动但窗口暂未就绪，{poll_interval:g} 秒后重试..."
            )
        elif seen_alive and gone_grace is not None:
            now = time.monotonic()
            if gone_since is None:
                gone_since = now
            elif now - gone_since >= gone_grace:
                raise RuntimeError(
                    f"{label}进程已退出，窗口不会再出现，请确认游戏已由 MAS 成功启动"
                )
            logger.info(f"正在等待{label}重新出现，{poll_interval:g} 秒后重试...")
        else:
            seen_alive = False
            logger.info(f"正在等待{label}窗口，{poll_interval:g} 秒后重试...")
        time.sleep(poll_interval)
    raise RuntimeError(f"{timeout:g} 秒内未找到{label}窗口")


def activate_window(
    hwnd: int, *, label: str, pause: Callable[[float], None] | None = None
) -> None:
    """把窗口显示出来并置前。

    Windows 前台锁不允许后台进程直接抢前台，这里先附着当前前台窗口的输入
    队列再置前。系统忽略焦点请求时只记一条 debug，继续按前置窗口处理。

    Args:
        hwnd: 目标窗口句柄
        label: 异常文案里的窗口称呼，如「原神游戏窗口」
        pause: 空等函数，由调用方决定是否响应停止信号；不给就直接睡；不给就直接睡

    Raises:
        RuntimeError: 窗口句柄已失效
    """

    wait = pause or time.sleep
    wait = pause or time.sleep
    win32api, win32con, win32gui, win32process = _win32()
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(f"{label}已失效")
    show_command = (
        win32con.SW_RESTORE
        if win32gui.IsIconic(hwnd)
        else win32con.SW_SHOW
        if not win32gui.IsWindowVisible(hwnd)
        else None
    )
    if show_command is not None:
        win32gui.ShowWindow(hwnd, show_command)
        wait(_SHOW_SETTLE_SECONDS)
    try:
        if win32gui.GetForegroundWindow() != hwnd:
            foreground = win32gui.GetForegroundWindow()
            fg_thread = win32process.GetWindowThreadProcessId(foreground)[0]
            win32process.AttachThreadInput(
                win32api.GetCurrentThreadId(), fg_thread, True
            )
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            finally:
                win32process.AttachThreadInput(
                    win32api.GetCurrentThreadId(), fg_thread, False
                )
        else:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:
        logger.debug(f"{label}焦点请求被系统忽略，继续按前置窗口处理")
    wait(_FOREGROUND_SETTLE_SECONDS)


def client_size(hwnd: int, *, label: str) -> tuple[int, int]:
    """客户区尺寸；窗口已失效或尺寸异常时抛错。

    Raises:
        RuntimeError: 客户区宽高非正
    """

    _, _, win32gui, _ = _win32()
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"{label}尺寸异常")
    return width, height


def warn_non_16_9(width: int, height: int, *, label: str) -> None:
    """窗口不是 16:9 时提醒坐标可能偏移；不阻断。"""

    if abs(width / height - 16 / 9) > _RATIO_TOLERANCE:
        logger.warning(f"{label}非 16:9（{width}x{height}），坐标可能偏移")


def capture_window_image(
    hwnd: int,
    *,
    label: str,
    pause: Callable[[float], None] | None = None,
    activate: bool = True,
    check_size: bool = True,
) -> Image.Image:
    """按客户区截一张原尺寸图。

    Args:
        check_size: 为 False 时跳过「客户区宽高为正」的校验，只用于保存诊断
            截图——此时宁可拿到一张尺寸异常的图，也不要因此丢掉证据
    """

    from app.utils import display as _display

    win32api, win32con, win32gui, _ = _win32()
    with _display.per_monitor_dpi():
        if activate:
            activate_window(hwnd, label=label, pause=pause)
        if check_size:
            width, height = client_size(hwnd, label=label)
        else:
            _, _, width, height = win32gui.GetClientRect(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        virtual_left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        virtual_top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        import pyautogui

        return pyautogui.screenshot(allScreens=True).crop(
            (
                left - virtual_left,
                top - virtual_top,
                left - virtual_left + width,
                top - virtual_top + height,
            )
        )


def capture_window(
    hwnd: int,
    *,
    label: str,
    pause: Callable[[float], None] | None = None,
    activate: bool = True,
) -> np.ndarray:
    """按客户区截图并统一缩放到 1920×1080 基准帧（BGR）。"""

    screenshot = capture_window_image(hwnd, label=label, pause=pause, activate=activate)
    screenshot = screenshot.resize(
        (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.LANCZOS
    )
    return cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_RGB2BGR)
