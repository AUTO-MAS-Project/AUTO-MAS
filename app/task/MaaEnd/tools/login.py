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
import ctypes
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
import pyautogui
import win32api
import win32con
import win32gui
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from app.models.emulator import DeviceInfo
from app.utils import get_logger

logger = get_logger("终末地登录")

_TEMPLATES = {
    "logout": (
        Path.cwd() / "res/MaaFW/image/EndFieldPC/登出-1080p.png",
        (1600, 100, 1920, 400),
        0.7,
    ),
    "main_out": (
        Path.cwd() / "res/MaaFW/image/EndFieldPC/主界面退出.png",
        (0, 700, 400, 1080),
        0.6,
    ),
    "main_out_confirm": (
        Path.cwd() / "res/MaaFW/image/EndFieldPC/主界面退出确认.png",
        (900, 500, 1500, 900),
        0.7,
    ),
    "logout_confirm": (
        Path.cwd() / "res/MaaFW/image/EndFieldPC/登出确认.png",
        (900, 450, 1500, 850),
        0.7,
    ),
}

Box = tuple[int, int, int, int]
OCRItem = tuple[str, Box]
# 多显示器适配
_user32 = ctypes.windll.user32
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p


@contextmanager
def _per_monitor_dpi():
    previous = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        if previous:
            _user32.SetThreadDpiAwarenessContext(previous)


@lru_cache(maxsize=1)
def _ocr_engine() -> RapidOCR:
    return RapidOCR()


@lru_cache(maxsize=None)
def _load_template(path: Path) -> np.ndarray:
    image_bytes = np.fromfile(path, dtype=np.uint8)
    template = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    return template


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("终末地主窗口已失效")

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.15)
    if not win32gui.IsWindowVisible(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        time.sleep(0.15)

    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:
        logger.debug("终末地主窗口焦点请求被系统忽略，继续按前置窗口处理")

    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地主窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError("终末地登录仅支持 16:9 游戏分辨率")
    return width, height


def _capture_window(hwnd: int) -> np.ndarray:
    with _per_monitor_dpi():
        _activate_window(hwnd)
        width, height = _client_size(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        virtual_left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        virtual_top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        screenshot = pyautogui.screenshot(allScreens=True).crop(
            (
                left - virtual_left,
                top - virtual_top,
                left - virtual_left + width,
                top - virtual_top + height,
            )
        )

    screenshot = screenshot.resize(
        (1920, 1080), Image.Resampling.LANCZOS
    )
    return cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_RGB2BGR)


def _find_template(frame: np.ndarray, name: str) -> Box | None:
    path, roi, threshold = _TEMPLATES[name]
    left, top, right, bottom = roi
    search = frame[top:bottom, left:right]
    template = _load_template(path)
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


def _click_box(hwnd: int, box: Box) -> None:
    with _per_monitor_dpi():
        _activate_window(hwnd)
        width, height = _client_size(hwnd)
        x, y, box_width, box_height = box
        client_x = round((x + box_width / 2) * width / 1920)
        client_y = round((y + box_height / 2) * height / 1080)
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


def _login_form_exists() -> bool:
    return win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Form") != 0


async def _wait_template(
    hwnd: int, name: str, timeout: int, *, click: bool = False
) -> Box:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        frame = await asyncio.to_thread(_capture_window, hwnd)
        match = _find_template(frame, name)
        if match is not None:
            if click:
                await asyncio.to_thread(_click_box, hwnd, match)
            return match
        await asyncio.sleep(1)
    raise RuntimeError(f"等待登录界面元素超时: {name}")


async def _open_login_form(hwnd: int) -> None:
    """Return the game to its login form from any supported screen."""

    logger.info("正在打开终末地登录表单")
    deadline = asyncio.get_running_loop().time() + 120
    next_escape_time = 0.0
    while asyncio.get_running_loop().time() < deadline:
        if _login_form_exists():
            logger.info("终末地登录表单已打开")
            return

        frame = await asyncio.to_thread(_capture_window, hwnd)
        logout = _find_template(frame, "logout")
        if logout is not None:
            logger.info("正在登出当前终末地账号")
            await asyncio.to_thread(_click_box, hwnd, logout)
            await _wait_template(
                hwnd,
                "logout_confirm",
                10,
                click=True,
            )
        elif (main_out := _find_template(frame, "main_out")) is not None:
            logger.info("已识别主界面退出按钮")
            await asyncio.to_thread(_click_box, hwnd, main_out)
            await _wait_template(
                hwnd,
                "main_out_confirm",
                10,
                click=True,
            )
        else:
            now = asyncio.get_running_loop().time()
            if now >= next_escape_time:
                await asyncio.to_thread(_press_escape, hwnd)
                next_escape_time = now + 5

        await asyncio.sleep(1)

    raise RuntimeError("打开终末地登录表单超时")


async def _submit_login_form(hwnd: int, account_id: str) -> None:
    """Select a saved account when needed, then submit the login form."""

    deadline = asyncio.get_running_loop().time() + 30
    selector_expanded = False
    masked_id = f"***{account_id[-4:]}"

    while asyncio.get_running_loop().time() < deadline:
        frame = await asyncio.to_thread(_capture_window, hwnd)
        ocr_items = await asyncio.to_thread(
            _read_text, frame, (480, 270, 1440, 810)
        )
        target_accounts = [
            box for text, box in ocr_items if account_id[-4:] in text
        ]
        login_buttons = [box for text, box in ocr_items if text == "登录"]

        if selector_expanded:
            if target_accounts:
                logger.info(f"在登录下拉框中选择账号: {masked_id}")
                await asyncio.to_thread(_click_box, hwnd, target_accounts[0])
                selector_expanded = False
                await asyncio.sleep(1)
                continue
        elif target_accounts:
            if login_buttons:
                logger.info(f"登录表单已选中目标账号: {masked_id}")
                await asyncio.to_thread(_click_box, hwnd, login_buttons[0])
                logger.info("已点击终末地登录按钮")
                return

        if not selector_expanded:
            logger.info(f"当前未选中目标账号，展开登录下拉框: {masked_id}")
            await asyncio.to_thread(
                _click_box,
                hwnd,
                (900, 430, 520, 100),
            )
            selector_expanded = True

        await asyncio.sleep(1)

    raise RuntimeError(f"登录表单中未找到目标账号: {masked_id}")


async def login(id: str, emulator_info: DeviceInfo | None = None) -> bool:
    """切换到终末地客户端已保存的最近账号。

    Args:
        id: 账号标识，使用后四位匹配最近账号。
        emulator_info: 模拟器设备信息，当前仅支持 PC 端。

    Returns:
        bool: 登录成功时返回 True。

    Raises:
        RuntimeError: 窗口、识别、点击或登录确认失败。
    """
    if emulator_info is not None:
        raise RuntimeError("终末地模拟器登录暂未实现")
    if len(id) < 4:
        raise RuntimeError("终末地账号不足四位，无法匹配最近账号")

    hwnd = win32gui.FindWindow("UnityWndClass", "Endfield")
    if hwnd == 0:
        raise RuntimeError("未找到终末地主窗口")

    masked_id = f"***{id[-4:]}"
    logger.info(f"开始切换终末地账号: {masked_id}")
    try:
        await _open_login_form(hwnd)
        await _submit_login_form(hwnd, id)
        await _wait_template(hwnd, "logout", 120)
    except asyncio.CancelledError:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"终末地登录流程异常: {e}") from e

    logger.success(f"终末地账号切换成功: {masked_id}")
    return True
