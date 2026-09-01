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

"""OK-WW（鸣潮）强制账号切换。

参照 ok-ww-old 可用的 MultiAccountDailyTask 切换逻辑重写（不依赖失效版的模板
特征匹配），交互与截图采用 MaaEnd login 已验证的前台 pyautogui + DPI 适配模式，
OCR 复用通用工具集 `app.tools.ocr`。

流程::

    找到游戏窗口 → 返回登录界面（已登录时 ESC → 终端 → 返回登录）
    → 按手机号后 4 位识别掩码账号 → 展开账号下拉选择目标 → 点击登录
    → 等待登录页消失（登录成功）
"""

import asyncio
import ctypes
import inspect
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

from app.tools.ocr import Box, OCRItem, ocr_image
from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    # pyautogui 与 pywin32 仅 Windows 可用（无图形会话导入即失败），随入口的
    # IS_WINDOWS 检查一并惰性导入，避免非 Windows 环境在未启用切号时导入崩溃
    import pyautogui
    import win32api
    import win32con
    import win32gui
    import win32process

logger = get_logger("OK-WW 账号切换")

# 诊断文件（debug/okww-account-switch/switch-detail-*.log）：记录切换过程各步骤
# OCR 文本，供用户反馈登录失败时对照定位识别漂移；切换串行独占前台，单例写入。
_DIAGNOSTIC_PATH: Path | None = None


def _write_diagnostic(text: str) -> None:
    """向诊断文件追加一行（旁路，失败时静默忽略）。"""
    if _DIAGNOSTIC_PATH is not None:
        try:
            with _DIAGNOSTIC_PATH.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass

# ── 鸣潮客户端窗口识别（与 Okww/AutoProxy 的 _WUWA_CLIENT_PROCESS 一致）──
_WUWA_CLASS = "UnrealWindow"
_WUWA_PROCESS = "Client-Win64-Shipping.exe"

# 游戏窗口就绪宽限期：进程拉起到 UnrealWindow 窗口可见通常存在启动延迟，且设备
# 性能越差窗口创建/亮相越慢。账号切换紧随脚本配置的定长 WaitTime 之后立即执行，
# 须在宽限期内轮询等待窗口就绪，否则慢设备会误报「未找到鸣潮游戏窗口」。
_GAME_WINDOW_WAIT_SECONDS = 60.0
# 窗口轮询间隔。
_WINDOW_POLL_INTERVAL = 1.0
# 启动界面稳定等待：窗口已出现但尚未进入可执行登录态（仍停在警告/加载/游戏内更新
# 过渡帧）时，在硬上限内轮询等待「登录页」或「已登录主菜单」出现。鸣潮更新由 MAS
# 启动前预更新，游戏内更新概率较低，但仍以「进展续延」应答长加载：界面仍在变化时
# 持续顺延，长时间无进展才判失败并交由返回登录流程兜底。
_IN_GAME_UPDATE_TIMEOUT = 1800.0
# 长时间无进展判定：界面静止达到该时长仍未进入登录态则视为卡死，提前交还兜底流程。
_IN_GAME_STALL_SECONDS = 60.0
# 游戏内更新/加载等待的轮询间隔（比窗口等待更宽松，降低长等待期 OCR 负载）。
_IN_GAME_POLL_INTERVAL = 3.0
# 长等待期诊断 OCR 的落盘节流：更新可能耗时数十分钟，若每个轮询都全量写诊断文件，
# 单次切换会累积数千行；改为每 N 次轮询（≈ N*3s）写一次，既能保留过渡帧采样又不膨胀。
_DIAGNOSTIC_DUMP_EVERY_POLLS = 10

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# 登录表单判定区域（相对 1080p 帧，对齐 ok-ww box_of_screen(0.3, 0.3, 0.7, 0.8)）
_LOGIN_ROI: Box = (576, 324, 1344, 864)
# 仅在登录页出现的文本，用于判定「已处于登录界面 / 登录成功」
_LOGIN_PAGE_TEXTS = ("其他登录方式",)
# 已登录主菜单判定文本（登录界面但无输入框：退出/公告/工具/账号/设置 + 登录状态）
_LOGGED_IN_MENU_TEXTS = ("登录状态", "点击连接")

# 掩码账号形如 123****5678
_MASKED_ACCOUNT = re.compile(r"\d{3}\*+\d{4}")
_MASKED_SUFFIX = re.compile(r"\d+\*+(\d{4})")

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


# ── 窗口定位 ────────────────────────────────────────────────────────────


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


def _find_game_hwnd(*, wait: bool = True) -> int:
    """按窗口类 + 所属进程名定位鸣潮主窗口。

    用 ``EnumWindows + psutil.Process(pid).name()`` 而非 process_iter 的 name 属性，
    规避提权进程 name 读取被拒导致的漏判；同进程存在多个窗口时取面积最大者。

    Args:
        wait: 为 True 时在宽限期 ``_GAME_WINDOW_WAIT_SECONDS`` 内轮询等待窗口就绪，
            以吸收进程拉起后窗口延迟亮相的启动阶段；为 False 时单次枚举立即返回。

    Raises:
        RuntimeError: 宽限期结束仍未定位到鸣潮游戏窗口。
    """
    deadline = time.monotonic() + _GAME_WINDOW_WAIT_SECONDS
    while True:
        candidates: list[int] = []

        def _enum(hwnd: int, _lparam: int) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                if win32gui.GetClassName(hwnd) != _WUWA_CLASS:
                    return True
            except Exception:
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid and _process_name(pid) == _WUWA_PROCESS:
                candidates.append(hwnd)
            return True

        win32gui.EnumWindows(_enum, 0)
        if candidates:
            return max(candidates, key=_window_area)
        if not wait or time.monotonic() >= deadline:
            break
        logger.info(
            "鸣潮游戏进程已启动但窗口暂未就绪，"
            f"{_WINDOW_POLL_INTERVAL:g} 秒后重试..."
        )
        time.sleep(_WINDOW_POLL_INTERVAL)
    raise RuntimeError(
        f"未找到鸣潮游戏窗口（进程 {_WUWA_PROCESS}，窗口类 {_WUWA_CLASS}）"
    )


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("鸣潮游戏窗口已失效")
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
            # 的输入队列，再置前，绕过系统限制（与 ok-ww ensure_in_front 同理）。
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
        logger.debug("鸣潮游戏窗口焦点请求被系统忽略，继续按前置窗口处理")
    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("鸣潮游戏窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        logger.warning(
            f"鸣潮窗口非 16:9（{width}x{height}），账号切换坐标可能偏移"
        )
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


def _dump_ocr_items(items: list[OCRItem]) -> None:
    """诊断旁路：把一次 OCR 的全部识别文本写入诊断文件（标注调用函数）。"""
    if _DIAGNOSTIC_PATH is None:
        return
    caller = ""
    frame = inspect.currentframe()
    if frame is not None and frame.f_back is not None:
        caller = frame.f_back.f_code.co_name
    _write_diagnostic(f"\n[{datetime.now():%H:%M:%S}] OCR[{caller}] {len(items)} 条:\n")
    for text, box in items:
        x, y, w, h = box
        _write_diagnostic(f"  ({x:4},{y:4} {w:3}x{h:3}) {text}\n")


def _read_texts(hwnd: int, roi: Box | None = None) -> list[OCRItem]:
    frame = _capture_window(hwnd, activate=False)
    items = ocr_image(frame, roi)
    _dump_ocr_items(items)
    return items


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


def _click_point(
    hwnd: int, px: int, py: int, *, after_sleep: float = 0.3
) -> None:
    _click_box(hwnd, (px, py, 1, 1), after_sleep=after_sleep)


def _press_escape(hwnd: int, *, after_sleep: float = 1.5) -> None:
    _activate_window(hwnd)
    pyautogui.press("esc")
    time.sleep(after_sleep)


# ── OCR 文本判定辅助 ─────────────────────────────────────────────────────


def _find_text(items: list[OCRItem], keywords: tuple[str, ...]) -> Box | None:
    for text, box in items:
        if any(keyword in text for keyword in keywords):
            return box
    return None


def _wait_ocr_text(
    hwnd: int,
    keywords: tuple[str, ...],
    *,
    roi: Box | None = None,
    timeout: int,
) -> Box | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        box = _find_text(_read_texts(hwnd, roi), keywords)
        if box is not None:
            return box
        time.sleep(1)
    return None


def _on_login_page(hwnd: int) -> bool:
    return _find_text(_read_texts(hwnd, _LOGIN_ROI), _LOGIN_PAGE_TEXTS) is not None


def _on_logged_in_menu(hwnd: int) -> bool:
    """已登录主菜单（登录界面但无输入框）：出现 登录状态/点击连接。"""
    return _find_text(_read_texts(hwnd), _LOGGED_IN_MENU_TEXTS) is not None


def _find_confirm_logout_box(items: list[OCRItem]) -> Box | None:
    """在 OCR 条目中定位弹窗中的「确认登出」按钮。

    只认「登出」，不认裸「退出」——主菜单右侧有「退出」（退出游戏）按钮，
    弹窗未打开时绝不能误点；弹窗说明文本「确认登出账号？」含问号需排除，
    按钮文本恰为「确认登出」。
    """
    candidates = [(text, box) for text, box in items if "登出" in text]
    if not candidates:
        return None
    # 精确等于按钮文本
    for text, box in candidates:
        if text == "确认登出":
            logger.info("OK-WW 登出按钮精确命中「确认登出」")
            return box
    # 排除说明文本（含问号）后取含「登出」的候选，多个命中取最右（按钮在弹窗右侧）
    filtered = [(t, b) for t, b in candidates if "？" not in t and "?" not in t]
    if filtered:
        text, box = max(filtered, key=lambda item: item[1][0] + item[1][2])
        logger.info(f"OK-WW 登出按钮命中候选文本: {text}")
        return box
    logger.info(f"登出候选均为说明文本: {[t for t, _ in candidates]}")
    return None


def _post_logout(hwnd: int, on_log: Callable[[str], None]) -> None:
    """点击确认登出后：点一下画面中央触发输入框，识别到「登录」再返回。"""
    on_log("已点击确认登出，正在等待登录输入框")
    _click_point(hwnd, _FRAME_WIDTH // 2, _FRAME_HEIGHT // 2, after_sleep=2.5)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _find_text(_read_texts(hwnd, _LOGIN_ROI), ("登录",)) is not None:
            on_log("识别到「登录」，登录输入框已弹出")
            return
        time.sleep(1)
    on_log("等待登录输入框超时（30s 未识别到「登录」）")
    raise RuntimeError("等待登录输入框超时（30s 未识别到「登录」）")


def _logout_from_menu(hwnd: int, on_log: Callable[[str], None]) -> None:
    """已登录主菜单 -> 打开账号菜单 -> 点「确认登出」-> 弹登录输入框。

    右侧竖排按钮（1080p）：退出193 公告317 工具450 账号576 设置709。
    账号按钮候选点击后，优先按 OCR「确认登出」文本定位按钮。
    """
    on_log("检测到已登录主菜单，正在登出当前账号")
    for label, y in (("账号", 576), ("账号上方", 505), ("工具", 450)):
        confirm = _find_confirm_logout_box(_read_texts(hwnd))
        if confirm is not None:
            _click_box(hwnd, confirm, after_sleep=1.5)
            _post_logout(hwnd, on_log)
            return
        on_log(f"尝试点击右侧{label}按钮区域打开账号菜单")
        _click_point(hwnd, round(0.93 * _FRAME_WIDTH), y, after_sleep=1.5)
        confirm = _find_confirm_logout_box(_read_texts(hwnd))
        if confirm is not None:
            _click_box(hwnd, confirm, after_sleep=1.5)
            _post_logout(hwnd, on_log)
            return
    raise RuntimeError("未找到「确认登出」入口，请人工确认主菜单登出按钮位置")


def _frame_signature(frame: np.ndarray) -> int:
    """对下采样的帧做哈希，用于判断界面是否仍在变化（有更新/加载进展）。"""
    small = frame[::40, ::40]
    return hash(small.tobytes())


def _wait_for_actionable_state(
    hwnd: int, on_log: Callable[[str], None]
) -> None:
    """等待进入可执行的登录态（登录页或已登录主菜单）。

    游戏窗口刚出现时可能仍停在启动过渡帧（警告弹窗、加载条、游戏内更新、自动登录等），
    此时登录页与主菜单两态都不命中。若立即按 ESC 走返回登录，可能落在不匹配的画面上。
    故采用「进展续延」语义等待两态之一出现：

    - 命中任意态 → 返回，由调用方按对应态执行（登录页→选择登录，主菜单→登出）；
    - 界面仍在变化（有更新/加载进展）→ 持续顺延，硬上限 ``_IN_GAME_UPDATE_TIMEOUT``；
    - 界面持续 ``_IN_GAME_STALL_SECONDS`` 无任何进展且仍非登录态 → 判卡死，交还调用方
      走「ESC→终端→返回登录」兜底（覆盖已直接进入游戏主场景的情形）。

    进度日志按约 5 条/轮询节流，避免向调度台频繁刷屏。
    """
    deadline = time.monotonic() + _IN_GAME_UPDATE_TIMEOUT
    last_progress = time.monotonic()
    last_sig: int | None = None
    iter_count = 0
    while time.monotonic() < deadline:
        frame = _capture_window(hwnd, activate=False)
        items_full = ocr_image(frame)
        if iter_count % _DIAGNOSTIC_DUMP_EVERY_POLLS == 0:
            _dump_ocr_items(items_full)
        if (
            _find_text(ocr_image(frame, _LOGIN_ROI), _LOGIN_PAGE_TEXTS) is not None
            or _find_text(items_full, _LOGGED_IN_MENU_TEXTS) is not None
        ):
            return
        sig = _frame_signature(frame)
        if sig != last_sig:
            last_sig = sig
            last_progress = time.monotonic()
        if time.monotonic() - last_progress >= _IN_GAME_STALL_SECONDS:
            break
        if iter_count % 5 == 0:
            on_log("鸣潮仍在启动/游戏内更新或加载过渡帧中，等待进入登录页或已登录主菜单...")
        iter_count += 1
        time.sleep(_IN_GAME_POLL_INTERVAL)
    on_log(
        "等待进入可执行登录态超时或长时间无进展"
        f"（{_IN_GAME_UPDATE_TIMEOUT:g}s），按未知状态走返回登录流程"
    )


def _switch_to_login(hwnd: int, on_log: Callable[[str], None]) -> None:
    """回到登录界面；已处于登录页直接返回，主菜单走登出，其余（含游戏主场景）走游戏内返回。"""
    _wait_for_actionable_state(hwnd, on_log)

    if _on_login_page(hwnd):
        on_log("已处于登录界面，跳过返回登录")
        return
    if _on_logged_in_menu(hwnd):
        _logout_from_menu(hwnd, on_log)
        if _on_login_page(hwnd):
            return
        on_log("登出后仍未出现登录输入框，继续走游戏内返回登录流程")

    on_log("正在返回登录界面")
    _press_escape(hwnd)
    _wait_ocr_text(hwnd, ("终端",), timeout=30)
    _click_point(
        hwnd,
        round(0.04 * _FRAME_WIDTH),
        round(0.96 * _FRAME_HEIGHT),
        after_sleep=1,
    )
    back_box = _wait_ocr_text(hwnd, ("返回登录",), timeout=30)
    if back_box is not None:
        _click_box(hwnd, back_box, after_sleep=3)
    else:
        _click_point(
            hwnd,
            round(0.67 * _FRAME_WIDTH),
            round(0.63 * _FRAME_HEIGHT),
            after_sleep=3,
        )
    _wait_ocr_text(
        hwnd,
        _LOGIN_PAGE_TEXTS,
        roi=_LOGIN_ROI,
        timeout=60,
    )
    on_log("已返回登录界面")


def _detect_current_account(hwnd: int) -> str | None:
    """从登录页 OCR 掩码账号（如 123****5678）识别当前账号后 4 位。"""
    for text, _ in _read_texts(hwnd):
        match = _MASKED_SUFFIX.search(text)
        if match:
            return match.group(1)
    return None


def _expand_account_dropdown(hwnd: int) -> None:
    """点击账号选择框直至下拉列表展开（出现多个掩码账号）。

    若始终识别不到任何掩码账号，说明无法确认账号选择器已打开（OCR 失败或
    登录界面布局变化）；继续登录可能落在错误账号上，按失败抛出而非静默返回。
    """
    found_masked = False
    for _ in range(3):
        items = _read_texts(hwnd, _LOGIN_ROI)
        masked = [box for text, box in items if _MASKED_ACCOUNT.search(text)]
        if len(masked) >= 2:
            return
        if not masked:
            # 可能为 OCR 瞬时失败，等待后重试
            time.sleep(1)
            continue
        found_masked = True
        _click_box(hwnd, masked[0], after_sleep=1)
    if not found_masked:
        raise RuntimeError(
            "未识别到任何掩码账号，无法确认账号选择器已打开，请人工检查登录界面"
        )


def _click_masked_account(hwnd: int, pattern: re.Pattern[str]) -> bool:
    items = _read_texts(hwnd)
    for text, box in items:
        if pattern.search(text):
            _click_box(hwnd, box, after_sleep=1)
            return True
    return False


def _wait_login_success(hwnd: int, *, timeout: int = 180) -> None:
    """点击登录后等待登录页消失（登录成功进入加载/主界面）。"""
    deadline = time.monotonic() + timeout
    absent_count = 0
    while time.monotonic() < deadline:
        if not _on_login_page(hwnd):
            absent_count += 1
            if absent_count >= 2:
                return
        else:
            absent_count = 0
        time.sleep(1)
    raise RuntimeError("等待登录完成超时（登录页未消失）")


def _select_and_login(
    hwnd: int, suffix: str, on_log: Callable[[str], None]
) -> None:
    pattern = re.compile(rf"\d+\*+{re.escape(suffix)}")
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        _activate_window(hwnd)
        time.sleep(1)
        _expand_account_dropdown(hwnd)
        time.sleep(0.5)
        if _click_masked_account(hwnd, pattern):
            time.sleep(1)
            detected = _detect_current_account(hwnd)
            on_log(
                f"已选择账号 ****{suffix}，当前显示 "
                f"****{detected if detected else '未知'}"
            )
            if detected == suffix:
                break
        if attempt < max_retries:
            on_log(f"账号显示不匹配，重试（{attempt}/{max_retries}）")
            time.sleep(1)
        else:
            on_log(f"账号选择失败，已重试 {max_retries} 次")
            raise RuntimeError(f"账号选择失败，已重试 {max_retries} 次")
    time.sleep(4)
    items = _read_texts(hwnd, _LOGIN_ROI)
    login_box = _find_text(items, ("登录",))
    if login_box is not None:
        _click_box(hwnd, login_box, after_sleep=3)
    else:
        _click_point(
            hwnd,
            _FRAME_WIDTH // 2,
            _FRAME_HEIGHT // 2 + 95,
            after_sleep=3,
        )
    _wait_login_success(hwnd)
    on_log(f"登录成功：****{suffix}")


def _save_error_screenshot(hwnd: int) -> None:
    """保存切换失败时的原始窗口截图，便于排查 OCR 文本漂移。"""
    try:
        screenshot_dir = Path.cwd() / "debug" / "okww-account-switch"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / (
            f"switch-error-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
        )
        _capture_window_image(hwnd, activate=False).save(
            screenshot_path, format="PNG"
        )
        logger.warning(f"账号切换错误截图已保存: {screenshot_path}")
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始切换异常
        logger.warning(f"账号切换错误截图保存失败: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def account_switch(
    account_id: str, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """强制切换鸣潮登录账号到 ``account_id``（按手机号后 4 位匹配）。

    Args:
        account_id: 目标账号（手机号），取后 4 位匹配登录页掩码账号。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        切换成功返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到游戏窗口 / 登录流程失败 / 超时。
    """
    on_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("OK-WW 账号切换仅支持 Windows 平台")
    account_id = str(account_id or "").strip()
    if len(account_id) < 4:
        raise RuntimeError("账号不足四位，无法按手机号后 4 位匹配登录账号")
    suffix = account_id[-4:]

    # 开启诊断记录：进度日志与各步骤 OCR 文本写入 debug/okww-account-switch/，
    # 供登录失败时用户反馈定位（文件随时间戳命名，一次切换一个文件）
    global _DIAGNOSTIC_PATH
    diagnostic_dir = Path.cwd() / "debug" / "okww-account-switch"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    _DIAGNOSTIC_PATH = diagnostic_dir / (
        f"switch-detail-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.log"
    )

    def _on_log(msg: str) -> None:
        _write_diagnostic(f"[{datetime.now():%H:%M:%S}] {msg}\n")
        on_log(msg)

    _on_log(f"开始切换鸣潮账号：****{suffix}")
    try:
        hwnd = _find_game_hwnd()
        _activate_window(hwnd)
        _switch_to_login(hwnd, _on_log)
        _select_and_login(hwnd, suffix, _on_log)
    except Exception:
        try:
            # wait=False：主流程已等待过窗口，此处单次枚举即可，避免失败后再空等宽限期。
            _save_error_screenshot(_find_game_hwnd(wait=False))
        except Exception:
            pass
        raise
    finally:
        _DIAGNOSTIC_PATH = None
    logger.success(f"鸣潮账号切换成功：****{suffix}")
    return True


async def async_switch_account(
    account_id: str, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """async 版本：在后台线程执行完整切换流程，避免阻塞事件循环。"""
    return await asyncio.to_thread(account_switch, account_id, on_log=on_log)
