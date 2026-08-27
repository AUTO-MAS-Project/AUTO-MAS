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
from datetime import datetime
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
# 纵向延伸到画面底部以容纳展开的下拉列表，横向保持表单宽度，避免圈入左下角版本号
_LOGIN_SCAN_ROI: Box = (480, 270, 1440, _FRAME_HEIGHT)
# 下拉框展开时每行账号都带该文案，用它正向判断下拉框开合
_DROPDOWN_MARKER = "上次登录"
# 点击后等待界面响应的冷却秒数，避免同一目标被连续点击
_ACCOUNT_CLICK_COOLDOWN = 3.0
# 提交前需要连续确认目标账号的帧数
_SUBMIT_CONFIRM_FRAMES = 2
# 展开态连续多少帧读到账号行却没有目标就判定账号不可用
_ACCOUNT_MISSING_FRAMES = 3
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


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("终末地主窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError("终末地登录仅支持 16:9 游戏分辨率")
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
    screenshot = _capture_window_image(hwnd, activate=activate).resize(
        (_FRAME_WIDTH, _FRAME_HEIGHT), Image.Resampling.LANCZOS
    )
    return cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_RGB2BGR)


def _save_error_screenshot(hwnd: int) -> Path | None:
    """保存登录失败时未经缩放或标注的游戏窗口截图。"""

    try:
        screenshot_dir = Path.cwd() / "debug/maaend-login"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / (
            f"login-error-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
        )
        _capture_window_image(hwnd, activate=False).save(screenshot_path, format="PNG")
        logger.warning(f"终末地登录错误截图已保存: {screenshot_path}")
        return screenshot_path
    except Exception as error:
        logger.warning(f"终末地登录错误截图保存失败: {error}")
        return None


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
    items = _read_text(frame, _LOGIN_SCAN_ROI)
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
            if now >= next_escape_time:
                await asyncio.to_thread(_press_escape, hwnd)
                next_escape_time = now + 5

    raise RuntimeError("打开终末地登录表单超时")


def _group_rows(items: list[OCRItem]) -> list[OCRItem]:
    """把同一行被拆成多个文本框的 OCR 结果拼回整行。

    下拉列表中的账号常被拆成 `135` `****` `9623` 三个框，逐框匹配会丢失后四位。
    按纵向重叠归行、横向排序后拼接，可恢复完整账号文本。

    Args:
        items: 单帧 OCR 结果。

    Returns:
        整行文本与其合并后的外框，按纵坐标升序排列。
    """

    rows: list[list[OCRItem]] = []
    for item in sorted(items, key=lambda item: item[1][1]):
        _, (_, top, _, height) = item
        # 容差取行高一半，缩放后的行高差异不会把相邻行并到一起
        for row in rows:
            row_top = min(box[1] for _, box in row)
            row_bottom = max(box[1] + box[3] for _, box in row)
            if top < row_bottom - height / 2 and top + height > row_top + height / 2:
                row.append(item)
                break
        else:
            rows.append([item])

    grouped: list[OCRItem] = []
    for row in rows:
        row.sort(key=lambda item: item[1][0])
        left = min(box[0] for _, box in row)
        top = min(box[1] for _, box in row)
        right = max(box[0] + box[2] for _, box in row)
        bottom = max(box[1] + box[3] for _, box in row)
        grouped.append(
            ("".join(text for text, _ in row), (left, top, right - left, bottom - top))
        )
    return grouped


def _match_account(
    rows: list[OCRItem], account_id: str, *, list_top: int | None = None
) -> Box | None:
    """按后四位匹配账号，后四位撞号时再用前三位消歧。

    界面对账号做掩码显示，只暴露前三位与后四位。后四位作为主判据；同一帧内多行
    命中同一后四位时，用前三位收窄候选，收窄后仍不唯一则无法区分，直接报错而不是
    赌一个候选。

    Args:
        rows: 单帧整行 OCR 结果，须先经 `_group_rows` 归行。
        account_id: 完整账号。
        list_top: 下拉列表顶边；传入时忽略当前账号栏等列表上方内容。

    Returns:
        命中的文本框，未命中时为 None。

    Raises:
        RuntimeError: 掩码信息不足以区分多个候选账号。
    """

    account_rows = [
        (text, box) for text, box in rows if list_top is None or box[1] >= list_top
    ]
    suffix = account_id[-4:]
    candidates = [box for text, box in account_rows if suffix in text]
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    # 前三位仅用于收窄候选，不放宽匹配：后四位未命中时不会走到这里
    prefix = account_id[:3]
    narrowed = [box for text, box in account_rows if suffix in text and prefix in text]
    if len(narrowed) == 1:
        logger.warning(f"后四位 {suffix} 命中多行，已按前三位 {prefix} 收窄")
        return narrowed[0]

    raise RuntimeError(
        f"登录列表中有 {len(candidates)} 个账号的掩码显示相同，无法区分目标账号，"
        "请改用 MAAEND 内置任务切换账号"
    )


async def _submit_login_form(hwnd: int, account_id: str) -> None:
    """在登录表单中选中目标账号并提交。

    每帧独立判断下拉框开合，不缓存上一帧的推断状态：折叠态与展开态共用同一片
    区域，缓存状态一旦与实际不符，会拿展开列表当折叠表单，把上一个账号提交上去。

    Args:
        hwnd: 终末地主窗口句柄。
        account_id: 完整账号。

    Raises:
        RuntimeError: 客户端未保存目标账号，或在超时前未能提交表单。
    """

    masked_id = f"***{account_id[-4:]}"
    # 点击后需要几帧才收起下拉框，冷却期内不重复点击
    click_deadline = 0.0
    # 折叠态连续确认目标账号的帧数，避免把展开列表误判成折叠表单就提交
    confirmed_frames = 0
    # 展开态连续识别到账号行但没有目标的帧数，用于区分漏识别与账号确实没保存
    missing_frames = 0

    async for frame in _poll_frames(hwnd, 40, activate=False):
        now = asyncio.get_running_loop().time()
        items = await asyncio.to_thread(_read_text, frame, _LOGIN_SCAN_ROI)
        # 账号匹配用归行结果，按钮定位仍用原始框，保持既有点击几何
        rows = _group_rows(items)
        logger.debug(f"登录表单识别结果: {_format_ocr_items(rows)}")
        dropdown_markers = [box for text, box in rows if _DROPDOWN_MARKER in text]
        list_top = min((box[1] for box in dropdown_markers), default=None)
        target = _match_account(rows, account_id, list_top=list_top)

        # 下拉框展开时每行账号都带“上次登录”，据此正向判断，不依赖上一帧状态
        if list_top is not None:
            confirmed_frames = 0
            if target is None:
                missing_frames += 1
                # 连续多帧都读到账号行却没有目标，继续等下去也不会出现，直接报错
                if missing_frames >= _ACCOUNT_MISSING_FRAMES:
                    raise RuntimeError(
                        f"登录列表中未找到目标账号: {masked_id}，"
                        "请确认客户端已保存该账号且显示在列表中"
                    )
                continue

            missing_frames = 0
            if now < click_deadline:
                continue
            logger.info(f"在登录下拉框中选择账号: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, target, activate=False)
            click_deadline = now + _ACCOUNT_CLICK_COOLDOWN
            continue

        missing_frames = 0
        login_button = next((box for text, box in items if text == "登录"), None)
        if target is None or login_button is None:
            confirmed_frames = 0
            recent = next((box for text, box in items if "最近" in text), None)
            if recent is None:
                continue
            logger.info(f"当前未选中目标账号，展开登录下拉框: {masked_id}")
            await asyncio.to_thread(_click_box, hwnd, recent, activate=False)
            click_deadline = now + _ACCOUNT_CLICK_COOLDOWN
            continue

        # 提交前多确认一帧：登录后界面不再显示账号，这是最后一次能校验账号身份的时机
        confirmed_frames += 1
        if confirmed_frames < _SUBMIT_CONFIRM_FRAMES:
            logger.debug(f"登录表单已选中目标账号，待确认帧数: {confirmed_frames}")
            continue

        logger.info(f"登录表单已选中目标账号: {masked_id}")
        await asyncio.to_thread(_click_box, hwnd, login_button, activate=False)
        logger.info("已点击终末地登录按钮")
        return

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
    try:
        await _open_login_form(hwnd)
        await _submit_login_form(hwnd, id)
        await _wait_template(hwnd, "logout", 120, "登录确认超时")
    except Exception:
        await asyncio.to_thread(_save_error_screenshot, hwnd)
        raise

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
