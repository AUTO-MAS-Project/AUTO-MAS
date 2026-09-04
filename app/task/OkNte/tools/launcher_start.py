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

"""OK-NTE（异环）通过启动器拉起游戏。

异环客户端直接运行 HTGame.exe 会卡界面，必须经启动器（NTELauncher 下的
NTEGame.exe / NTEGlobalGame.exe / NTETWGame.exe）启动。本模块对齐 ok-nte
上游 LauncherTask 的启动流程，交互与截图采用与账号切换一致的前台
pyautogui + DPI 适配模式，OCR 复用通用工具集 `app.tools.ocr`。

流程::

    退出屏保 → 拉起启动器 → 等启动器窗口 → OCR 找「开始游戏」/「更新」按钮
    并点击（点「更新」后只点一次，等更新完成按钮变回「开始游戏」再点）
    → 等 HTGame.exe 进程 + 可见窗口出现（游戏就绪，停在标题界面）
"""

import asyncio
import ctypes
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

logger = get_logger("OK-NTE 启动器启动")

# 游戏客户端与启动器进程名（对齐 ok-nte 上游 src/__init__.py）
_GAME_PROCESS = "HTGame.exe"
LAUNCHER_EXES = ("NTEGame.exe", "NTEGlobalGame.exe", "NTETWGame.exe")

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# 首次找到按钮的等待；点击「开始游戏」后等游戏起窗；点「更新」后等更新完成
_FIND_BUTTON_TIMEOUT = 120
_START_GAME_TIMEOUT = 300
# 更新类等待上限：异环更新频繁且包体大，慢网下 30 分钟不够；对齐 ok-ww「MAS 下载
# 不设总时限」的思路放宽到 2 小时。下载进行中时由下方下载状态检测持续动态续延，
# 该值仅为点击「更新」后尚未出现下载 UI 的兜底等待。
_UPDATE_TIMEOUT = 7200
# 启动器拉起后等其窗口创建的时限（对齐 ok-nte 上游 _wait_for_process 默认值）
_LAUNCHER_WINDOW_TIMEOUT = 120
# 启动器点「确定」自重启后，等旧进程退出再找新窗口的缓冲
_LAUNCHER_RESTART_QUIET_SECONDS = 3.0

# ── 启动器下载状态动态识别（基于 OCR，样本为真实下载界面）────────────────
# 下载进行中的判定文本：底部状态行「... 下载中 0% (x/x) 当前速度 xx MB/s」
# 与右下角「暂停下载」按钮（该按钮仅在下载进行中存在）
_DOWNLOAD_STATE_TEXTS = ("下载中", "暂停下载")
# 下载进度相关文本特征：用于构造「下载进度签名」，只看下载相关行，
# 避免首页横幅轮播等无关界面变化干扰卡死判定
_DOWNLOAD_PROGRESS_TOKENS = ("%", "MB/s", "剩余时间")
# 检测到下载态时每次顺延的等待宽限（下载 UI 持续存在就持续等，等效不设总时限）
_UPDATE_ACTIVE_GRACE_SECONDS = 600.0
# 下载进度签名持续无变化的时长上限：百分比/速度/剩余时间长时间不动视为下载卡死
_DOWNLOAD_STALL_SECONDS = 300.0


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


def _wait_launcher_hwnd(
    launcher_path: Path, *, timeout: int | None = None
) -> int | None:
    """轮询等待启动器窗口创建。

    启动器进程被拉起后窗口创建需要时间（单次查找会瞬时误判失败）；窗口
    也可能由其它区服启动器进程名承载，按候选名单兜底。
    """
    deadline = time.monotonic() + (timeout or _LAUNCHER_WINDOW_TIMEOUT)
    while True:
        hwnd = _find_process_hwnd(launcher_path.name)
        if hwnd is None:
            for exe in LAUNCHER_EXES:
                hwnd = _find_process_hwnd(exe)
                if hwnd is not None:
                    break
        if hwnd is not None or time.monotonic() >= deadline:
            return hwnd
        time.sleep(2)


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("异环启动器窗口已失效")
    show_command = (
        win32con.SW_RESTORE
        if win32gui.IsIconic(hwnd)
        else win32con.SW_SHOW if not win32gui.IsWindowVisible(hwnd) else None
    )
    if show_command is not None:
        win32gui.ShowWindow(hwnd, show_command)
        time.sleep(0.15)
    try:
        if win32gui.GetForegroundWindow() != hwnd:
            # Windows 前台锁：后台进程不能直接抢占前台。先附着当前前台窗口线程
            # 的输入队列，再置前，绕过系统限制（与 OK-NTE 切号同理）。
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
        logger.debug("异环启动器窗口焦点请求被系统忽略，继续按前置窗口处理")
    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("异环启动器窗口尺寸异常")
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


def _save_error_screenshot(launcher_hwnd: int | None) -> None:
    """保存启动失败时的原始窗口截图，便于排查 OCR 文本漂移。"""
    try:
        screenshot_dir = Path.cwd() / "debug" / "oknte-launcher-start"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / (
            f"launcher-error-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
        )
        target = launcher_hwnd if launcher_hwnd is not None else _find_game_hwnd()
        if target is None:
            return
        _capture_window_image(target, activate=False).save(
            screenshot_path, format="PNG"
        )
        logger.warning(f"启动器启动错误截图已保存: {screenshot_path}")
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始启动异常
        logger.warning(f"启动器启动错误截图保存失败: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def start_game_via_launcher(
    launcher_path: Path, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """通过启动器拉起异环游戏，直到 HTGame.exe 窗口出现（停在标题界面）。

    启动器按钮有概率是「更新」而非「开始游戏」（游戏有新版本时）：点「更新」
    后不再重复点击，等更新完成、按钮变回「开始游戏」后再点。

    启动器自身更新按弹窗分两级处理：「全新启动器现已推出」弹窗点「立即体验」
    升级；更新完成后「更新已完成，请重新启动游戏」弹窗点「确定」重启启动器，
    并重新等待启动器窗口后继续走「开始游戏」流程。另有「提示」类弹窗（如检测
    到 RTSS/微星小飞机冲突）：弹窗遮罩下「开始游戏」仍可被 OCR 看到，但点击
    会落在遮罩上被吞掉，故每轮先点「确定」/「忽略」关掉弹窗再处理按钮（对齐
    ok-nte 上游 launcher_popup_close 的防护顺序）。

    游戏下载进行中（「下载中」状态行 /「暂停下载」按钮）基于下载状态动态续延等待，
    下载多久等多久；同时以百分比/速度/剩余时间构造下载进度签名，长时间无变化
    判定下载卡死提前失败。

    Args:
        launcher_path: 启动器 exe 路径（NTELauncher 下的启动器程序）。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        游戏窗口就绪返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到启动器窗口 / 按钮点击失败 / 等待游戏窗口超时。
    """
    on_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("OK-NTE 启动器启动仅支持 Windows 平台")

    # 挂机定时任务几乎必然带屏保运行：先退出屏保，避免截图全黑导致 OCR 全盲
    dismiss_screensaver()

    try:
        hwnd = _wait_launcher_hwnd(launcher_path)
        if hwnd is None:
            raise RuntimeError(
                f"等待启动器窗口超时（{_LAUNCHER_WINDOW_TIMEOUT}s 未找到进程 "
                f"{launcher_path.name} 的窗口，若启动器弹出 UAC 请先确认）"
            )
        _activate_window(hwnd)

        start_clicks = 0
        update_clicked = False
        # 点「更新」后按钮是否已离开更新态（被进度 UI 取代过）：用于区分
        # 「更新刚点完、按钮文本尚未切换」与「更新完成、按钮真正变回」
        start_button_gone = False
        launcher_upgrade_clicked = False
        last_download_sig: int | None = None
        last_download_progress = time.monotonic()
        deadline = time.monotonic() + _FIND_BUTTON_TIMEOUT
        while time.monotonic() < deadline:
            if _find_game_hwnd() is not None:
                on_log("已检测到异环游戏窗口")
                return True

            try:
                items = _read_texts(hwnd)
            except RuntimeError:
                # 启动器点击「开始游戏」后最小化或退出，窗口失效：只等游戏起窗
                if start_clicks > 0:
                    time.sleep(2)
                    continue
                raise

            now = time.monotonic()

            # 弹窗一：全新启动器推送 → 点「立即体验」升级启动器
            upgrade_box = _find_text(items, ("立即体验",))
            if upgrade_box is not None and not launcher_upgrade_clicked:
                on_log("检测到「全新启动器现已推出」弹窗，点击「立即体验」升级启动器...")
                _click_box(hwnd, upgrade_box, after_sleep=3)
                launcher_upgrade_clicked = True
                deadline = max(deadline, now + _UPDATE_TIMEOUT)
                time.sleep(2)
                continue

            # 弹窗二：启动器更新完成 → 点「确定」重启启动器，重新等窗口
            if _find_text(items, ("更新已完成", "重新启动游戏")) is not None:
                confirm_box = _find_text(items, ("确定",))
                if confirm_box is not None:
                    on_log("启动器更新完成，点击「确定」重启启动器...")
                    _click_box(hwnd, confirm_box, after_sleep=3)
                    time.sleep(_LAUNCHER_RESTART_QUIET_SECONDS)
                    new_hwnd = _wait_launcher_hwnd(launcher_path)
                    if new_hwnd is None:
                        raise RuntimeError(
                            "启动器重启后未找到启动器窗口，请人工确认启动器状态"
                        )
                    hwnd = new_hwnd
                    _activate_window(hwnd)
                    start_clicks = 0
                    update_clicked = False
                    start_button_gone = False
                    launcher_upgrade_clicked = False
                time.sleep(2)
                continue

            # 弹窗三：启动器「提示」弹窗（如检测到 RTSS/微星小飞机冲突）。弹窗
            # 以遮罩覆盖启动器，此时「开始游戏」仍可被 OCR 看到，但点击落在遮罩
            # 上被吞掉：必须先点「确定」/「忽略」关掉弹窗，本轮不再处理开始/更新
            # 按钮（对齐 ok-nte 上游 launcher_popup_close 的防护顺序）
            if any(text.strip() == "提示" for text, _ in items):
                popup_box = _find_text(items, ("确定",)) or _find_text(
                    items, ("忽略",)
                )
                if popup_box is not None:
                    on_log("检测到启动器「提示」弹窗，点击关闭...")
                    _click_box(hwnd, popup_box, after_sleep=2)
                    # 遮罩期「开始游戏」点击会被吞掉：关掉弹窗后重置点击预算，
                    # 避免预算在遮罩期耗尽后按钮恢复也无预算可点
                    start_clicks = 0
                    time.sleep(1)
                    continue

            # 游戏下载进行中：基于下载状态动态续延等待，并以下载进度签名检测卡死
            if _find_text(items, _DOWNLOAD_STATE_TEXTS) is not None:
                deadline = max(deadline, now + _UPDATE_ACTIVE_GRACE_SECONDS)
                progress_sig = hash(
                    tuple(
                        text
                        for text, _ in items
                        if any(token in text for token in _DOWNLOAD_PROGRESS_TOKENS)
                    )
                )
                if progress_sig != last_download_sig:
                    last_download_sig = progress_sig
                    last_download_progress = now
                elif now - last_download_progress >= _DOWNLOAD_STALL_SECONDS:
                    raise RuntimeError(
                        f"启动器下载长时间无进展（{_DOWNLOAD_STALL_SECONDS:g}s 内"
                        "百分比/速度无变化，疑似卡住），请人工确认下载状态"
                    )
                time.sleep(2)
                continue

            start_box = _find_text(items, ("开始游戏",))
            update_box = None if start_box else _find_text(items, ("更新",))
            if update_clicked and start_box is None:
                start_button_gone = True
            if (
                start_box is not None
                and update_clicked
                and start_button_gone
            ):
                # 更新完成后按钮已真正变回「开始游戏」（中间被进度 UI/遮罩
                # 取代过）：重置点击预算与更新标记，允许再次点击进入游戏
                # （更新后无重启弹窗时此处是唯一再点入口）
                on_log("游戏更新完成，按钮已恢复「开始游戏」，继续启动...")
                start_clicks = 0
                update_clicked = False
                start_button_gone = False
            if start_box is not None and start_clicks < 3:
                on_log("点击启动器「开始游戏」")
                _click_box(hwnd, start_box, after_sleep=3)
                start_clicks += 1
                deadline = max(deadline, now + _START_GAME_TIMEOUT)
            elif update_box is not None and not update_clicked:
                on_log("检测到启动器「更新」按钮，正在更新游戏，等待时间将延长...")
                _click_box(hwnd, update_box, after_sleep=3)
                update_clicked = True
                deadline = max(deadline, now + _UPDATE_TIMEOUT)
            time.sleep(2)

        if _find_game_hwnd() is not None:
            on_log("已检测到异环游戏窗口")
            return True
        raise RuntimeError(
            "等待异环游戏窗口超时"
            + ("（游戏更新可能未完成，请人工确认启动器状态）" if update_clicked else "")
        )
    except Exception:
        # 失败留启动器/游戏原图，供排查 OCR 文本漂移
        try:
            _save_error_screenshot(_wait_launcher_hwnd(launcher_path, timeout=5))
        except Exception:
            pass
        raise


async def async_start_game_via_launcher(
    launcher_path: Path, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """async 版本：在后台线程执行启动器交互，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        start_game_via_launcher, launcher_path, on_log=on_log
    )
