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
from pathlib import Path

import cv2
import numpy as np
import psutil
import pyautogui
import win32api
import win32con
import win32gui
import win32process
from PIL import Image

from app.tools.ocr import Box, OCRItem, ocr_image
from app.utils import get_logger

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

_user32 = ctypes.windll.user32
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p


@contextmanager
def _per_monitor_dpi():
    """切换到 per-monitor DPI 感知，保证窗口坐标换算在跨 DPI 显示器下正确。"""
    previous = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        if previous:
            _user32.SetThreadDpiAwarenessContext(previous)


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


def _find_game_hwnd() -> int:
    """按窗口类 + 所属进程名定位鸣潮主窗口。

    用 ``EnumWindows + psutil.Process(pid).name()`` 而非 process_iter 的 name 属性，
    规避提权进程 name 读取被拒导致的漏判；同进程存在多个窗口时取面积最大者。
    """
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
    if not candidates:
        raise RuntimeError(
            f"未找到鸣潮游戏窗口（进程 {_WUWA_PROCESS}，窗口类 {_WUWA_CLASS}）"
        )
    return max(candidates, key=_window_area)


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
    raise_if_not_found: bool = True,
) -> Box | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        box = _find_text(_read_texts(hwnd, roi), keywords)
        if box is not None:
            return box
        time.sleep(1)
    if raise_if_not_found:
        raise RuntimeError(f"等待文本超时（{timeout}s）：{keywords}")
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


def _switch_to_login(hwnd: int, on_log: Callable[[str], None]) -> None:
    """回到登录界面；已处于登录页直接返回，主菜单走登出，其余走游戏内返回。"""
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
    _wait_ocr_text(hwnd, ("终端",), timeout=30, raise_if_not_found=False)
    _click_point(
        hwnd,
        round(0.04 * _FRAME_WIDTH),
        round(0.96 * _FRAME_HEIGHT),
        after_sleep=1,
    )
    back_box = _wait_ocr_text(
        hwnd, ("返回登录",), timeout=30, raise_if_not_found=False
    )
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
        raise_if_not_found=False,
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
    """点击账号选择框直至下拉列表展开（出现多个掩码账号）。"""
    for _ in range(3):
        items = _read_texts(hwnd, _LOGIN_ROI)
        masked = [box for text, box in items if _MASKED_ACCOUNT.search(text)]
        if len(masked) >= 2:
            return
        if not masked:
            return
        _click_box(hwnd, masked[0], after_sleep=1)


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
            on_log(
                f"账号选择失败，已重试 {max_retries} 次，继续尝试登录"
            )
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
            _save_error_screenshot(_find_game_hwnd())
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
