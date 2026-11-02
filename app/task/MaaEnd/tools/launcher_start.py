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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""终末地经官方启动器拉起游戏（Game.LaunchMode == "Launcher"）。

启动器是鹰角的多游戏启动器：自动识别根目录下稳定的 ``Launcher.exe``，
真正的界面窗口由版本目录下的 ``Games.exe`` 承载（版本目录随启动器自更新变化，
如 ``<根>\\1.6.0\\``），因此窗口定位与进程清理都按「进程家族 + exe 位于启动器安装
根目录树内」双重限定；手动指定的其他程序按完整路径匹配——
``Launcher.exe`` / ``Games.exe`` 都是常见进程名，单按名
匹配会误伤无关程序。

流程（对齐 MAS 内 ok-ww / ok-nte 的启动器方案）::

    退出屏保 → 拉起 Launcher.exe → 等启动器窗口 → OCR 右下角动作区找按钮
    · 按钮是「更新游戏」：点击 → 出现「系统提示」弹窗（所需/剩余空间）→ 点「确认」
      → 按钮变「正在下载」，按下载态动态续延等待（多久等多久）；下载完成后
      自动进入「安装中」「校验中」（无需干预），完毕后按钮变回「开始游戏」
    · 按钮是「开始游戏」：点击 → 等 Endfield.exe 可见窗口出现
    · 弹窗是「检测到启动器版本更新」：点「更新」交给官方 updater（绝不点「退出」）
      → 原启动器窗口退出，updater 独立窗口自行下载安装 → 完成后自动拉起新版
      启动器窗口，重新定位窗口并重置状态继续
    点击被吞时按时间间隔补点，至多 _START_CLICK_LIMIT 次

界面文案只覆盖国服启动器（更新游戏 / 开始游戏 / 正在下载 / 系统提示 / 确认 /
启动器版本更新）；国际服 GRYPHLINK 的按钮文案不同，识别不到时按超时失败处理。
"""

import asyncio
import ctypes
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Event

import cv2
import numpy as np
import psutil
from PIL import Image

from app.services import endfield_launcher as _service_endfield_launcher
from app.tools import error_screenshot as _tool_error_screenshot
from app.tools import ocr as _tool_ocr
from app.utils import IS_WINDOWS, get_logger
from app.utils import display as _utils_display

if IS_WINDOWS:
    # pyautogui 与 pywin32 仅 Windows 可用（无图形会话导入即失败），随入口的
    # IS_WINDOWS 检查一并惰性导入
    import pyautogui
    import win32api
    import win32con
    import win32gui
    import win32process

logger = get_logger("MaaEnd 启动器启动")


class _LaunchCancelled(Exception):
    """内部停止信号；取消不作为启动失败截图或重试。"""


def _pause(seconds: float, stop_event: Event | None = None) -> None:
    if stop_event is None:
        time.sleep(seconds)
    elif stop_event.wait(seconds):
        raise _LaunchCancelled()


# 游戏客户端进程名：Endfield.exe 出现可见窗口即视为游戏就绪
_GAME_PROCESS = "Endfield.exe"

# 启动器进程家族：根目录 Launcher.exe 是引导器，界面窗口属于版本目录下的 Games.exe；
# 家族匹配还须限定 exe 位于启动器安装根目录树内（对齐 ok-ww 的 launcher 家族口径）
_LAUNCHER_PROCESS_NAMES = frozenset({"launcher.exe", "games.exe"})

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# 右下角动作区（相对 1080p 帧）：启动按钮与下载状态都在此区域；左侧游戏列表、
# 中间公告/新闻列表含大量富文本，不参与判定与点击，避免干扰误触
_ACTION_ROI: _tool_ocr.Box = (1380, 860, 1920, 1080)

# 主按钮文案（国服启动器）：有更新时是「更新游戏」，无更新时是「开始游戏」，
# 下载中是「正在下载」。次要的「DirectX 11 启动（游戏异常时使用）」不含这些词，
# 不会被误点。
_START_GAME_TEXTS = ("开始游戏",)
_UPDATE_GAME_TEXTS = ("更新游戏",)
# 下载结束后的安装/校验阶段按钮文案：实测全自动且不拦截开始游戏，按忙碌态
# 一并续延等待，防止安装校验耗时超过下载宽限期被误判超时
_INSTALL_PHASE_TEXTS = ("安装中", "校验中")
# 忙碌态判定文本：下载中的按钮文案与「暂停下载」附带按钮，加安装/校验阶段；
# 裸「下载」用于容忍 OCR 拆词。「预下载」开放且游戏可玩是官方预期状态，
# 含「预」的条目必须排除（见 _find_busy_box）
_BUSY_STATE_TEXTS = ("正在下载", "下载中", "暂停下载", "下载") + _INSTALL_PHASE_TEXTS
# 更新确认弹窗（「系统提示」+ 所需/剩余空间）：弹窗居中，不受动作区限制；
# 「取消」与「确认」同屏，必须按精确文案点「确认」/「确定」，绝不点「取消」
_DIALOG_TITLE_TEXTS = ("系统提示",)
_DIALOG_SPACE_TEXTS = ("所需空间", "剩余空间")
_DIALOG_CONFIRM_TEXTS = ("确认", "确定")
# 启动器自更新弹窗：正文「检测到启动器版本更新」，按钮「退出/更新」并排；
# 点「更新」交给官方 updater，绝不点「退出」
_LAUNCHER_SELF_UPDATE_TEXTS = ("启动器版本更新", "启动器更新")
_SELF_UPDATE_EXIT_TEXTS = ("退出",)
_SELF_UPDATE_CONFIRM_TEXTS = ("更新",)
# 自更新按钮行（1080p 基准）：整词「退出」与「更新」同行并排的水平跨度上限
_SELF_UPDATE_BUTTON_ROW_SPAN = 400
# 点「更新」后 updater 独立窗口自行下载安装并拉起新版启动器窗口，此间原窗口
# 已失效；等待新版窗口恢复的总上限
_SELF_UPDATE_RESTART_TIMEOUT = 600
# 恢复等待用短拍轮询：单次长等会错过循环顶的游戏窗口判定，须短拍回主循环复查
_SELF_UPDATE_POLL_SECONDS = 5

# 下载进度相关文本特征：用于构造「下载进度签名」，只看含百分比/体积/速度的条目；
# 计时文本必须剥离，否则计时器每秒变化会掩盖真实进度停滞
_DOWNLOAD_PROGRESS_TOKENS = ("%", "MB", "GB", "KB")
_ELAPSED_TIME_PATTERN = re.compile(r"\d{1,}:\d{2}(?::\d{2})*")

# 首次找到按钮的等待；点击「开始游戏」后等游戏起窗；点「更新」后等更新完成
_FIND_BUTTON_TIMEOUT = 120
_START_GAME_TIMEOUT = 300
# 更新类等待上限：游戏包体大，慢网下 30 分钟不够，放宽到 2 小时；该值仅为点击
# 「更新游戏」后尚未出现下载 UI 的兜底等待，进入下载态后由忙碌态持续动态续延
_UPDATE_TIMEOUT = 7200
# 启动器拉起后等其窗口创建的时限
_LAUNCHER_WINDOW_TIMEOUT = 120

# 检测到下载态时每次顺延的等待宽限（下载 UI 持续存在就持续等，等效不设总时限）
_UPDATE_ACTIVE_GRACE_SECONDS = 600.0
# 下载进度签名持续无变化的时长上限：百分比/体积/速度长时间不动视为下载卡死
_DOWNLOAD_STALL_SECONDS = 300.0
# 下载态等待的绝对上限：单次下载最多等这么久，防止进度文本持续抖动时既判不出
# 卡死也无法退出（正常下载远超此时长才会触发，属防意外兜底）
_BUSY_WAIT_HARD_LIMIT_SECONDS = 7200.0
# 「开始游戏」点击重试：被遮挡等场景点击可能被吞，按时间间隔重试并保留宽松总
# 上限防死循环；点击生效时启动器会退出或最小化，按钮消失即停止重试
_START_CLICK_LIMIT = 8
_START_CLICK_INTERVAL_SECONDS = 12.0
# 「更新游戏」点击重试：单次点击防重复下载是有意设计，但点击被吞时需按间隔补点，
# 以按钮长时间停留原状（未被下载 UI 取代）为被吞判据；自更新「更新」补点共用该节奏
_UPDATE_CLICK_RETRY_SECONDS = 15.0
_UPDATE_CLICK_RETRY_LIMIT = 3


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


def _root_prefix(launcher_path: Path) -> str:
    """启动器安装根目录树前缀（casefold、带尾部分隔符），用于 exe 归属判定。"""
    return (
        str(_service_endfield_launcher.launcher_root(launcher_path))
        .casefold()
        .rstrip("\\/")
        + "\\"
    )


def _find_process_hwnd(process_name: str) -> int | None:
    """按所属进程名找最大可见窗口；不存在返回 None。"""
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


def _matches_launcher_exe(exe: str, launcher_path: Path) -> bool:
    """匹配所选程序本身，或同目录树内已知的启动器家族程序。"""
    process_path = Path(exe)
    if str(process_path).casefold() == str(launcher_path).casefold():
        return True
    return process_path.name.casefold() in _LAUNCHER_PROCESS_NAMES and str(
        process_path
    ).casefold().startswith(_root_prefix(launcher_path))


def _is_launcher_process(pid: int, launcher_path: Path) -> bool:
    """判定 pid 是否属于启动器进程家族（进程名 + exe 位于安装根目录树内）。

    exe 路径读取被拒（如提权进程）时退回仅进程名判定——等待窗口期内的同名
    兜底可以接受。
    """
    exe = _process_exe(pid)
    if exe is not None:
        return _matches_launcher_exe(exe, launcher_path)
    name = _process_name(pid)
    return name is not None and name.casefold() in _LAUNCHER_PROCESS_NAMES


def _find_launcher_hwnd(launcher_path: Path) -> int | None:
    """在启动器安装根目录树内按进程家族找最大可见窗口；不存在返回 None。"""
    candidates: list[int] = []

    def _enum(hwnd: int, _lparam: int) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid and _is_launcher_process(pid, launcher_path):
            candidates.append(hwnd)
        return True

    win32gui.EnumWindows(_enum, 0)
    return max(candidates, key=_window_area) if candidates else None


def find_launcher_pids(launcher_path: Path) -> list[int]:
    """按启动器进程家族找 pid（根目录引导器 + 版本目录下的界面程序）。

    供任务清理使用：Launcher.exe / Games.exe 是通用进程名，kill 误杀不可恢复，
    口径比窗口定位更保守——必须「exe 可读且位于安装根目录树内」双条件同时满足；
    exe 读取被拒的同名进程跳过并打警告（多为提权进程，普通权限下本就杀不动）。
    """
    pids: list[int] = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            exe = process.info["exe"]
            if exe is None:
                name = (process.info["name"] or "").casefold()
                if (
                    name in _LAUNCHER_PROCESS_NAMES
                    or name == launcher_path.name.casefold()
                ):
                    logger.warning(
                        f"同名启动器进程 exe 不可读，跳过清理以免误杀: pid={process.pid}"
                    )
                continue
            if _matches_launcher_exe(exe, launcher_path):
                pids.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return pids


def _wait_launcher_hwnd(
    launcher_path: Path, *, timeout: int | None = None, stop_event: Event | None = None
) -> int | None:
    """轮询等待启动器窗口创建。

    启动器进程被拉起后窗口创建需要时间（单次查找会瞬时误判失败）；窗口由版本
    目录下的 Games.exe 承载，家族匹配可同时覆盖根目录引导器与界面程序，也兼容
    启动器自更新后的新版本目录。
    """
    deadline = time.monotonic() + (timeout or _LAUNCHER_WINDOW_TIMEOUT)
    while True:
        _pause(0, stop_event)
        hwnd = _find_launcher_hwnd(launcher_path)
        if hwnd is not None or time.monotonic() >= deadline:
            return hwnd
        _pause(2, stop_event)


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int, *, stop_event: Event | None = None) -> None:
    _pause(0, stop_event)
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("终末地启动器窗口已失效")
    show_command = (
        win32con.SW_RESTORE
        if win32gui.IsIconic(hwnd)
        else win32con.SW_SHOW
        if not win32gui.IsWindowVisible(hwnd)
        else None
    )
    if show_command is not None:
        win32gui.ShowWindow(hwnd, show_command)
        _pause(0.15, stop_event)
    try:
        if win32gui.GetForegroundWindow() != hwnd:
            # Windows 前台锁：后台进程不能直接抢占前台。先附着当前前台窗口线程
            # 的输入队列，再置前，绕过系统限制
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
        logger.debug("终末地启动器窗口焦点请求被系统忽略，继续按前置窗口处理")
    _pause(0.1, stop_event)


def _client_size(hwnd: int) -> tuple[int, int]:
    try:
        _, _, width, height = win32gui.GetClientRect(hwnd)
    except win32gui.error as error:
        raise RuntimeError("终末地启动器窗口已失效，可能启动器已关闭") from error
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地启动器窗口已失效或尺寸异常，可能启动器已关闭")
    return width, height


def _capture_window_image(hwnd: int, *, activate: bool = True) -> Image.Image:
    with _utils_display.per_monitor_dpi():
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


def _read_texts(hwnd: int) -> list[_tool_ocr.OCRItem]:
    return _tool_ocr.ocr_image(_capture_window(hwnd, activate=False))


def _click_box(
    hwnd: int,
    box: _tool_ocr.Box,
    *,
    activate: bool = False,
    after_sleep: float = 0.3,
    stop_event: Event | None = None,
) -> None:
    """点击 1080p 坐标空间中的一个文字框中心。"""
    _pause(0, stop_event)
    with _utils_display.per_monitor_dpi():
        if activate:
            _activate_window(hwnd, stop_event=stop_event)
        width, height = _client_size(hwnd)
        x, y, box_width, box_height = box
        client_x = round((x + box_width / 2) * width / _FRAME_WIDTH)
        client_y = round((y + box_height / 2) * height / _FRAME_HEIGHT)
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))

    original_position = pyautogui.position()
    try:
        _pause(0, stop_event)
        pyautogui.moveTo(screen_x, screen_y)
        _pause(0.3, stop_event)
        pyautogui.click()
        _pause(after_sleep, stop_event)
    finally:
        pyautogui.moveTo(*original_position)


# ── OCR 文本判定辅助 ─────────────────────────────────────────────────────


def _find_text(
    items: list[_tool_ocr.OCRItem], keywords: tuple[str, ...]
) -> _tool_ocr.Box | None:
    for text, box in items:
        if any(keyword in text for keyword in keywords):
            return box
    return None


def _find_dialog_button(
    items: list[_tool_ocr.OCRItem], labels: tuple[str, ...]
) -> _tool_ocr.Box | None:
    """弹窗按钮按整词匹配：正文说明文字里出现同词时不能误点（_find_text 是子串匹配），
    且 OCR 条目自上而下排列，正文先于按钮出现。"""

    for text, box in items:
        if text.strip() in labels:
            return box
    return None


def _find_self_update_button(items: list[_tool_ocr.OCRItem]) -> _tool_ocr.Box | None:
    """自更新弹窗按钮行定位：整词「退出」「更新」同行并排是该弹窗的强特征。

    以整词「退出」为锚，只接受同一按钮行（中心 y 相差不超过按钮高）、位于其
    右侧且水平间距不超过一个按钮行跨度的整词「更新」；公告正文命中自更新
    文案而别处散落孤立的「更新」时不会出手。
    """
    exit_box = next(
        (box for text, box in items if text.strip() in _SELF_UPDATE_EXIT_TEXTS),
        None,
    )
    if exit_box is None:
        return None
    exit_x, exit_y, exit_w, exit_h = exit_box
    exit_center_y = exit_y + exit_h / 2
    for text, box in items:
        if text.strip() not in _SELF_UPDATE_CONFIRM_TEXTS:
            continue
        x, y, _, h = box
        if (
            abs(y + h / 2 - exit_center_y) <= exit_h
            and x > exit_x + exit_w
            and x - (exit_x + exit_w) <= _SELF_UPDATE_BUTTON_ROW_SPAN
        ):
            return box
    return None


def _items_in_action_roi(items: list[_tool_ocr.OCRItem]) -> list[_tool_ocr.OCRItem]:
    """按文字框中心过滤出右下角动作区内的条目（排除左侧列表等富文本干扰）。"""
    left, top, right, bottom = _ACTION_ROI
    selected: list[_tool_ocr.OCRItem] = []
    for text, (x, y, width, height) in items:
        center_x = x + width / 2
        center_y = y + height / 2
        if left <= center_x <= right and top <= center_y <= bottom:
            selected.append((text, (x, y, width, height)))
    return selected


def _download_progress_texts(items: list[_tool_ocr.OCRItem]) -> tuple[str, ...]:
    """取百分比/体积/速度相关文本并剥离计时（见常量说明），供进度签名使用。"""
    texts = []
    for text, _ in items:
        if any(token in text for token in _DOWNLOAD_PROGRESS_TOKENS):
            texts.append(_ELAPSED_TIME_PATTERN.sub("", text))
    return tuple(texts)


def _find_busy_box(items: list[_tool_ocr.OCRItem]) -> _tool_ocr.Box | None:
    """识别启动器下载态按钮；「预下载」不算忙碌。

    预下载开放且游戏可玩是官方预期状态，此时按钮区可能并存「开始游戏」与
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


def dismiss_screensaver(*, stop_event: Event | None = None) -> None:
    """屏保运行时轻推鼠标将其退出（旁路：失败仅记日志，不阻断启动流程）。

    屏保全屏覆盖会让窗口截图变成黑屏，OCR 找不到任何按钮；挂机定时任务几乎
    必然带屏保运行，开工前先退出一次。
    """
    if not _screensaver_running():
        return
    logger.info("检测到屏幕保护程序正在运行，轻推鼠标退出...")
    original_position = None
    try:
        x, y = pyautogui.position()
        original_position = (x, y)
        deadline = time.monotonic() + 10
        offset = 50
        while _screensaver_running() and time.monotonic() < deadline:
            _pause(0, stop_event)
            pyautogui.moveTo(x + offset, y)
            offset = -offset
            _pause(1, stop_event)
    except _LaunchCancelled:
        raise
    except Exception as error:
        logger.warning(f"退出屏幕保护程序失败（忽略，继续启动流程）: {error}")
    finally:
        if original_position is not None:
            pyautogui.moveTo(*original_position)


def _save_error_screenshot(
    launcher_path: Path,
    *,
    on_error_screenshot: Callable[[Path], None] | None = None,
) -> None:
    """保存启动失败时的窗口截图，便于排查 OCR 文本漂移。"""
    try:
        target = _find_launcher_hwnd(launcher_path)
        if target is None:
            target = _find_game_hwnd()
        if target is None:
            return
        screenshot_path = _tool_error_screenshot.save_error_screenshot(
            _capture_window_image(target, activate=False),
            "maaend-launcher-start",
            "launcher-error",
        )
        if screenshot_path is not None and on_error_screenshot is not None:
            on_error_screenshot(screenshot_path)
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始启动异常
        logger.warning(f"启动器启动错误截图保存失败: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def start_game_via_launcher(
    launcher_path: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    on_error_screenshot: Callable[[Path], None] | None = None,
    stop_event: Event | None = None,
) -> bool:
    """通过官方启动器拉起终末地，直到 Endfield.exe 窗口出现（停在标题界面）。

    启动器按钮有概率是「更新游戏」而非「开始游戏」（游戏有新版本时）：点
    「更新游戏」后出现「系统提示」弹窗，点「确认」开始下载，等下载完成并自动
    走完「安装中」「校验中」（无需干预）、按钮变回「开始游戏」后再点。下载与
    安装校验进行中按忙碌态动态续延等待，下载多久等多久；
    同时以百分比/体积/速度构造进度签名，长时间无变化判定下载卡死提前失败。

    启动器自身也可能弹出「检测到启动器版本更新」弹窗：点「更新」交给官方
    updater 独立窗口自行下载安装（绝不点「退出」），原启动器窗口随之退出；
    updater 完成后自动拉起新版启动器窗口，重新定位窗口并重置状态继续。

    启动器拉起后会显示「系统提示」等居中弹窗，遮罩下按钮点击会被吞掉，故每轮
    先关掉弹窗再处理按钮；「取消」与「确认」同屏，一律只点「确认」/「确定」。

    Args:
        launcher_path: 自动识别或手动指定的启动器 exe 路径。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。
        on_error_screenshot: 将本次保存的失败截图交给任务报告。
        stop_event: 异步任务取消时置位，交互线程在下一次操作前退出。

    Returns:
        游戏窗口就绪返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到启动器窗口 / 按钮点击失败 / 等待游戏窗口超时。
    """
    dispatch_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("MaaEnd 启动器启动仅支持 Windows 平台")
    # 光标停在主屏四角时 pyautogui 全部鼠标/键盘操作都会在真实移动前抛
    # FailSafeException 且重试无法自愈；MAS 属无人值守托管，停用四角 fail-safe
    previous_failsafe = pyautogui.FAILSAFE
    pyautogui.FAILSAFE = False
    stop_event = stop_event or Event()

    diagnostic_path: Path | None = (
        Path.cwd()
        / "debug"
        / "maaend-launcher-start"
        / f"launcher-detail-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    )

    def _write_diagnostic(text: str) -> None:
        """诊断旁路失败不得覆盖启动异常；写入失败后停止本次记录。"""
        nonlocal diagnostic_path
        if diagnostic_path is None:
            return
        try:
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            with diagnostic_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now():%H:%M:%S}] {text}\n")
        except OSError as error:
            logger.warning(f"启动器诊断记录保存失败: {error}")
            diagnostic_path = None

    def _on_log(text: str) -> None:
        _write_diagnostic(text)
        dispatch_log(text)

    on_log = _on_log
    _write_diagnostic(f"开始启动终末地，启动器: {launcher_path}")

    try:
        _pause(0, stop_event)
        dismiss_screensaver(stop_event=stop_event)
        hwnd = _wait_launcher_hwnd(launcher_path, stop_event=stop_event)
        if hwnd is None:
            raise RuntimeError(
                f"等待启动器窗口超时（{_LAUNCHER_WINDOW_TIMEOUT}s 未找到 "
                f"{_service_endfield_launcher.launcher_root(launcher_path)} 下的启动器窗口，"
                "若启动器弹出 UAC 请先确认）"
            )
        _activate_window(hwnd, stop_event=stop_event)

        start_clicks = 0
        last_start_click: float | None = None
        start_click_exhausted_logged = False
        exit_wait_polls = 0
        update_clicked = False
        last_update_click: float | None = None
        update_click_retries = 0
        update_exhausted_logged = False
        # 启动器自更新进行中：原窗口已让位给 updater，等待新版窗口恢复；
        # 自更新等待起点用于约束恢复总时长
        self_update_wait = False
        self_update_clicks = 0
        last_self_update_click: float | None = None
        self_update_since: float | None = None
        # 自更新补点耗尽与按钮定位失败的提示只报一次
        self_update_exhausted_logged = False
        self_update_button_missed_logged = False
        # 点「更新游戏」后是否确实进入过下载态：作为「按钮被取代」的强证据，
        # 避免单帧 OCR 漏识别按钮就误判为点击被吞而重复点击
        update_went_busy = False
        # 下载会话跨帧累计；短暂 OCR 漏识别不代表下载完成，不能重置基准。
        busy_since: float | None = None
        last_download_sig: int | None = None
        last_download_progress = time.monotonic()
        # 安装/校验阶段进入日志只报一次；离开该阶段即复位，支持同一轮内再次更新
        install_phase_logged = False
        last_ocr_texts: tuple[str, ...] | None = None
        last_ocr_dump = 0.0
        deadline = time.monotonic() + _FIND_BUTTON_TIMEOUT

        while time.monotonic() < deadline:
            _pause(0, stop_event)
            if _find_game_hwnd() is not None:
                on_log("已检测到终末地游戏窗口")
                return True

            if self_update_wait:
                # 自更新中：原窗口已让位给 updater。等待态检查放在循环顶，无论
                # 旧窗口是否仍可读都不再对已让位的窗口出手；每拍回循环顶复查
                # 游戏窗口——单次长等会把「间隙期已点到开始游戏、启动器正常
                # 退出」误判成自更新失败；恢复总时长仍受上限约束，超限才报
                # 人工确认
                if self_update_since is not None and (
                    time.monotonic() - self_update_since >= _SELF_UPDATE_RESTART_TIMEOUT
                ):
                    raise RuntimeError(
                        "启动器自更新后未恢复启动器窗口，请人工确认启动器状态"
                    ) from None
                new_hwnd = _wait_launcher_hwnd(
                    launcher_path,
                    timeout=_SELF_UPDATE_POLL_SECONDS,
                    stop_event=stop_event,
                )
                if new_hwnd is not None and not win32gui.IsWindow(hwnd):
                    # 旧窗口已失效后再找到的启动器窗口必是新版（句柄值可能被
                    # 复用，不能以 new_hwnd != hwnd 判新）：全量重置流程状态，
                    # 界面重新探测
                    on_log("新版启动器窗口已就绪，继续启动流程...")
                    hwnd = new_hwnd
                    _activate_window(hwnd, stop_event=stop_event)
                    start_clicks = 0
                    last_start_click = None
                    start_click_exhausted_logged = False
                    exit_wait_polls = 0
                    update_clicked = False
                    last_update_click = None
                    update_click_retries = 0
                    update_exhausted_logged = False
                    update_went_busy = False
                    busy_since = None
                    last_download_sig = None
                    last_download_progress = time.monotonic()
                    install_phase_logged = False
                    last_ocr_texts = None
                    last_ocr_dump = 0.0
                    self_update_wait = False
                    self_update_clicks = 0
                    last_self_update_click = None
                    self_update_since = None
                    self_update_exhausted_logged = False
                    self_update_button_missed_logged = False
                    deadline = max(deadline, time.monotonic() + _FIND_BUTTON_TIMEOUT)
                # 旧窗口仍在（updater 尚未接管）或新版窗口未出现：保持等待态
                # 继续观察，不重置状态，也不对已让位的窗口重新点「更新」
                _pause(2, stop_event)
                continue

            try:
                items = _read_texts(hwnd)
            except (RuntimeError, win32gui.error):
                # 自更新等待已在循环顶统一处理；启动器点击「开始游戏」后会退出
                # 或最小化：只等游戏起窗
                if start_clicks > 0:
                    exit_wait_polls += 1
                    if exit_wait_polls == 1:
                        on_log("启动器已退出，正在等待游戏窗口出现...")
                    elif exit_wait_polls % 5 == 0:
                        on_log("仍在等待游戏窗口出现...")
                    _pause(2, stop_event)
                    continue
                raise

            now = time.monotonic()
            ocr_texts = tuple(text for text, _ in items)
            # 识别文本变化时留痕；相同画面每 30 秒采样一次，避免下载期日志膨胀。
            if ocr_texts != last_ocr_texts or now - last_ocr_dump >= 30:
                _write_diagnostic(
                    "OCR: "
                    + repr(items)
                    + f"; 下载已等待={now - busy_since if busy_since is not None else 0:.0f}s"
                    + f"; 进度未变={now - last_download_progress:.0f}s"
                )
                last_ocr_texts = ocr_texts
                last_ocr_dump = now

            # 启动器自更新弹窗（正文「检测到启动器版本更新」，按钮「退出/更新」）：
            # 点「更新」交给官方 updater，绝不点「退出」。检测不依赖「系统提示」
            # 标题（标题行漏识别会让整个分支不可达），但正文子串可能被新闻/公告
            # 命中，出手须先定位「退出+更新」按钮行；按钮定位不到或补点耗尽时
            # 不劫持，留提示交给自更新恢复超时兜底
            if _find_text(items, _LAUNCHER_SELF_UPDATE_TEXTS) is not None:
                if self_update_clicks >= _UPDATE_CLICK_RETRY_LIMIT:
                    # 补点耗尽弹窗仍在：不再补点也不劫持后续处理，留提示交给
                    # 恢复超时兜底（总截止会给出自更新专属报错）
                    if not self_update_exhausted_logged:
                        self_update_exhausted_logged = True
                        on_log(
                            "自更新「更新」补点已耗尽且弹窗仍在，请人工确认启动器状态"
                        )
                else:
                    self_update_box = _find_self_update_button(items)
                    if self_update_box is not None:
                        if (
                            last_self_update_click is None
                            or now - last_self_update_click
                            >= _UPDATE_CLICK_RETRY_SECONDS
                        ):
                            on_log("检测到启动器自更新，点击「更新」并等待其完成...")
                            _click_box(
                                hwnd,
                                self_update_box,
                                after_sleep=3,
                                stop_event=stop_event,
                            )
                            self_update_clicks += 1
                            last_self_update_click = now
                            self_update_wait = True
                            if self_update_since is None:
                                self_update_since = now
                            # 自更新窗口恢复可能远超基准窗口期：整体截止一并顺延
                            # （恢复上限外加一次按钮探测期，超限时报自更新专属错误）
                            deadline = max(
                                deadline,
                                now
                                + _SELF_UPDATE_RESTART_TIMEOUT
                                + _FIND_BUTTON_TIMEOUT,
                            )
                        _pause(2, stop_event)
                        continue
                    # 正文命中但按钮行未定位到（按钮被 OCR 合并或未渲染）：不动手
                    # 不劫持，留一次提示交给后续处理与恢复超时兜底
                    if not self_update_button_missed_logged:
                        self_update_button_missed_logged = True
                        on_log("检测到自更新提示但未能定位「更新」按钮，继续观察...")

            # 更新确认弹窗（「系统提示」+ 所需/剩余空间）：「取消」与「确认」同屏，
            # 必须按精确文案点「确认」/「确定」，绝不点「取消」；弹窗居中，不受
            # 右下角动作区限制
            if _find_text(items, _DIALOG_TITLE_TEXTS) is not None:
                confirm_box = _find_dialog_button(items, _DIALOG_CONFIRM_TEXTS)
                if confirm_box is not None:
                    is_update_dialog = (
                        _find_text(items, _DIALOG_SPACE_TEXTS) is not None
                    )
                    on_log(
                        "检测到更新确认弹窗，点击「确认」开始下载..."
                        if is_update_dialog
                        else "检测到启动器弹窗，点击关闭..."
                    )
                    _click_box(hwnd, confirm_box, after_sleep=3, stop_event=stop_event)
                    # 遮罩期「开始游戏」点击会被吞掉：关掉弹窗后重置点击计数与
                    # 间隔，立即可重试（耗尽提示标志一并重置）
                    start_clicks = 0
                    last_start_click = None
                    start_click_exhausted_logged = False
                    if is_update_dialog:
                        # 点「确认」后进入下载：重置进度基准，等按钮变「正在下载」
                        update_went_busy = False
                        busy_since = None
                        last_download_sig = None
                        last_download_progress = now
                        deadline = max(deadline, now + _UPDATE_TIMEOUT)
                    _pause(2, stop_event)
                    continue

            # 状态判定与点击只认右下角动作区，排除左侧列表富文本干扰
            action_items = _items_in_action_roi(items)

            # 游戏下载/安装校验进行中：基于忙碌态动态续延等待，并以进度签名
            # 检测卡死；进入安装/校验阶段时留一条日志（全自动，无需干预）。
            # 动作区同帧出现「开始游戏」（阶段切换残影）时按恢复处理，不拦截点击
            if (
                _find_busy_box(action_items) is not None
                and _find_text(action_items, _START_GAME_TEXTS) is None
            ):
                if update_clicked:
                    update_went_busy = True
                install_phase = (
                    _find_text(action_items, _INSTALL_PHASE_TEXTS) is not None
                )
                if install_phase and not install_phase_logged:
                    on_log(
                        "下载已完成，启动器正在安装/校验游戏文件"
                        "（全自动，请勿关闭启动器）..."
                    )
                    install_phase_logged = True
                    # 安装校验的进度签名与下载分开计基准，避免跨阶段误判卡死
                    last_download_sig = None
                    last_download_progress = now
                elif not install_phase:
                    install_phase_logged = False
                if busy_since is None:
                    busy_since = now
                elif now - busy_since >= _BUSY_WAIT_HARD_LIMIT_SECONDS:
                    raise RuntimeError(
                        "启动器下载超出"
                        f" {_BUSY_WAIT_HARD_LIMIT_SECONDS / 60:g} 分钟仍未完成，"
                        "请人工确认下载状态"
                    )
                deadline = max(deadline, now + _UPDATE_ACTIVE_GRACE_SECONDS)
                progress_texts = _download_progress_texts(action_items)
                # 动作区没识别到百分比/体积/速度时无法据此判卡死，交给上面的
                # 绝对上限兜底；有进度文本时才用「长时间不变」判卡死。安装/校验
                # 阶段进度展示口径与下载不同，只按绝对上限兜底，不再按下载停滞
                # 判死，避免校验耗时超过下载停滞阈值被误报
                if progress_texts and not install_phase:
                    progress_sig = hash(progress_texts)
                    if progress_sig != last_download_sig:
                        last_download_sig = progress_sig
                        last_download_progress = now
                    elif now - last_download_progress >= _DOWNLOAD_STALL_SECONDS:
                        raise RuntimeError(
                            f"启动器下载长时间无进展（{_DOWNLOAD_STALL_SECONDS:g}s 内"
                            "百分比/体积/速度无变化，疑似卡住），请人工确认下载状态"
                        )
                _pause(2, stop_event)
                continue

            start_box = _find_text(action_items, _START_GAME_TEXTS)
            if start_box is not None:
                # 明确恢复「开始游戏」才视为下载结束；空帧与未知画面保留基准。
                busy_since = None
                last_download_sig = None
                install_phase_logged = False
            update_box = (
                None if start_box else _find_text(action_items, _UPDATE_GAME_TEXTS)
            )
            if start_box is not None and update_clicked:
                # 「开始游戏」已取代「更新游戏」：更新流程已结束，重置更新标记，
                # 允许再次点击进入游戏（更新后无重启弹窗时此处是唯一再点入口）
                on_log("游戏更新完成，按钮已恢复「开始游戏」，继续启动...")
                update_clicked = False
                last_update_click = None
                update_click_retries = 0
                update_exhausted_logged = False
                update_went_busy = False
                last_download_sig = None
                last_download_progress = now
            if start_box is not None and start_clicks >= _START_CLICK_LIMIT:
                if not start_click_exhausted_logged:
                    start_click_exhausted_logged = True
                    on_log(
                        f"「开始游戏」已点击 {_START_CLICK_LIMIT} 次仍未生效，"
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
                    on_log("点击启动器「开始游戏」")
                else:
                    on_log(
                        f"第 {start_clicks + 1} 次点击「开始游戏」"
                        "（此前点击未生效，可能被遮挡）"
                    )
                _click_box(hwnd, start_box, after_sleep=3, stop_event=stop_event)
                start_clicks += 1
                last_start_click = now
                deadline = max(deadline, now + _START_GAME_TIMEOUT)
            elif update_box is not None and not update_clicked:
                on_log("检测到启动器「更新游戏」按钮，正在更新游戏，等待时间将延长...")
                _click_box(hwnd, update_box, after_sleep=3, stop_event=stop_event)
                update_clicked = True
                last_update_click = now
                update_click_retries = 0
                update_exhausted_logged = False
                update_went_busy = False
                deadline = max(deadline, now + _UPDATE_TIMEOUT)
            elif (
                update_box is not None
                and update_clicked
                and not update_went_busy
                and last_update_click is not None
                and now - last_update_click >= _UPDATE_CLICK_RETRY_SECONDS
            ):
                # 点击「更新游戏」后按钮长时间停留原状（未进入下载态）：判定
                # 点击被吞，按间隔补点，最多补三次。
                if update_click_retries < _UPDATE_CLICK_RETRY_LIMIT:
                    on_log("「更新游戏」点击未生效，补点一次...")
                    _click_box(hwnd, update_box, after_sleep=3, stop_event=stop_event)
                    update_click_retries += 1
                    last_update_click = now
                elif not update_exhausted_logged:
                    update_exhausted_logged = True
                    on_log(
                        f"「更新游戏」已补点 {_UPDATE_CLICK_RETRY_LIMIT} 次仍未生效，"
                        "停止补点并继续等待（可能被遮挡或启动器异常）"
                    )
            _pause(2, stop_event)

        if _find_game_hwnd() is not None:
            on_log("已检测到终末地游戏窗口")
            return True
        raise RuntimeError(
            "等待终末地游戏窗口超时"
            + ("（游戏更新可能未完成，请人工确认启动器状态）" if update_clicked else "")
        )
    except _LaunchCancelled:
        _write_diagnostic("启动已取消")
        raise
    except Exception as error:
        _write_diagnostic(f"启动失败: {type(error).__name__}: {error}")
        # 失败留启动器/游戏原图，供排查 OCR 文本漂移
        _save_error_screenshot(launcher_path, on_error_screenshot=on_error_screenshot)
        raise
    finally:
        pyautogui.FAILSAFE = previous_failsafe


async def async_start_game_via_launcher(
    launcher_path: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    on_error_screenshot: Callable[[Path], None] | None = None,
) -> bool:
    """async 版本：在后台线程执行启动器交互，避免阻塞事件循环。"""
    stop_event = Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            start_game_via_launcher,
            launcher_path,
            on_log=on_log,
            on_error_screenshot=on_error_screenshot,
            stop_event=stop_event,
        )
    )
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        stop_event.set()
        # 线程退出前不交还桌面；再次取消也不能跳过这一步。
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            worker.result()
        except _LaunchCancelled:
            pass
        except Exception as error:
            logger.debug(f"启动器交互中止时退出: {error}")
        raise
