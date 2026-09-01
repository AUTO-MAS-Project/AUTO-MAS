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

"""OK-NTE（异环）强制账号切换。

参照 OK-WW 强制切号骨架重写（前台 pyautogui + DPI 适配 + 1080p 帧坐标空间，
OCR 复用通用工具集 `app.tools.ocr`）。异环部分界面元素没有文本可识别，
无文本元素按 1080p 帧相对坐标点击。

流程::

    标题界面点右上角退出图标位置（相对坐标，双入口）→ 已登录：确认弹窗
    点「确认」；未登录：直接打开登录面板 → HOTTA STUDIO 登录面板
    → 点账号卡片展开列表 → 按手机号后 4 位选择目标账号（超出可见范围时
    滚轮翻页）→ 点「登 录」→ 等待登录面板消失（登录成功）

退出图标位置的点击是双入口：已登录时弹出「是否退出当前账号」确认弹窗，
未登录时该点击直接打开登录面板，按点击后弹出的界面分流。
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

logger = get_logger("OK-NTE 账号切换")

# 诊断文件（debug/oknte-account-switch/switch-detail-*.log）：记录切换过程各步骤
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

# ── 异环客户端窗口识别（与 OkNte/AutoProxy 的 _NTE_CLIENT_PROCESS 一致）──
_NTE_CLIENT_PROCESS = "HTGame.exe"

# 游戏窗口就绪宽限期：进程拉起到窗口可见通常存在启动延迟，且设备性能越差窗口
# 创建/亮相越慢。账号切换紧随定长 WaitTime 之后立即执行，须在宽限期内轮询等待
# 窗口就绪，否则慢设备会误报「未找到异环游戏窗口」。
_GAME_WINDOW_WAIT_SECONDS = 60.0
# 窗口轮询间隔。
_WINDOW_POLL_INTERVAL = 1.0
# 启动界面稳定等待：窗口已出现但尚未进入可执行态（仍停在 splash/加载/游戏内更新
# 过渡帧）时，在硬上限内轮询等待「标题界面」或「登录面板」出现。异环更新频繁，点
# 「开始游戏」后游戏内更新可能耗时很长，故界面仍在变化（有进展）时持续顺延等待；
# 只有持续 ``_IN_GAME_STALL_SECONDS`` 无任何进展（界面静止且仍非标题/登录）才判失败。
_IN_GAME_UPDATE_TIMEOUT = 1800.0
# 长时间无进展判定：界面静止达到该时长仍非标题/登录面板则视为卡死，提前失败。
_IN_GAME_STALL_SECONDS = 60.0
# 游戏内更新/加载等待的轮询间隔（比窗口等待更宽松，降低长等待期 OCR 负载）。
_IN_GAME_POLL_INTERVAL = 3.0
# 长等待期诊断 OCR 的落盘节流：更新可能耗时数十分钟，若每个轮询都全量写诊断文件，
# 单次切换会累积数千行；改为每 N 次轮询（≈ N*3s）写一次，既能保留过渡帧采样又不膨胀。
_DIAGNOSTIC_DUMP_EVERY_POLLS = 10

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# 标题界面右上角退出图标（无文本可 OCR，按 2048x1152 参考截图换算 1080p 坐标）
_LOGOUT_ICON_POINT = (1865, 342)
# 账号列表滚动中心（HOTTA STUDIO 面板中部），目标账号超出可见范围时滚轮翻页
_LIST_SCROLL_POINT = (960, 600)

# 仅标题界面出现的文本（底部居中按钮），用于判定「处于标题界面」
_TITLE_TEXTS = ("进入游戏",)
# 仅登录面板出现的文本，用于判定「登录面板已打开 / 登录成功后面板消失」
_PANEL_TEXTS = ("使用其他方式登录",)

# 掩码账号形如 130*****6220
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
    """按所属进程名定位异环主窗口。

    异环窗口类未实测稳定，故只用 ``EnumWindows + psutil.Process(pid).name()``
    过滤 HTGame.exe 的可见窗口（规避提权进程 name 读取被拒导致的漏判），
    同进程存在多个窗口时取面积最大者。

    Args:
        wait: 为 True 时在宽限期 ``_GAME_WINDOW_WAIT_SECONDS`` 内轮询等待窗口就绪，
            吸收进程拉起后窗口延迟亮相的启动阶段；为 False 时单次枚举立即返回。

    Raises:
        RuntimeError: 宽限期结束仍未定位到异环游戏窗口。
    """
    deadline = time.monotonic() + _GAME_WINDOW_WAIT_SECONDS
    while True:
        candidates: list[int] = []

        def _enum(hwnd: int, _lparam: int) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
            except Exception:
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid and _process_name(pid) == _NTE_CLIENT_PROCESS:
                candidates.append(hwnd)
            return True

        win32gui.EnumWindows(_enum, 0)
        if candidates:
            return max(candidates, key=_window_area)
        if not wait or time.monotonic() >= deadline:
            break
        logger.info(
            "异环游戏进程已启动但窗口暂未就绪，"
            f"{_WINDOW_POLL_INTERVAL:g} 秒后重试..."
        )
        time.sleep(_WINDOW_POLL_INTERVAL)
    raise RuntimeError(
        f"未找到异环游戏窗口（进程 {_NTE_CLIENT_PROCESS}）"
    )


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("异环游戏窗口已失效")
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
            # 的输入队列，再置前，绕过系统限制（与 OK-WW 切号同理）。
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
        logger.debug("异环游戏窗口焦点请求被系统忽略，继续按前置窗口处理")
    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("异环游戏窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        logger.warning(
            f"异环窗口非 16:9（{width}x{height}），账号切换坐标可能偏移"
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


def _on_login_panel(hwnd: int) -> bool:
    """登录面板是否已打开（面板内独有文本「使用其他方式登录」）。"""
    return _find_text(_read_texts(hwnd), _PANEL_TEXTS) is not None


def _frame_signature(frame: np.ndarray) -> int:
    """对下采样的帧做哈希，用于判断界面是否仍在变化（有更新/加载进展）。"""
    small = frame[::40, ::40]
    return hash(small.tobytes())


def _reacquire_game_hwnd(on_log: Callable[[str], None]) -> int:
    """窗口句柄在等待期间失效（如游戏内更新触发客户端重启）时重新定位异环窗口。

    重定位成功返回新句柄；等待宽限期内仍找不到则抛出，交由调用方失败处理。
    """
    on_log("游戏窗口句柄已失效，重新定位异环游戏窗口...")
    return _find_game_hwnd(wait=True)


def _wait_for_actionable_state(
    hwnd: int, on_log: Callable[[str], None]
) -> int:
    """等待进入可执行的切号态（标题界面或登录面板），返回当前有效的游戏窗口句柄。

    游戏窗口刚出现时可能仍停在启动过渡帧（splash/加载），而异环更新频繁，点「开始
    游戏」后游戏内可能出现体积大、耗时长更新的界面（此时标题界面与登录面板都不命中）。
    若立即按标题界面退出图标分流，会落在不匹配的画面上。故采用「进展续延」语义等待：

    - 命中标题界面/登录面板 → 返回有效句柄，由调用方按对应态执行；
    - 界面仍在变化（有更新/加载进展）→ 持续顺延等待，硬上限 ``_IN_GAME_UPDATE_TIMEOUT``；
    - 界面持续 ``_IN_GAME_STALL_SECONDS`` 无任何进展且仍非标题/登录 → 判卡死提前失败。
    - 等待期间窗口句柄失效（客户端更新重启）→ 重新定位新窗口后继续等待。

    进度日志按约 5 条/轮询节流，避免向调度台频繁刷屏。
    """
    deadline = time.monotonic() + _IN_GAME_UPDATE_TIMEOUT
    last_progress = time.monotonic()
    last_sig: int | None = None
    iter_count = 0
    while time.monotonic() < deadline:
        try:
            frame = _capture_window(hwnd, activate=False)
            items = ocr_image(frame)
        except RuntimeError:
            # 窗口句柄失效：可能是游戏内更新触发客户端重启，重找新窗口继续而非中止。
            hwnd = _reacquire_game_hwnd(on_log)
            last_progress = time.monotonic()
            last_sig = None
            continue
        if iter_count % _DIAGNOSTIC_DUMP_EVERY_POLLS == 0:
            _dump_ocr_items(items)
        if (
            _find_text(items, _PANEL_TEXTS) is not None
            or _find_text(items, _TITLE_TEXTS) is not None
        ):
            return hwnd
        sig = _frame_signature(frame)
        if sig != last_sig:
            last_sig = sig
            last_progress = time.monotonic()
        if time.monotonic() - last_progress >= _IN_GAME_STALL_SECONDS:
            break
        if iter_count % 5 == 0:
            on_log("异环仍在游戏内更新/加载过渡帧中，等待进入标题界面或登录面板...")
        iter_count += 1
        time.sleep(_IN_GAME_POLL_INTERVAL)
    raise RuntimeError(
        "等待异环标题界面/登录面板超时：长时间无进展或超过硬上限"
        f"（{_IN_GAME_UPDATE_TIMEOUT:g}s），请人工确认游戏已停在标题界面"
    )


def _find_confirm_box(items: list[OCRItem]) -> Box | None:
    """在 OCR 条目中定位退出确认弹窗的「确认」按钮。

    弹窗说明文本「是否确认退出当前账号?」含「确认」子串，必须排除；
    按钮文本恰为「确认」，与左侧「取消」区分。
    """
    candidates = [(text, box) for text, box in items if "确认" in text]
    if not candidates:
        return None
    # 精确等于按钮文本
    for text, box in candidates:
        if text == "确认":
            logger.info("OK-NTE 确认按钮精确命中「确认」")
            return box
    # 排除说明文本（含问号 / 「退出」）后取含「确认」的候选，多个命中取最右
    # （确认按钮在弹窗右侧）
    filtered = [
        (t, b)
        for t, b in candidates
        if "？" not in t and "?" not in t and "退出" not in t and "取消" not in t
    ]
    if filtered:
        text, box = max(filtered, key=lambda item: item[1][0] + item[1][2])
        logger.info(f"OK-NTE 确认按钮命中候选文本: {text}")
        return box
    logger.info(f"确认候选均为说明文本: {[t for t, _ in candidates]}")
    return None


def _find_login_button(items: list[OCRItem]) -> Box | None:
    """在 OCR 条目中定位登录面板的「登 录」按钮。

    OCR 文本已去空白，按钮文本归一化后恰为「登录」；面板下方还有
    「使用其他方式登录」，须排除。
    """
    candidates = [(text, box) for text, box in items if "登录" in text]
    if not candidates:
        return None
    for text, box in candidates:
        if text == "登录":
            logger.info("OK-NTE 登录按钮精确命中「登录」")
            return box
    filtered = [(t, b) for t, b in candidates if "其他方式" not in t]
    if filtered:
        text, box = max(filtered, key=lambda item: item[1][0] + item[1][2])
        logger.info(f"OK-NTE 登录按钮命中候选文本: {text}")
        return box
    logger.info(f"登录候选均为干扰文本: {[t for t, _ in candidates]}")
    return None


def _open_account_panel(hwnd: int, on_log: Callable[[str], None]) -> None:
    """标题界面 → 点右上角退出图标位置 → 按弹出的界面分流。

    该位置点击是双入口：已登录时此点击弹出「是否退出当前账号」确认弹窗，
    点「确认」后登录面板打开；未登录时此点击直接打开登录面板。
    """
    on_log("正在点击标题界面右上角退出图标位置")
    _click_point(hwnd, *_LOGOUT_ICON_POINT, after_sleep=1.5)

    # 已登录：等待退出确认弹窗；未登录：登录面板直接打开
    confirm: Box | None = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        items = _read_texts(hwnd)
        confirm = _find_confirm_box(items)
        if confirm is not None:
            break
        if _find_text(items, _PANEL_TEXTS) is not None:
            on_log("登录面板已打开（当前未登录）")
            return
        time.sleep(1)

    if confirm is None:
        raise RuntimeError(
            "点击退出图标位置后未出现退出确认或登录面板，请人工确认当前处于标题界面"
        )
    on_log("检测到已登录，点击「确认」退出当前账号")
    _click_box(hwnd, confirm, after_sleep=2)

    if _wait_ocr_text(hwnd, _PANEL_TEXTS, timeout=30) is None:
        raise RuntimeError("退出账号后登录面板未打开（30s 未识别到登录面板）")
    on_log("登录面板已打开")


def _detect_current_account(hwnd: int) -> str | None:
    """从登录面板 OCR 掩码账号（如 130*****6220）识别当前账号后 4 位。"""
    for text, _ in _read_texts(hwnd):
        match = _MASKED_SUFFIX.search(text)
        if match:
            return match.group(1)
    return None


def _expand_account_list(hwnd: int) -> None:
    """点击当前账号卡片直至账号列表展开（出现多个掩码账号）。

    若始终识别不到任何掩码账号，说明无法确认账号列表已打开（OCR 失败或
    面板布局变化）；继续登录可能落在错误账号上，按失败抛出而非静默返回。
    """
    found_masked = False
    for _ in range(3):
        items = _read_texts(hwnd)
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
            "未识别到任何掩码账号，无法确认账号列表已打开，请人工检查登录面板"
        )


def _scroll_list(hwnd: int) -> None:
    """在账号列表区域滚轮下翻一页（目标账号不在可见范围时使用）。"""
    with _per_monitor_dpi():
        width, height = _client_size(hwnd)
        px, py = _LIST_SCROLL_POINT
        client_x = round(px * width / _FRAME_WIDTH)
        client_y = round(py * height / _FRAME_HEIGHT)
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    pyautogui.moveTo(screen_x, screen_y)
    time.sleep(0.2)
    pyautogui.scroll(-3)
    time.sleep(0.5)


def _click_masked_account(
    hwnd: int, pattern: re.Pattern[str], on_log: Callable[[str], None]
) -> bool:
    """在账号列表中点击目标掩码账号；不在可见范围时滚轮翻页（上限 5 页）。"""
    for page in range(6):
        items = _read_texts(hwnd)
        for text, box in items:
            if pattern.search(text):
                _click_box(hwnd, box, after_sleep=1)
                return True
        if page < 5:
            on_log(f"目标账号不在当前可见列表，滚轮翻页（{page + 1}/5）")
            _scroll_list(hwnd)
    return False


def _wait_login_success(hwnd: int, *, timeout: int = 120) -> None:
    """点击登录后等待登录面板消失（登录成功进入加载/游戏）。"""
    deadline = time.monotonic() + timeout
    absent_count = 0
    while time.monotonic() < deadline:
        if not _on_login_panel(hwnd):
            absent_count += 1
            if absent_count >= 2:
                return
        else:
            absent_count = 0
        time.sleep(1)
    raise RuntimeError("等待登录完成超时（登录面板未消失）")


def _select_and_login(
    hwnd: int, suffix: str, on_log: Callable[[str], None]
) -> None:
    pattern = re.compile(rf"\d+\*+{re.escape(suffix)}")
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        _activate_window(hwnd)
        time.sleep(1)
        _expand_account_list(hwnd)
        time.sleep(0.5)
        if _click_masked_account(hwnd, pattern, on_log):
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
    time.sleep(2)
    login_box = _find_login_button(_read_texts(hwnd))
    if login_box is not None:
        _click_box(hwnd, login_box, after_sleep=3)
    else:
        # OCR 失败兜底：登录按钮在面板中线、账号卡片下方约一卡处
        on_log("未识别到「登录」按钮文本，按面板相对位置兜底点击")
        _click_point(hwnd, 960, 660, after_sleep=3)
    _wait_login_success(hwnd)
    on_log(f"登录成功：****{suffix}")


def _save_error_screenshot(hwnd: int) -> None:
    """保存切换失败时的原始窗口截图，便于排查 OCR 文本漂移。"""
    try:
        screenshot_dir = Path.cwd() / "debug" / "oknte-account-switch"
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
    """强制切换异环登录账号到 ``account_id``（按手机号后 4 位匹配）。

    Args:
        account_id: 目标账号（手机号），取后 4 位匹配登录面板掩码账号。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        切换成功返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到游戏窗口 / 画面不在标题界面或登录面板 / 流程失败 / 超时。
    """
    on_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("OK-NTE 账号切换仅支持 Windows 平台")
    account_id = str(account_id or "").strip()
    if len(account_id) < 4:
        raise RuntimeError("账号不足四位，无法按手机号后 4 位匹配登录账号")
    suffix = account_id[-4:]

    # 开启诊断记录：进度日志与各步骤 OCR 文本写入 debug/oknte-account-switch/，
    # 供登录失败时用户反馈定位（文件随时间戳命名，一次切换一个文件）
    global _DIAGNOSTIC_PATH
    diagnostic_dir = Path.cwd() / "debug" / "oknte-account-switch"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    _DIAGNOSTIC_PATH = diagnostic_dir / (
        f"switch-detail-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.log"
    )

    def _on_log(msg: str) -> None:
        _write_diagnostic(f"[{datetime.now():%H:%M:%S}] {msg}\n")
        on_log(msg)

    _on_log(f"开始切换异环账号：****{suffix}")
    try:
        hwnd = _find_game_hwnd()
        _activate_window(hwnd)
        # 启动稳定化：等界面进入「标题界面」或「登录面板」之一，再按各自流程分流，
        # 避免在窗口已现但仍在加载过渡帧时立即误判失败；等待期间窗口重启会返回新句柄。
        hwnd = _wait_for_actionable_state(hwnd, _on_log)
        if _on_login_panel(hwnd):
            on_log("登录面板已打开，直接选择账号")
        else:
            _open_account_panel(hwnd, _on_log)
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
    logger.success(f"异环账号切换成功：****{suffix}")
    return True


async def async_switch_account(
    account_id: str, *, on_log: Callable[[str], None] | None = None
) -> bool:
    """async 版本：在后台线程执行完整切换流程，避免阻塞事件循环。"""
    return await asyncio.to_thread(account_switch, account_id, on_log=on_log)
