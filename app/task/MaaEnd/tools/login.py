#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

#   Portions of the login flow are adapted from AliceJump/ok-end-field:
#   https://github.com/AliceJump/ok-end-field
#   Original project licensed under GNU AGPL-3.0.
#   Modified for AUTO-MAS on 2026-07-19.


import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from app.core import Config
from app.utils import IS_WINDOWS
from app.utils import display as _utils_display

if TYPE_CHECKING:
    import pyautogui
    import win32api
    import win32con
    import win32gui

if IS_WINDOWS:
    # pyautogui 在无图形会话(如无 DISPLAY 的 Linux)导入即失败，
    # 且下方使用它的函数均为 Windows 专属路径，随 win32 一并惰性导入
    import pyautogui
    import win32api
    import win32con
    import win32gui
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from app.models.emulator import DeviceInfo
from app.tools import error_screenshot as _tool_error_screenshot
from app.tools import ocr as _tool_ocr
from app.utils import get_logger

logger = get_logger("终末地登录")

_IMAGE_ROOT = Config.resource_path / "MaaFW" / "image" / "EndFieldPC"
_TEMPLATES = {
    "logout": (
        _IMAGE_ROOT / "登出-1080p.png",
        (1600, 100, 1920, 400),
        0.7,
    ),
    "main_out": (
        _IMAGE_ROOT / "主界面退出.png",
        (0, 700, 400, 1080),
        0.6,
    ),
    "main_out_confirm": (
        _IMAGE_ROOT / "主界面退出确认.png",
        (900, 500, 1500, 900),
        0.7,
    ),
    "logout_confirm": (
        _IMAGE_ROOT / "登出确认.png",
        (900, 450, 1500, 850),
        0.7,
    ),
}

Box = tuple[int, int, int, int]
OCRItem = tuple[str, Box]
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080
_LOGIN_FORM_ROI: Box = (480, 270, 1440, 810)
_STARTUP_TIMEOUT = 3600
_STARTUP_STALL_TIMEOUT = 1800
_DOWNLOAD_STALL_TIMEOUT = 300
_WINDOW_TIMEOUT = 120
_STARTUP_TEXTS = (
    "正在获取终末地",
    "下载速度",
    "正在编译着色器",
    "正在检查资源完整性",
)
# 只用百分比和已下载量判进度，速度、预计剩余时间变化不能掩盖卡死；数字与单位
# 间容忍空格
_PROGRESS_PATTERN = re.compile(r"\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?[MGK]B/(?=\d)")
# 进度只取状态行邻近条目（1080p 基准垂直距离），排除全屏无关数字干扰
_PROGRESS_ROW_SPAN = 150
# 登录表单等待窗口：无启动状态时超过该时长仍未见到登录表单则判未就绪
_LOGIN_FORM_TIMEOUT = 120
# 资源更新重启：确认点击最小间隔、窗口消失后等待拉起的时长与重启次数上限
_CONFIRM_RETRY_SECONDS = 15
_RESTART_DELAY_SECONDS = 15
_RESTART_LIMIT = 3
# 重启确认弹窗确认按钮的判定区下缘（1080p 基准，弹窗按钮位于表单区下半部）
_RESTART_CONFIRM_Y_MIN = 500
# 近期见过重启确认弹窗时暂停按 ESC，避免把弹窗按掉后误报登录未就绪
_RESTART_ESCAPE_HOLD_SECONDS = 30
# 单帧状态漏识别保留停滞基准，连续缺失才算状态切换
_STATE_MISSING_FRAMES = 3
# 登录诊断日志保留份数：全量 OCR 诊断会持续累积，仅保留最近若干份
_DIAGNOSTIC_KEEP_COUNT = 10


class LoginNotReadyError(RuntimeError):
    """游戏尚未进入可登录画面，重试时保留其启动进度。"""


@lru_cache(maxsize=1)
def _ocr_engine() -> RapidOCR:
    return RapidOCR()


@lru_cache(maxsize=None)
def _load_template(path: Path) -> np.ndarray | None:
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except OSError:
        return None


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("终末地主窗口已失效")

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
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:
        logger.debug("终末地主窗口焦点请求被系统忽略，继续按前置窗口处理")

    time.sleep(0.1)


def _client_size(hwnd: int, *, check_ratio: bool = True) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地主窗口尺寸异常")
    if check_ratio and abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError("终末地登录仅支持 16:9 游戏分辨率")
    return width, height


def _capture_window_image(
    hwnd: int, *, activate: bool = True, check_ratio: bool = True
) -> Image.Image:
    with _utils_display.per_monitor_dpi():
        if activate:
            _activate_window(hwnd)
        width, height = _client_size(hwnd, check_ratio=check_ratio)
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


def _save_error_screenshot(
    hwnd: int, *, on_error_screenshot: Callable[[Path], None] | None = None
) -> None:
    """保存登录失败时未标注的游戏窗口截图，由共享工具压缩落盘。"""

    try:
        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            raise RuntimeError("终末地主窗口无效或已最小化，无法保存错误截图")
        # 诊断图保留实际客户区，不受登录识别的画面比例限制。
        screenshot_path = _tool_error_screenshot.save_error_screenshot(
            _capture_window_image(hwnd, activate=False, check_ratio=False),
            "maaend-login",
            "login-error",
        )
        if screenshot_path is not None and on_error_screenshot is not None:
            on_error_screenshot(screenshot_path)
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始登录异常
        logger.warning(f"终末地登录错误截图保存失败: {error}")


def _find_template(frame: np.ndarray, name: str) -> Box | None:
    path, roi, threshold = _TEMPLATES[name]
    left, top, right, bottom = roi
    search = frame[top:bottom, left:right]
    template = _load_template(path)
    if template is None:
        return None
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return None

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    if score < threshold:
        return None

    x = left + location[0]
    y = top + location[1]
    return x, y, template.shape[1], template.shape[0]


def _read_text(frame: np.ndarray, roi: Box) -> list[OCRItem]:
    left, top, right, bottom = roi
    result, _ = _ocr_engine()(frame[top:bottom, left:right])
    items: list[OCRItem] = []
    for line in result or []:
        points, text, _ = line
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        box = (
            left + round(min(xs)),
            top + round(min(ys)),
            round(max(xs) - min(xs)),
            round(max(ys) - min(ys)),
        )
        items.append(("".join(str(text).split()), box))
    return items


def _click_box(hwnd: int, box: Box, *, activate: bool = True) -> None:
    with _utils_display.per_monitor_dpi():
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
        time.sleep(0.5)
        pyautogui.click()
        time.sleep(0.5)
    finally:
        pyautogui.moveTo(*original_position)


def _press_escape(hwnd: int) -> None:
    _activate_window(hwnd)
    pyautogui.press("esc")


def _login_form_visible(frame: np.ndarray) -> bool:
    texts = [text for text, _ in _read_text(frame, _LOGIN_FORM_ROI)]
    return "登录" in texts and any(
        "最近" in text or "其他账号登录" in text for text in texts
    )


async def _poll_frames(
    hwnd: int, timeout: int, *, activate: bool = True
) -> AsyncIterator[np.ndarray]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        yield await asyncio.to_thread(_capture_window, hwnd, activate=activate)
        await asyncio.sleep(1)


async def _wait_template(
    hwnd: int,
    name: str,
    timeout: int,
    error: str,
    *,
    click: bool = False,
) -> Box:
    async for frame in _poll_frames(hwnd, timeout):
        match = _find_template(frame, name)
        if match is not None:
            if click:
                await asyncio.to_thread(_click_box, hwnd, match)
            return match
    raise RuntimeError(error)


def _find_restart_confirm(items: list[OCRItem]) -> Box | None:
    """资源更新重启弹窗的确认按钮：整词匹配并按中心点判区，左上角点在弹窗
    边缘按钮上会漏判。"""
    left, _, right, bottom = _LOGIN_FORM_ROI
    for value, box in items:
        if value.strip() not in ("确认", "确定"):
            continue
        center_x = box[0] + box[2] / 2
        center_y = box[1] + box[3] / 2
        if left <= center_x <= right and _RESTART_CONFIRM_Y_MIN <= center_y <= bottom:
            return box
    return None


def _startup_state(items: list[OCRItem]) -> tuple[str, str, Box | None]:
    """只识别已知更新状态及其重启确认按钮，不处理无关弹窗。

    重启确认按任一特征文本进入观察态（同帧要求两个都命中会因单行漏识别
    整体不可达）；进度只取状态行邻近条目并排序归一，避免 OCR 顺序抖动让
    进度每帧都「变化」重置停滞计时。
    """
    text = "".join(value for value, _ in items)
    if "资源初始化更新完成" in text or "重启游戏" in text:
        return "重启确认", "", _find_restart_confirm(items)
    for state in _STARTUP_TEXTS:
        anchor = next((box for value, box in items if state in value), None)
        if anchor is None:
            continue
        anchor_y = anchor[1]
        progress_values = sorted(
            match
            for value, box in items
            if abs(box[1] - anchor_y) <= _PROGRESS_ROW_SPAN
            for match in _PROGRESS_PATTERN.findall(value.upper())
        )
        return state, "|".join(progress_values), None
    return "", "", None


async def _open_login_form(
    hwnd: int,
    *,
    restart_game: Callable[[], Awaitable[None]] | None = None,
    write_diagnostic: Callable[[str], None] | None = None,
) -> int:
    """把游戏带回登录表单，等待启动期更新完成后返回当前窗口句柄。

    Args:
        hwnd: 当前终末地窗口句柄，游戏尚未起窗时可为 0。
        restart_game: 资源更新确认后按原启动方式重新拉起游戏的回调。
        write_diagnostic: 启动状态诊断写入回调。

    Returns:
        登录表单可见时的当前游戏窗口句柄。

    Raises:
        LoginNotReadyError: 游戏尚未进入可登录画面，重试时保留其启动进度。
        RuntimeError: 启动进度停滞或更新重启处理异常。
    """

    logger.info("正在打开终末地登录表单")
    # 历史 MAS 登录入口的临时加固；上游账号切换覆盖该启动状态后改走上游并移除。
    loop = asyncio.get_running_loop()
    hard_deadline = loop.time() + _STARTUP_TIMEOUT
    deadline = loop.time() + _LOGIN_FORM_TIMEOUT
    missing_since: float | None = None
    last_state = ""
    last_progress = ""
    progress_time = loop.time()
    state_missing_frames = 0
    restart_pending = False
    restart_count = 0
    next_confirm_time = 0.0
    next_escape_time = 0.0
    last_restart_seen = 0.0
    last_diagnostic_time = 0.0
    while loop.time() < hard_deadline:
        await asyncio.sleep(1)
        now = loop.time()
        current = win32gui.FindWindow("UnityWndClass", "Endfield")
        if not current or not win32gui.IsWindow(current):
            if missing_since is None:
                missing_since = now
                logger.info("终末地窗口暂不可用，等待重新创建")
            if now - missing_since >= _WINDOW_TIMEOUT:
                raise LoginNotReadyError("等待终末地窗口重新出现超时")
            if (
                restart_pending
                and now - missing_since >= _RESTART_DELAY_SECONDS
                and restart_game
            ):
                restart_pending = False
                logger.info("更新确认后游戏已退出，按原启动方式重新拉起")
                await restart_game()
                # 重启后重新计时：新版拉起与新一轮更新不占上一轮的硬上限
                hard_deadline = loop.time() + _STARTUP_TIMEOUT
            continue
        if current != hwnd or missing_since is not None:
            logger.info("已重新找到终末地窗口")
            hwnd = current
            deadline = now + _LOGIN_FORM_TIMEOUT
            restart_pending = False
        missing_since = None
        try:
            frame = await asyncio.to_thread(_capture_window, hwnd)
        except (win32gui.error, RuntimeError):
            # IsWindow 与截图之间也可能发生销毁；只吞掉窗口确实失效的竞态。
            if not win32gui.IsWindow(hwnd):
                continue
            raise
        items = await asyncio.to_thread(_tool_ocr.ocr_image, frame)
        state, progress, confirm = _startup_state(items)
        progress_changed = bool(progress and progress != last_progress)
        if state or progress:
            state_missing_frames = 0
        if progress:
            if progress_changed:
                progress_time = now
                if state:
                    logger.info(f"等待终末地启动: {state} {progress}")
        elif state and (not last_state or last_progress):
            progress_time = now
        elif not state and last_state:
            # 单帧漏识别保留停滞基准，连续多帧缺失才视为状态切换，
            # 否则闪烁即可规避卡死判定
            state_missing_frames += 1
            if state_missing_frames >= _STATE_MISSING_FRAMES:
                progress_time = now
        diagnostic_items = tuple(items)
        if write_diagnostic and (
            state != last_state or progress_changed or now - last_diagnostic_time >= 15
        ):
            write_diagnostic(
                f"启动状态={state or '未识别'}, 进度={progress or '无'}\n"
                + "\n".join(
                    f"  ({x},{y} {width}x{height}) {text}"
                    for text, (x, y, width, height) in diagnostic_items
                )
                + "\n"
            )
            last_diagnostic_time = now
        last_state = state
        last_progress = progress
        if state:
            if state == "重启确认":
                last_restart_seen = now
            stall_timeout = (
                _DOWNLOAD_STALL_TIMEOUT if progress else _STARTUP_STALL_TIMEOUT
            )
            if now - progress_time >= stall_timeout:
                raise RuntimeError(f"终末地启动进度长时间未变化: {state}")
            if (
                state == "重启确认"
                and not confirm
                and now - progress_time >= _LOGIN_FORM_TIMEOUT
            ):
                raise RuntimeError("未能识别资源初始化更新弹窗的确认按钮")
            deadline = now + _LOGIN_FORM_TIMEOUT
            if state == "重启确认" and confirm and now >= next_confirm_time:
                if restart_count >= _RESTART_LIMIT:
                    raise RuntimeError("终末地更新后反复要求重启，请人工检查")
                logger.info("确认资源初始化更新完成，等待游戏重启")
                await asyncio.to_thread(_click_box, hwnd, confirm)
                restart_pending = True
                restart_count += 1
                next_confirm_time = now + _CONFIRM_RETRY_SECONDS
            continue
        if now >= deadline:
            raise LoginNotReadyError("打开终末地登录表单超时")
        if await asyncio.to_thread(_login_form_visible, frame):
            logger.info("终末地登录表单已打开")
            return hwnd

        for name, confirm, message, error in (
            ("logout", "logout_confirm", "正在登出当前终末地账号", "确认登出超时"),
            (
                "main_out",
                "main_out_confirm",
                "正在退出终末地主界面",
                "确认退出终末地主界面超时",
            ),
        ):
            if (match := _find_template(frame, name)) is None:
                continue
            logger.info(message)
            await asyncio.to_thread(_click_box, hwnd, match)
            await _wait_template(hwnd, confirm, 10, error, click=True)
            break
        else:
            now = asyncio.get_running_loop().time()
            # 最近见过重启确认弹窗时暂停 ESC：把弹窗按掉会丢更新完成确认，
            # 之后只能空等登录表单超时
            if (
                now - last_restart_seen >= _RESTART_ESCAPE_HOLD_SECONDS
                and now >= next_escape_time
            ):
                await asyncio.to_thread(_press_escape, hwnd)
                next_escape_time = now + 5

    # 超限归入 LoginNotReadyError：外层按保留游戏处理，不丢更新与下载进度
    raise LoginNotReadyError("等待终末地更新及启动超过一小时")


async def _submit_login_form(hwnd: int, account_id: str) -> None:
    """Select a saved account when needed, then submit the login form."""

    masked_id = f"***{account_id[-4:]}"
    account_list_top: int | None = None
    selector_expanded = False
    last_ocr_accounts: tuple[OCRItem, ...] | None = None

    # 仅记录当前阶段的超时信息，不参与账号选择状态判断。
    step_name = "识别登录表单中的目标账号或账号选择器"
    step_timeout = 45
    step_deadline = asyncio.get_running_loop().time() + step_timeout

    async for frame in _poll_frames(hwnd, 90, activate=False):
        if asyncio.get_running_loop().time() >= step_deadline:
            message = (
                f"终末地登录{step_name}超时（{step_timeout}秒），目标账号: {masked_id}"
            )
            logger.warning(message)
            raise RuntimeError(message)

        # 下拉框展开后，从“最近”底部扫描到屏幕底部，避免固定 ROI 截断后面的账号。
        recent: Box | None = None
        if selector_expanded and account_list_top is not None:
            ocr_items = await asyncio.to_thread(
                _read_text,
                frame,
                (0, account_list_top, _FRAME_WIDTH, _FRAME_HEIGHT),
            )
            ocr_accounts = tuple((text, box) for text, box in ocr_items if "*" in text)
            if ocr_accounts != last_ocr_accounts:
                logger.info(
                    f"登录下拉框 OCR 账号列表: {ocr_accounts or '未识别到掩码账号'}"
                )
                last_ocr_accounts = ocr_accounts
        else:
            ocr_items = await asyncio.to_thread(_read_text, frame, _LOGIN_FORM_ROI)
            recent = next((box for text, box in ocr_items if "最近" in text), None)
            if recent is not None:
                account_list_top = recent[1] + recent[3]

        target = next(
            (
                box
                for text, box in ocr_items
                if account_id[-4:] in text
                and (
                    not selector_expanded
                    or (account_list_top is not None and box[1] >= account_list_top)
                )
            ),
            None,
        )
        login_button = next((box for text, box in ocr_items if text == "登录"), None)

        if selector_expanded and target is not None:
            logger.info(f"在登录下拉框中选择账号: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, target, activate=False)
            selector_expanded = False
            step_name = "确认目标账号已在登录表单中选中"
            step_timeout = 15
            step_deadline = asyncio.get_running_loop().time() + step_timeout
            continue

        if not selector_expanded and target is not None and login_button is not None:
            logger.info(f"登录表单已选中目标账号: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, login_button, activate=False)
            logger.info("已点击终末地登录按钮")
            return

        if not selector_expanded:
            if recent is None:
                continue
            logger.info(f"当前未选中目标账号，展开登录下拉框: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, recent, activate=False)
            selector_expanded = True
            step_name = "扫描登录下拉框中的目标账号"
            step_timeout = 25
            step_deadline = asyncio.get_running_loop().time() + step_timeout

    message = (
        f"终末地登录流程超时（当前步骤：{step_name}，总预算 "
        f"90秒），目标账号: {masked_id}"
    )
    logger.warning(message)
    raise RuntimeError(message)


def _prune_diagnostic_logs(directory: Path) -> None:
    """仅保留最近 _DIAGNOSTIC_KEEP_COUNT 份登录诊断日志，文件名含时间戳可排序。"""
    stale_logs = sorted(
        directory.glob("login-detail-*.log"), key=lambda path: path.name, reverse=True
    )
    for stale in stale_logs[_DIAGNOSTIC_KEEP_COUNT:]:
        stale.unlink(missing_ok=True)


async def login(
    id: str,
    emulator_info: DeviceInfo | None = None,
    *,
    restart_game: Callable[[], Awaitable[None]] | None = None,
    on_error_screenshot: Callable[[Path], None] | None = None,
) -> bool:
    """切换到终末地客户端已保存的最近账号。

    Args:
        id: 待切换的账号 Id，按客户端最近账号列表匹配。
        emulator_info: 模拟器设备信息，终末地暂未支持模拟器登录。
        restart_game: 资源更新确认后按原启动方式重新拉起游戏的回调。
        on_error_screenshot: 将本次保存的失败截图交给任务报告。
    """
    if not IS_WINDOWS:
        raise RuntimeError("终末地账号切换仅支持 Windows 平台")
    # 光标停在主屏四角时 pyautogui 全部鼠标/键盘操作都会在真实移动前抛
    # FailSafeException 且重试无法自愈；MAS 属无人值守托管，停用四角 fail-safe
    pyautogui.FAILSAFE = False
    if emulator_info is not None:
        raise RuntimeError("终末地模拟器登录暂未实现")
    if len(id) < 4:
        raise RuntimeError("终末地账号不足四位，无法匹配最近账号")

    hwnd = win32gui.FindWindow("UnityWndClass", "Endfield")

    masked_id = f"***{id[-4:]}"
    diagnostic_dir = Path.cwd() / "debug" / "maaend-login"
    diagnostic_path = (
        diagnostic_dir / f"login-detail-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    )

    def _write_diagnostic(text: str) -> None:
        """诊断旁路失败不得覆盖登录异常；写入时遮蔽完整账号并清理旧诊断。

        OCR 原文会带出登录界面的账号列表，完整账号出现处替换为掩码；OCR
        拆碎的部分识别不在覆盖范围内，导出侧过滤仍需依赖问题包规则。
        """
        try:
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            _prune_diagnostic_logs(diagnostic_dir)
            masked_text = text.replace(id, masked_id)
            with diagnostic_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now():%H:%M:%S}] {masked_text}\n")
        except OSError as error:
            logger.warning(f"终末地登录诊断日志写入失败: {error}")

    logger.info(f"开始切换终末地账号: {masked_id}")
    try:
        hwnd = await _open_login_form(
            hwnd,
            restart_game=restart_game,
            write_diagnostic=_write_diagnostic,
        )
        await _submit_login_form(hwnd, id)
        await _wait_template(hwnd, "logout", 120, "登录确认超时：未检测到已登录界面")
    except Exception as error:
        _write_diagnostic(f"账号切换失败: {type(error).__name__}: {error}")
        hwnd = win32gui.FindWindow("UnityWndClass", "Endfield")
        await asyncio.to_thread(
            _save_error_screenshot, hwnd, on_error_screenshot=on_error_screenshot
        )
        raise

    logger.success(f"终末地账号切换成功: {masked_id}")
    return True
