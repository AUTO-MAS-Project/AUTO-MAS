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
from functools import lru_cache
from pathlib import Path
from typing import Pattern

import cv2
import numpy as np
import pyautogui
import win32api
import win32con
import win32gui
from PIL import Image
from pynput.keyboard import Controller, Key
from rapidocr_onnxruntime import RapidOCR

from app.models.emulator import DeviceInfo
from app.utils import get_logger

logger = get_logger("终末地登录")

_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080
_POLL_INTERVAL = 1
_READY_TIMEOUT = 120
_CONFIRM_TIMEOUT = 10
_TEXT_TIMEOUT = 30
_LOGIN_TIMEOUT = 120

_RESOURCE_ROOT = Path.cwd() / "res/MaaFW/image/EndFieldPC"
_TEMPLATES = {
    "logout": (
        _RESOURCE_ROOT / "登出-1080p.png",
        (1600, 100, 1920, 400),
        0.7,
    ),
    "main_out": (_RESOURCE_ROOT / "主界面退出.png", (0, 700, 400, 1080), 0.6),
    "main_out_confirm": (
        _RESOURCE_ROOT / "主界面退出确认.png",
        (900, 500, 1500, 900),
        0.7,
    ),
    "logout_confirm": (
        _RESOURCE_ROOT / "登出确认.png",
        (900, 450, 1500, 850),
        0.7,
    ),
}

Box = tuple[int, int, int, int]


@lru_cache(maxsize=1)
def _ocr_engine() -> RapidOCR:
    return RapidOCR()


@lru_cache(maxsize=None)
def _load_template(path: Path) -> np.ndarray:
    template = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if template is None:
        raise RuntimeError(f"登录模板不存在: {path.name}")
    return template


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("终末地主窗口已失效")
    if win32gui.GetForegroundWindow() == hwnd:
        return

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.15)
    if not win32gui.IsWindowVisible(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        time.sleep(0.15)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(hwnd)
        finally:
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(0.1)
    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError("无法将终末地主窗口切换到前台")


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地主窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError("终末地登录仅支持 16:9 游戏分辨率")
    return width, height


def _capture_window(hwnd: int) -> np.ndarray:
    _activate_window(hwnd)
    width, height = _client_size(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    screenshot = pyautogui.screenshot().crop((left, top, left + width, top + height))
    screenshot = screenshot.resize(
        (_FRAME_WIDTH, _FRAME_HEIGHT), Image.Resampling.LANCZOS
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


def _find_text(frame: np.ndarray, pattern: Pattern[str], roi: Box) -> list[Box]:
    left, top, right, bottom = roi
    result, _ = _ocr_engine()(frame[top:bottom, left:right])
    matches: list[Box] = []
    for line in result or []:
        points, text, _ = line
        if not pattern.search(re.sub(r"\s+", "", str(text))):
            continue

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x = left + round(min(xs))
        y = top + round(min(ys))
        matches.append((x, y, round(max(xs) - min(xs)), round(max(ys) - min(ys))))
    return matches


def _click_box(hwnd: int, box: Box) -> None:
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
    keyboard = Controller()
    keyboard.press(Key.esc)
    keyboard.release(Key.esc)


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
        await asyncio.sleep(_POLL_INTERVAL)
    raise RuntimeError(f"等待登录界面元素超时: {name}")


async def _wait_click_text(
    hwnd: int,
    pattern: Pattern[str],
    roi: Box,
    step: str,
    *,
    unique: bool = False,
) -> Box:
    deadline = asyncio.get_running_loop().time() + _TEXT_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        frame = await asyncio.to_thread(_capture_window, hwnd)
        matches = await asyncio.to_thread(_find_text, frame, pattern, roi)
        if unique and len(matches) > 1:
            raise RuntimeError(f"{step}失败: 匹配结果不唯一")
        if matches:
            await asyncio.to_thread(_click_box, hwnd, matches[0])
            return matches[0]
        await asyncio.sleep(_POLL_INTERVAL)
    raise RuntimeError(f"{step}超时")


async def _open_account_page(hwnd: int) -> None:
    deadline = asyncio.get_running_loop().time() + _READY_TIMEOUT
    next_escape_time = 0.0
    while asyncio.get_running_loop().time() < deadline:
        frame = await asyncio.to_thread(_capture_window, hwnd)
        if _find_template(frame, "logout") is not None:
            return

        main_out = _find_template(frame, "main_out")
        if main_out is not None:
            await asyncio.to_thread(_click_box, hwnd, main_out)
            await _wait_template(
                hwnd,
                "main_out_confirm",
                _CONFIRM_TIMEOUT,
                click=True,
            )
            continue

        now = asyncio.get_running_loop().time()
        if now >= next_escape_time:
            await asyncio.to_thread(_press_escape, hwnd)
            next_escape_time = now + 5
        await asyncio.sleep(_POLL_INTERVAL)

    raise RuntimeError("等待可登出状态超时")


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
        await _open_account_page(hwnd)
        await _wait_template(hwnd, "logout", _READY_TIMEOUT, click=True)
        await _wait_template(
            hwnd,
            "logout_confirm",
            _CONFIRM_TIMEOUT,
            click=True,
        )

        recent = await _wait_click_text(
            hwnd,
            re.compile("最近"),
            (480, 270, 1440, 810),
            "查找‘最近’按钮",
        )
        account_roi = (0, recent[1] + recent[3], _FRAME_WIDTH, _FRAME_HEIGHT)
        await _wait_click_text(
            hwnd,
            re.compile(re.escape(id[-4:])),
            account_roi,
            f"查找账号 {masked_id}",
            unique=True,
        )
        await _wait_click_text(
            hwnd,
            re.compile(r"^登录$"),
            (480, 270, 1440, 810),
            "查找‘登录’按钮",
        )
        await _wait_template(hwnd, "logout", _LOGIN_TIMEOUT)
    except asyncio.CancelledError:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"终末地登录流程异常: {e}") from e

    logger.success(f"终末地账号切换成功: {masked_id}")
    return True
