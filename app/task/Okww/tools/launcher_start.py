#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-WW（鸣潮）通过官方启动器拉起游戏。

本模块是「启动器启动」方式（``Game.Type = Launcher``）的实现：由 MAS 拉起官方
启动器（launcher.exe）并点「进入游戏」。另一种「直接启动」方式（``Client``，默认）
由 AutoProxy 的 _launch_game_direct 直接拉起客户端 exe，不经过本模块。
交互与截图采用与账号切换一致的前台 pyautogui + DPI 适配模式，OCR 复用通用工具集
`app.tools.ocr`。

流程::

    退出屏保 → 拉起启动器 → 等启动器窗口 → 在右下角动作区 OCR 找
    「进入游戏」/「更新」按钮并点击（点「更新」后只点一次，等下载与随后的
    校验解压结束、按钮变回后再点）→ 等 Client-Win64-Shipping.exe 进程 +
    可见窗口出现（游戏就绪）

与 ok-nte 的关键差异：

- 鸣潮启动器是进程家族：顶层 ``launcher.exe`` 只是引导器，真正的界面窗口属于
  版本目录下的 ``launcher_main.exe``（如 ``<根>\\2.6.5.0\\launcher_main.exe``，
  版本目录随启动器自更新变化）。窗口定位与进程清理都按「launcher.exe /
  launcher_main.exe + exe 位于启动器安装根目录树内」双重限定——``launcher.exe``
  是通用进程名，单按名匹配会误伤无关程序。
- 启动器左侧有用户信息卡与活动公告等富文本干扰，且下载进度行的速度/总量并不
  一直显示（可能只剩计时与百分比），因此状态判定与点击只认右下角动作区，
  下载卡死签名只取百分比/体积/速度并剥离计时文本。
- 启动器其它弹窗状态（自更新、公告等）待实测后按既有分支模式补充。
"""

import asyncio
import ctypes
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import psutil
from PIL import Image

from app.tools.error_screenshot import save_error_screenshot
from app.tools.ocr import Box, OCRItem, ocr_image
from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    # pyautogui 与 pywin32 仅 Windows 可用（无图形会话导入即失败），随入口的
    # IS_WINDOWS 检查一并惰性导入
    import pyautogui
    import win32api
    import win32con
    import win32gui
    import win32process

logger = get_logger("OK-WW 启动器启动")

# 诊断文件（debug/okww-launcher-start/launcher-detail-*.log）：记录窗口定位结果
# 与各轮 OCR 全量条目，供启动器按钮未被点击时排查窗口错抓/截图偏移/文本漂移；
# 启动交互串行独占前台，单例写入。
_DIAGNOSTIC_PATH: Path | None = None


def _write_diagnostic(text: str) -> None:
    """向诊断文件追加文本（旁路，失败时静默忽略）。"""
    if _DIAGNOSTIC_PATH is not None:
        try:
            with _DIAGNOSTIC_PATH.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass


def _dump_ocr_items(items: list[OCRItem]) -> None:
    """诊断旁路：把一次 OCR 的全部识别文本写入诊断文件。"""
    if _DIAGNOSTIC_PATH is None:
        return
    _write_diagnostic(f"OCR {len(items)} 条:\n")
    for text, (x, y, width, height) in items:
        _write_diagnostic(f"  ({x:4},{y:4} {width:3}x{height:3}) {text}\n")


def _describe_window(hwnd: int) -> str:
    """诊断旁路：描述窗口归属进程与标题，排查是否错抓同名/子进程窗口。"""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = _process_exe(pid) or _process_name(pid) or "?"
        title = win32gui.GetWindowText(hwnd)
        return f"pid={pid} exe={exe} title={title!r}"
    except Exception:
        return "描述失败"


# 游戏客户端进程名与窗口类（与账号切换的 _WUWA_PROCESS/_WUWA_CLASS 一致），
# 窗口出现即游戏就绪
_GAME_PROCESS = "Client-Win64-Shipping.exe"
_GAME_WINDOW_CLASS = "UnrealWindow"

# 启动器进程家族：顶层 launcher.exe 是引导器，真正的界面窗口属于版本目录下的
# launcher_main.exe；版本目录随启动器自更新变化（如 <根>\2.6.5.0\）。家族匹配
# 还须限定 exe 位于启动器安装根目录树内——launcher.exe 是通用进程名，单按名
# 匹配会误伤无关程序。
_LAUNCHER_PROCESS_NAMES = frozenset({"launcher.exe", "launcher_main.exe"})

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# 右下角动作区（相对 1080p 帧）：启动器按钮与下载进度都在此区域，左侧用户
# 信息卡/活动公告/新闻列表含大量富文本，不参与判定与点击，避免干扰误触
_ACTION_ROI: Box = (1240, 820, 1920, 1080)

# 首次找到按钮的等待；点击「进入游戏」后等游戏起窗；点「更新」后等下载完成
_FIND_BUTTON_TIMEOUT = 120
_START_GAME_TIMEOUT = 300
# 更新类等待上限：对齐 ok-nte「下载进行中动态续延」的思路放宽到 2 小时，
# 该值仅为点击「更新」后尚未出现下载 UI 的兜底等待
_UPDATE_TIMEOUT = 7200
# 启动器拉起后等其窗口创建的时限
_LAUNCHER_WINDOW_TIMEOUT = 120

# ── 启动器下载状态动态识别（基于 OCR，样本为真实下载界面）────────────────
# 忙碌态判定文本：右下角按钮「下载中 ...」与「校验解压文件 ..」。下载完成后
# 启动器会自动进入校验解压阶段（过程不消耗流量），解压完成才会回到「进入游戏」，
# 两态同样需要动态续延等待；裸「下载」用于容忍 OCR 拆词，但「预下载」开放且
# 游戏可玩是官方预期状态，含「预」的条目必须排除（见 _find_busy_box）
_BUSY_STATE_TEXTS = ("下载中", "下载", "校验解压")
# 下载进度相关文本特征：用于构造「下载进度签名」，只看含百分比/体积/速度的
# 条目；速度与总量并不一直显示（可能只剩「00:40:45 0.28%」这类计时+百分比），
# 计时文本必须剥离，否则计时器每秒变化会掩盖真实进度停滞
_DOWNLOAD_PROGRESS_TOKENS = ("%", "MB", "GB", "KB")
# 进度签名剥离模式：剥离「00:40:45」/「40:45」形态的计时文本（至少一组冒号）
_ELAPSED_TIME_PATTERN = re.compile(r"\d{1,}:\d{2}(?::\d{2})*")
# 检测到下载态时每次顺延的等待宽限（下载 UI 持续存在就持续等，等效不设总时限）
_UPDATE_ACTIVE_GRACE_SECONDS = 600.0
# 下载进度签名持续无变化的时长上限：百分比/体积/速度长时间不动视为下载卡死
_DOWNLOAD_STALL_SECONDS = 300.0
# 忙碌态等待的绝对上限：单次下载/校验解压最多等这么久，防止进度文本持续抖动
# 时既判不出卡死也无法退出（正常下载远超此时长才会触发，属防意外兜底）
_BUSY_WAIT_HARD_LIMIT_SECONDS = 7200.0
# 「进入游戏」点击重试：被遮挡等场景点击可能被吞（若用固定次数预算，遮罩消失
# 后预算已尽只能干等超时），改为按时间间隔重试并保留宽松总上限防死循环；点击
# 生效时启动器会直接退出，按钮消失即停止重试。
_START_CLICK_LIMIT = 8
_START_CLICK_INTERVAL_SECONDS = 12.0
# 「更新」点击重试：单次点击防重复下载是有意设计，但点击被吞时需按间隔补点，
# 以按钮长时间停留原状（未被下载/进度 UI 取代）为被吞判据
_UPDATE_CLICK_RETRY_SECONDS = 15.0
_UPDATE_CLICK_RETRY_LIMIT = 3


@lru_cache(maxsize=1)
def _user32_dpi_api():
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    return user32


@contextmanager
def _per_monitor_dpi():
    """切换到 per-monitor DPI 感知，保证窗口坐标换算在跨 DPI 显示器下正确。"""
    user32 = _user32_dpi_api()
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(previous)


# ── 窗口 / 进程定位 ─────────────────────────────────────────────────────


def _process_name(pid: int) -> str | None:
    """按 pid 读取进程名；提权进程可能被拒，返回 None 而非抛错。"""
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _process_exe(pid: int) -> str | None:
    """按 pid 读取进程 exe 完整路径；被拒时返回 None 而非抛错。"""
    try:
        return psutil.Process(pid).exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _window_area(hwnd: int) -> int:
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (right - left) * (bottom - top)
    except Exception:
        return 0


def _find_hwnd(process_name: str, window_class: str | None = None) -> int | None:
    """按所属进程名（可选加窗口类）找最大可见窗口；不存在返回 None。"""
    candidates: list[int] = []

    def _enum(hwnd: int, _lparam: int) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if window_class is not None and win32gui.GetClassName(hwnd) != window_class:
                return True
        except Exception:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid and _process_name(pid) == process_name:
            candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_enum, 0)
    return max(candidates, key=_window_area) if candidates else None


def _is_launcher_process(pid: int, root_prefix: str) -> bool:
    """判定 pid 是否属于启动器进程家族（进程名 + exe 位于安装根目录树内）。

    exe 路径读取被拒（如提权进程）时退回仅进程名判定——MAS 通常自己拉起
    启动器，等待窗口期内的同名兜底可以接受。
    """
    name = _process_name(pid)
    if name is None or name.casefold() not in _LAUNCHER_PROCESS_NAMES:
        return False
    exe = _process_exe(pid)
    if exe is None:
        return True
    return exe.casefold().startswith(root_prefix)


def _find_launcher_hwnd(launcher_path: Path) -> int | None:
    """在启动器安装根目录树内按进程家族找最大可见窗口；不存在返回 None。"""
    root_prefix = str(launcher_path.parent).casefold().rstrip("\\/") + "\\"
    candidates: list[int] = []

    def _enum(hwnd: int, _lparam: int) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid and _is_launcher_process(pid, root_prefix):
            candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_enum, 0)
    return max(candidates, key=_window_area) if candidates else None


def find_launcher_pids(launcher_path: Path) -> list[int]:
    """按启动器进程家族找 pid（顶层引导器 + 版本目录下的主程序）。

    供任务清理使用：launcher.exe 是通用进程名，kill 误杀不可恢复，口径比窗口
    定位更保守——必须「exe 可读且位于启动器安装根目录树内」双条件同时满足；
    exe 读取被拒的同名进程跳过并打警告（多为提权进程，普通权限下本就杀不动）。
    """
    root_prefix = str(launcher_path.parent).casefold().rstrip("\\/") + "\\"
    pids: list[int] = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            name = (process.info["name"] or "").casefold()
            if name not in _LAUNCHER_PROCESS_NAMES:
                continue
            exe = process.info["exe"]
            if exe is None:
                logger.warning(
                    f"同名启动器进程 exe 不可读，跳过清理以免误杀: pid={process.pid}"
                )
                continue
            if not exe.casefold().startswith(root_prefix):
                continue
            pids.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return pids


def has_launcher_window(launcher_path: Path) -> bool:
    """清理后复核启动器窗口是否仍存在。

    find_launcher_pids 为防误杀跳过 exe 不可读（提权）的同名进程，这类进程
    不会被自动结束；本函数复用窗口定位的容忍口径复核一次，供清理方提示用户
    手工确认，避免静默残留。
    """
    return _find_launcher_hwnd(launcher_path) is not None


def _find_game_hwnd() -> int | None:
    return _find_hwnd(_GAME_PROCESS, _GAME_WINDOW_CLASS)


def _wait_launcher_hwnd(
    launcher_path: Path, *, timeout: int | None = None
) -> int | None:
    """轮询等待启动器窗口创建。

    启动器进程被拉起后窗口创建需要时间（单次查找会瞬时误判失败）；窗口由
    版本目录下的 launcher_main.exe 承载，家族匹配可同时覆盖引导器与主程序，
    也兼容启动器自重启后的新进程。
    """
    deadline = time.monotonic() + (timeout or _LAUNCHER_WINDOW_TIMEOUT)
    while True:
        hwnd = _find_launcher_hwnd(launcher_path)
        if hwnd is not None or time.monotonic() >= deadline:
            return hwnd
        time.sleep(2)


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("鸣潮启动器窗口已失效")
    show_command = (
        win32con.SW_RESTORE
        if win32gui.IsIconic(hwnd)
        else win32con.SW_SHOW
        if not win32gui.IsWindowVisible(hwnd)
        else None
    )
    if show_command is not None:
        win32gui.ShowWindow(hwnd, show_command)
        time.sleep(0.15)
    try:
        if win32gui.GetForegroundWindow() != hwnd:
            # Windows 前台锁：后台进程不能直接抢占前台。先附着当前前台窗口线程
            # 的输入队列，再置前，绕过系统限制（与账号切换同理）。
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
        logger.debug("鸣潮启动器窗口焦点请求被系统忽略，继续按前置窗口处理")
    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("鸣潮启动器窗口已失效或尺寸异常，可能启动器已关闭")
    return width, height


def _capture_window_image(hwnd: int, *, activate: bool = True) -> Image.Image:
    with _per_monitor_dpi():
        if activate:
            _activate_window(hwnd)
        width, height = _client_size(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        virtual_left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        virtual_top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        return pyautogui.screenshot(allScreens=True).crop(
            (
                left - virtual_left,
                top - virtual_top,
                left - virtual_left + width,
                top - virtual_top + height,
            )
        )


def _capture_window(hwnd: int, *, activate: bool = True) -> np.ndarray:
    screenshot = _capture_window_image(hwnd, activate=activate)
    screenshot = screenshot.resize(
        (_FRAME_WIDTH, _FRAME_HEIGHT), Image.Resampling.LANCZOS
    )
    return cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_RGB2BGR)


def _read_texts(hwnd: int) -> list[OCRItem]:
    return ocr_image(_capture_window(hwnd, activate=False))


def _click_box(
    hwnd: int, box: Box, *, activate: bool = False, after_sleep: float = 0.3
) -> None:
    """点击 1080p 坐标空间中的一个文字框中心。"""
    with _per_monitor_dpi():
        if activate:
            _activate_window(hwnd)
        width, height = _client_size(hwnd)
        x, y, box_width, box_height = box
        client_x = round((x + box_width / 2) * width / _FRAME_WIDTH)
        client_y = round((y + box_height / 2) * height / _FRAME_HEIGHT)
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))

    original_position = pyautogui.position()
    try:
        pyautogui.moveTo(screen_x, screen_y)
        time.sleep(0.3)
        pyautogui.click()
        time.sleep(after_sleep)
    finally:
        pyautogui.moveTo(*original_position)


# ── OCR 文本判定辅助 ─────────────────────────────────────────────────────


def _find_text(items: list[OCRItem], keywords: tuple[str, ...]) -> Box | None:
    for text, box in items:
        if any(keyword in text for keyword in keywords):
            return box
    return None


def _items_in_action_roi(items: list[OCRItem]) -> list[OCRItem]:
    """按文字框中心过滤出右下角动作区内的条目（排除左侧卡片等富文本干扰）。"""
    left, top, right, bottom = _ACTION_ROI
    selected: list[OCRItem] = []
    for text, (x, y, width, height) in items:
        center_x = x + width / 2
        center_y = y + height / 2
        if left <= center_x <= right and top <= center_y <= bottom:
            selected.append((text, (x, y, width, height)))
    return selected


def _download_progress_texts(items: list[OCRItem]) -> tuple[str, ...]:
    """取百分比/体积/速度相关文本并剥离计时（见常量说明），供进度签名使用。"""
    texts = []
    for text, _ in items:
        if any(token in text for token in _DOWNLOAD_PROGRESS_TOKENS):
            texts.append(_ELAPSED_TIME_PATTERN.sub("", text))
    return tuple(texts)


def _find_busy_box(items: list[OCRItem]) -> Box | None:
    """识别启动器忙碌态按钮（下载中/校验解压）；「预下载」不算忙碌。

    预下载开放且游戏可玩是官方预期状态，此时按钮区可能并存「进入游戏」与
    「预下载」，裸「下载」子串会误命中，故含「预」的条目一律排除。
    """
    for text, box in items:
        if "预" in text:
            continue
        if any(keyword in text for keyword in _BUSY_STATE_TEXTS):
            return box
    return None


# ── 屏保退出（挂机定时任务几乎必然带屏保运行）───────────────────────────
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
    必然带屏保运行，开工前先退出一次。
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


def _save_error_screenshot(launcher_hwnd: int | None) -> None:
    """保存启动失败时的窗口截图，便于排查 OCR 文本漂移。"""
    try:
        target = launcher_hwnd if launcher_hwnd is not None else _find_game_hwnd()
        if target is None:
            return
        save_error_screenshot(
            _capture_window_image(target, activate=False),
            "okww-launcher-start",
            "launcher-error",
        )
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始启动异常
        logger.warning(f"启动器启动错误截图保存失败: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def start_game_via_launcher(
    launcher_path: Path, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """通过官方启动器拉起鸣潮，直到客户端窗口出现（停在标题界面）。

    启动器按钮有概率是「更新」而非「进入游戏」（游戏有新版本时）：点「更新」
    后不再重复点击，等下载完成、按钮变回后再点。下载完成后启动器自动进入
    「校验解压」阶段，与下载同样按忙碌态动态续延等待，解压多久等多久；同时以
    百分比/体积/速度构造进度签名，长时间无变化判定卡死提前失败。

    状态判定与点击只认右下角动作区（左侧用户卡片/活动公告为富文本干扰源）。

    Args:
        launcher_path: 启动器 exe 路径（鸣潮官方启动器 launcher.exe）。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        游戏窗口就绪返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到启动器窗口 / 按钮点击失败 / 等待游戏窗口超时。
    """
    on_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("OK-WW 启动器启动仅支持 Windows 平台")

    # 开启诊断记录：窗口定位结果与各轮 OCR 全量条目写入 debug/okww-launcher-start/，
    # 供按钮未被点击时排查窗口错抓、截图偏移与 OCR 文本漂移
    global _DIAGNOSTIC_PATH
    diagnostic_dir = Path.cwd() / "debug" / "okww-launcher-start"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    _DIAGNOSTIC_PATH = diagnostic_dir / (
        f"launcher-detail-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    )

    # 挂机定时任务几乎必然带屏保运行：先退出屏保，避免截图全黑导致 OCR 全盲
    dismiss_screensaver()

    try:
        hwnd = _wait_launcher_hwnd(launcher_path)
        if hwnd is None:
            raise RuntimeError(
                f"等待启动器窗口超时（{_LAUNCHER_WINDOW_TIMEOUT}s 未找到 "
                f"{launcher_path} 拉起的启动器进程窗口，若启动器弹出 UAC 请先确认）"
            )
        _write_diagnostic(
            f"[{datetime.now():%H:%M:%S}] 启动器窗口 hwnd={hwnd} "
            f"{_describe_window(hwnd)}\n"
        )
        on_log("已定位启动器窗口，正在识别启动器按钮...")
        _activate_window(hwnd)

        start_clicks = 0
        last_start_click: float | None = None
        start_click_exhausted_logged = False
        exit_wait_polls = 0
        update_clicked = False
        last_update_click: float | None = None
        update_click_retries = 0
        update_exhausted_logged = False
        # 点「更新」后是否确实进入过下载/校验解压态：作为「按钮被取代」的强证据，
        # 避免单帧 OCR 漏识别按钮就误判为点击被吞而重复点击
        update_went_busy = False
        # 点「更新」后按钮是否已离开更新态（被下载 UI 取代过）：用于区分
        # 「更新刚点完、按钮文本尚未切换」与「下载结束、按钮真正变回」
        update_button_gone = False
        last_download_sig: int | None = None
        last_download_progress = time.monotonic()
        busy_since: float | None = None
        iter_count = 0
        deadline = time.monotonic() + _FIND_BUTTON_TIMEOUT
        while time.monotonic() < deadline:
            if _find_game_hwnd() is not None:
                on_log("已检测到鸣潮游戏窗口")
                return True

            try:
                items = _read_texts(hwnd)
            except RuntimeError:
                # 启动器点击「进入游戏」后会直接退出：只等游戏起窗
                if start_clicks > 0:
                    exit_wait_polls += 1
                    if exit_wait_polls == 1:
                        on_log("启动器已退出，正在等待游戏窗口出现...")
                    elif exit_wait_polls % 5 == 0:
                        on_log("仍在等待游戏窗口出现...")
                    time.sleep(2)
                    continue
                raise

            # 每 5 轮（≈10s）落一次 OCR 全量条目，空转时可从诊断文件定位
            if iter_count % 5 == 0:
                _write_diagnostic(f"\n[{datetime.now():%H:%M:%S}] 第 {iter_count} 轮\n")
                _dump_ocr_items(items)

            now = time.monotonic()

            # 弹窗防护：「提示」类弹窗以遮罩覆盖启动器，此时按钮仍可被 OCR
            # 看到，但点击会落在遮罩上被吞掉：必须先点「确定」/「忽略」关掉
            # 弹窗，本轮不再处理按钮（对齐 ok-nte launcher_popup_close 的
            # 防护顺序；其余弹窗状态待实测后补充）
            if any(text.strip() == "提示" for text, _ in items):
                popup_box = _find_text(items, ("确定",)) or _find_text(items, ("忽略",))
                if popup_box is not None:
                    on_log("检测到启动器「提示」弹窗，点击关闭...")
                    _click_box(hwnd, popup_box, after_sleep=2)
                    # 遮罩期「进入游戏」点击会被吞掉：关掉弹窗后重置点击计数
                    # 与间隔，立即可重试（耗尽提示标志一并重置，恢复后再次耗尽
                    # 仍能提示）
                    start_clicks = 0
                    last_start_click = None
                    start_click_exhausted_logged = False
                    time.sleep(1)
                    continue

            # 状态判定与点击只认右下角动作区，排除左侧富文本干扰
            action_items = _items_in_action_roi(items)

            # 游戏下载/校验解压进行中：基于忙碌态动态续延等待，并以进度签名
            # 检测卡死（校验解压阶段进度行为「过程不消耗流量 88.08%」）
            if _find_busy_box(action_items) is not None:
                if update_clicked:
                    update_went_busy = True
                if busy_since is None:
                    busy_since = now
                elif now - busy_since >= _BUSY_WAIT_HARD_LIMIT_SECONDS:
                    raise RuntimeError(
                        "启动器下载/校验解压超出"
                        f" {_BUSY_WAIT_HARD_LIMIT_SECONDS / 60:g} 分钟仍未完成，"
                        "请人工确认下载状态"
                    )
                deadline = max(deadline, now + _UPDATE_ACTIVE_GRACE_SECONDS)
                progress_texts = _download_progress_texts(action_items)
                # 动作区没识别到百分比/体积/速度时无法据此判卡死，交给上面的
                # 绝对上限兜底；有进度文本时才用「长时间不变」判卡死
                if progress_texts:
                    progress_sig = hash(progress_texts)
                    if progress_sig != last_download_sig:
                        last_download_sig = progress_sig
                        last_download_progress = now
                    elif now - last_download_progress >= _DOWNLOAD_STALL_SECONDS:
                        raise RuntimeError(
                            f"启动器下载/校验解压长时间无进展"
                            f"（{_DOWNLOAD_STALL_SECONDS:g}s 内百分比/体积/速度无变化，"
                            "疑似卡住），请人工确认下载状态"
                        )
                time.sleep(2)
                continue
            # 离开忙碌态：清掉忙碌基准，避免下次进入时用到过期时刻
            busy_since = None
            last_download_sig = None

            start_box = _find_text(action_items, ("进入游戏",))
            update_box = None if start_box else _find_text(action_items, ("更新",))
            if start_box is not None and update_clicked:
                # 「进入游戏」出现即更新流程已结束（无论更新是否真正执行过）：
                # 清理更新标记，避免残留污染超时报错文案与补点日志措辞
                on_log("启动器按钮已变为「进入游戏」，更新流程结束")
                update_clicked = False
                update_button_gone = False
                update_went_busy = False
                update_click_retries = 0
                update_exhausted_logged = False
            if update_clicked and update_went_busy and update_box is None:
                # 必须「进入过下载态」才算按钮被真正取代，单帧漏识别不算
                update_button_gone = True
            if update_box is not None and update_clicked and update_button_gone:
                # 下载结束后按钮已真正变回（中间被下载 UI 取代过）：重置更新
                # 标记允许再次点击（更新后需再点一次「更新」应用时由此入口进入）
                on_log("启动器按钮已恢复，继续处理...")
                update_clicked = False
                update_button_gone = False
                update_went_busy = False
                update_click_retries = 0
                update_exhausted_logged = False
            if start_box is not None and start_clicks >= _START_CLICK_LIMIT:
                if not start_click_exhausted_logged:
                    start_click_exhausted_logged = True
                    on_log(
                        f"「进入游戏」已点击 {_START_CLICK_LIMIT} 次仍未生效，"
                        "停止点击并继续等待（可能被遮挡或启动器异常）"
                    )
            elif (
                start_box is not None
                and start_clicks < _START_CLICK_LIMIT
                and (
                    last_start_click is None
                    or now - last_start_click >= _START_CLICK_INTERVAL_SECONDS
                )
            ):
                if start_clicks == 0:
                    on_log("点击启动器「进入游戏」")
                else:
                    on_log(
                        f"第 {start_clicks + 1} 次点击「进入游戏」"
                        "（此前点击未生效，可能被遮挡）"
                    )
                _click_box(hwnd, start_box, after_sleep=3)
                start_clicks += 1
                last_start_click = now
                deadline = max(deadline, now + _START_GAME_TIMEOUT)
            elif update_box is not None and not update_clicked:
                on_log("检测到启动器「更新」按钮，正在更新游戏，等待时间将延长...")
                _click_box(hwnd, update_box, after_sleep=3)
                update_clicked = True
                last_update_click = now
                deadline = max(deadline, now + _UPDATE_TIMEOUT)
            elif (
                update_box is not None
                and update_clicked
                and not update_went_busy
                and not update_button_gone
                and last_update_click is not None
                and now - last_update_click >= _UPDATE_CLICK_RETRY_SECONDS
            ):
                # 点击「更新」后按钮长时间停留原状（未被下载/进度 UI 取代）：
                # 判定点击被吞，按间隔补点
                if update_click_retries < _UPDATE_CLICK_RETRY_LIMIT:
                    on_log("「更新」点击未生效，补点一次...")
                    _click_box(hwnd, update_box, after_sleep=3)
                    update_click_retries += 1
                    last_update_click = now
                elif not update_exhausted_logged:
                    update_exhausted_logged = True
                    on_log(
                        f"「更新」已补点 {_UPDATE_CLICK_RETRY_LIMIT} 次仍未生效，"
                        "停止补点并继续等待（可能被遮挡或启动器异常）"
                    )
            if iter_count % 5 == 0:
                sample = (
                    " / ".join(text for text, _ in action_items[:6])
                    or "（动作区未识别到文本）"
                )
                on_log(f"仍在等待启动器按钮，动作区识别: {sample}")
            iter_count += 1
            time.sleep(2)

        if _find_game_hwnd() is not None:
            on_log("已检测到鸣潮游戏窗口")
            return True
        raise RuntimeError(
            "等待鸣潮游戏窗口超时"
            + ("（游戏更新可能未完成，请人工确认启动器状态）" if update_clicked else "")
        )
    except Exception:
        # 失败留启动器/游戏原图，供排查 OCR 文本漂移
        try:
            _save_error_screenshot(_wait_launcher_hwnd(launcher_path, timeout=5))
        except Exception:
            pass
        raise
    finally:
        _DIAGNOSTIC_PATH = None


async def async_start_game_via_launcher(
    launcher_path: Path, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """async 版本：在后台线程执行启动器交互，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        start_game_via_launcher, launcher_path, on_log=on_log
    )
