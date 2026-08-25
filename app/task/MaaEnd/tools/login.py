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
from collections.abc import AsyncIterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

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

_IMAGE_ROOT = Path.cwd() / "res/MaaFW/image/EndFieldPC"
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
        else win32con.SW_SHOW if not win32gui.IsWindowVisible(hwnd) else None
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


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地主窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError("终末地登录仅支持 16:9 游戏分辨率")
    return width, height


def _capture_window(hwnd: int, *, activate: bool = True) -> np.ndarray:
    with _per_monitor_dpi():
        if activate:
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
        (_FRAME_WIDTH, _FRAME_HEIGHT), Image.Resampling.LANCZOS
    )
    return cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_RGB2BGR)


def _find_template(frame: np.ndarray, name: str) -> Box | None:
    path, roi, threshold = _TEMPLATES[name]
    left, top, right, bottom = roi
    search = frame[top:bottom, left:right]
    template = _load_template(path)
    if template is None:
        logger.warning(f"模板图片加载失败: {path}")
        return None
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return None

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    if score < threshold:
        logger.debug(f"模板 {name} 未命中: 得分 {score:.3f} < 阈值 {threshold}")
        return None
    logger.debug(f"模板 {name} 命中: 得分 {score:.3f}")

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


def _format_ocr_items(items: list[OCRItem]) -> str:
    """将 OCR 结果压缩成单行日志，便于实机排查识别问题。"""

    if not items:
        return "无识别结果"
    return " | ".join(f"{text}@{box[0]},{box[1]}" for text, box in items)


def _click_box(hwnd: int, box: Box, *, activate: bool = True) -> None:
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
        time.sleep(0.5)
        pyautogui.click()
        time.sleep(0.5)
    finally:
        pyautogui.moveTo(*original_position)


def _press_escape(hwnd: int) -> None:
    _activate_window(hwnd)
    pyautogui.press("esc")


def _login_form_visible(frame: np.ndarray) -> bool:
    items = _read_text(frame, _LOGIN_FORM_ROI)
    logger.debug(f"登录表单检测: {_format_ocr_items(items)}")
    texts = [text for text, _ in items]
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


async def _open_login_form(hwnd: int) -> None:
    """Return the game to its login form from any supported screen."""

    logger.info("正在打开终末地登录表单")
    await asyncio.to_thread(_activate_window, hwnd)
    next_escape_time = 0.0
    async for frame in _poll_frames(hwnd, 120, activate=False):
        if await asyncio.to_thread(_login_form_visible, frame):
            logger.info("终末地登录表单已打开")
            return

        for name, confirm, message, error in (
            ("logout", "logout_confirm", "正在登出当前终末地账号", "确认登出超时"),
            ("main_out", "main_out_confirm", "正在退出终末地主界面", "确认退出终末地主界面超时"),
        ):
            if (match := _find_template(frame, name)) is None:
                continue
            logger.info(message)
            await asyncio.to_thread(_click_box, hwnd, match)
            await _wait_template(hwnd, confirm, 10, error, click=True)
            break
        else:
            now = asyncio.get_running_loop().time()
            if now >= next_escape_time:
                await asyncio.to_thread(_press_escape, hwnd)
                next_escape_time = now + 5

    raise RuntimeError("打开终末地登录表单超时")


def _match_account(
    items: list[OCRItem], account_id: str, *, allow_prefix: bool = False
) -> Box | None:
    """按后四位匹配账号。

    Args:
        items: 单帧 OCR 结果。
        account_id: 完整账号。
        allow_prefix: 后四位未识别时是否回退前三位匹配。仅在多行并存的下拉列表中
            开启，此时唯一命中才可信；折叠表单只显示一个账号，回退会把号段相同的
            错误账号误判为目标。

    Returns:
        命中的文本框，未命中时为 None。
    """

    suffix = account_id[-4:]
    target = next((box for text, box in items if suffix in text), None)
    if target is not None:
        return target
    # 账号过短时前三位与后四位重叠，回退没有意义
    if not allow_prefix or len(account_id) < 7:
        return None

    # 前三位是号段，容易命中同号段的其他账号，多处命中时宁可放弃本帧
    prefix = account_id[:3]
    candidates = [box for text, box in items if prefix in text]
    if len(candidates) == 1:
        logger.warning(f"后四位未识别，回退前三位匹配账号: {prefix}***")
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            f"后四位未识别且前三位 {prefix} 命中 {len(candidates)} 处，跳过本帧"
        )
    return None


async def _submit_login_form(hwnd: int, account_id: str) -> None:
    """Select a saved account when needed, then submit the login form."""

    masked_id = f"***{account_id[-4:]}"
    # 非空表示下拉框已展开，账号列表从该纵坐标开始
    account_list_top: int | None = None
    # 已点击目标账号，等待下拉框收起后再提交
    account_clicked = False

    async for frame in _poll_frames(hwnd, 90, activate=False):
        if account_list_top is not None:
            # 展开态从“最近”底部扫描到画面底部，避免固定 ROI 截断靠后的账号
            ocr_items = await asyncio.to_thread(
                _read_text,
                frame,
                (0, account_list_top, _FRAME_WIDTH, _FRAME_HEIGHT),
            )
            logger.debug(f"下拉框识别结果: {_format_ocr_items(ocr_items)}")
            target = _match_account(ocr_items, account_id, allow_prefix=True)
            if target is None:
                # 点击后目标从列表消失即下拉框已收起，回到表单确认选中结果
                if account_clicked:
                    account_list_top = None
                continue

            logger.info(f"在登录下拉框中选择账号: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, target, activate=False)
            account_clicked = True
            continue

        ocr_items = await asyncio.to_thread(_read_text, frame, _LOGIN_FORM_ROI)
        logger.debug(f"登录表单识别结果: {_format_ocr_items(ocr_items)}")
        target = _match_account(ocr_items, account_id)
        login_button = next(
            (box for text, box in ocr_items if text == "登录"), None
        )
        if target is not None and login_button is not None:
            logger.info(f"登录表单已选中目标账号: {masked_id}")
            await asyncio.to_thread(
                _click_box, hwnd, login_button, activate=False
            )
            logger.info("已点击终末地登录按钮")
            return

        recent = next((box for text, box in ocr_items if "最近" in text), None)
        if recent is None:
            continue
        logger.info(f"当前未选中目标账号，展开登录下拉框: {masked_id}")
        await asyncio.to_thread(_click_box, hwnd, recent, activate=False)
        account_list_top = recent[1] + recent[3]
        account_clicked = False

    raise RuntimeError(f"登录表单中未找到目标账号: {masked_id}")


async def login(id: str, emulator_info: DeviceInfo | None = None) -> bool:
    """切换到终末地客户端已保存的最近账号。"""
    if emulator_info is not None:
        raise RuntimeError("终末地模拟器登录暂未实现")
    if len(id) < 4:
        raise RuntimeError("终末地账号不足四位，无法匹配最近账号")

    hwnd = win32gui.FindWindow("UnityWndClass", "Endfield")
    if hwnd == 0:
        raise RuntimeError("未找到终末地主窗口")

    masked_id = f"***{id[-4:]}"
    logger.info(f"开始切换终末地账号: {masked_id}")
    await _open_login_form(hwnd)
    await _submit_login_form(hwnd, id)
    await _wait_template(hwnd, "logout", 120, "登录确认超时")

    logger.success(f"终末地账号切换成功: {masked_id}")
    return True


def replace_account_switch_task(
    tasks: list[dict[str, Any]],
    account_id: str,
    controller_type: str,
    task_id: str,
) -> None:
    """按当前账号设置唯一的 MaaEnd 切号任务。"""

    tasks[:] = [task for task in tasks if task.get("taskName") != "AccountSwitch"]
    if not account_id:
        return

    tasks.insert(
        0,
        {
            "id": task_id,
            "taskName": "AccountSwitch",
            "enabled": True,
            "enabledByController": {controller_type: True},
            "optionValues": {
                "AccountSwitchLastFourDigits": {
                    "type": "input",
                    "values": {"LastFourDigits": account_id[-4:]},
                }
            },
        },
    )
