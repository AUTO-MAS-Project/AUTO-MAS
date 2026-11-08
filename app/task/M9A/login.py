#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""B 服（哔哩哔哩渠服）登录：MAS 原生实现，登录完成后交给 M9A 的启动任务进游戏。

入口是 ``MaaFWFlavor`` 的可选钩子 ``ensure_logged_in``（契约见
``app/task/MaaFW/tools/embedded/flavor.py`` 模块说明）：MAS 启动模拟器（连带拉起游戏）之后、
第一个任务下发之前调用，只在 M9A 脚本、ADB controller 且 ``Run.LoginMode == "Mas"`` 时真正做事，
其余情况直接返回空串（引擎不写日志）。

流程取自实机验证过的 B 服登录界面（16:9，坐标按屏幕宽高取比例，所以分辨率无关）：

1. 等 B 服客户端到前台，没在前台就按包名拉起（``cmd package resolve-activity`` 拿启动组件，
   拿不到就用哔哩哔哩 SDK 的启动页 Activity）；
2. 循环截图 + OCR：

   - 「隐私政策提示」弹层：找到唯一的「同意」按钮（中心点限定在屏幕中下部）就点它；
   - 「登录记录」面板：收起态先点右侧箭头展开列表，再按登录记录里显示的完整昵称精确匹配
     （中心点限定在列表区域），唯一命中后点击，复核「登录」按钮与仍可见的昵称，最后点「登录」；
   - 已登录停在标题页（OCR 到「START」）：MAS 无法知道当前登录的是哪个账号，为了保证切到目标
     账号，点标题页右下角退出图标 → 唯一的「确认」→ 等「登录记录」面板出现后按上一条选号；
3. 登录后等哔哩哔哩面板消失（游戏回到标题页），把这之后的进游戏与任务执行交给 M9A 的
   ``StartUp`` 与用户任务队列。

沿用的是哔哩哔哩 SDK 登录面板与标题页的 UI 锚点；布局改版后这里要跟着改。脚本能自己登录的
项目照旧走 ``Run.LoginMode == "Project"``，本模块只在 MAS 原生登录模式下生效。

失败一律抛 :class:`MaaFWLoginRequired`（文案直接给用户看，本轮按普通失败重试）；
用户停止（``CancelledError``）照常向上抛，不在截图 / 等帧里吞掉。
"""

from __future__ import annotations

import asyncio
import io
import re
import subprocess
import time
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np
from PIL import Image

from app.task.MaaFW.tools.embedded.flavor import MaaFWLoginRequired
from app.utils import get_logger

logger = get_logger("M9A B 服登录")

Progress = Callable[[str], Awaitable[None]]

#: 官服包名是 ``com.shenlan.m.reverse1999``，B 服是 ``.bilibili`` 后缀的另一个客户端。
BILIBILI_PACKAGE = "com.shenlan.m.reverse1999.bilibili"
#: 哔哩哔哩 SDK 启动页 Activity；``resolve-activity`` 拿不到启动组件时兜底。
BILIBILI_START_ACTIVITY = "com.ssgame.mobile.gamesdk.frame.AppStartUpActivity"

_PRIVACY_HINT = "隐私政策"
_LOGIN_RECORD = "登录记录"
_SWITCH_OTHER = "切换其他账号"
_AGREE_RE = re.compile(r"^同意$")
_LOGIN_RE = re.compile(r"^登录$")
_CONFIRM_RE = re.compile(r"^确认$")

#: 标题页「START」按钮的 OCR 文字（偶尔只读到 TART / ERS 这类残词，放宽匹配）。
_TITLE_HINTS = ("START", "TART", "ERS")
#: 标题页右下角的退出图标位置（相对屏幕；实机 2560x1440 验证，点它弹「是否登出当前账号？」）。
_EXIT_POINT = (0.956, 0.91)

#: ``dumpsys activity activities`` 里表示 Activity 在前台的几种写法（与模拟器应用启动同一口径）。
_FOREGROUND_MARKERS = (
    "topResumedActivity=",
    "ResumedActivity:",
    "mResumedActivity:",
    "mCurrentFocus=",
)

_POLL_SECONDS = 1.0
#: 冷启动到出现登录界面 / 标题页的上限（含模拟器内应用拉起）。
_LAUNCH_TIMEOUT = 90.0
#: 整个登录流程的上限（协议、选号、登录、回标题）。
_LOGIN_TIMEOUT = 240.0
#: 既没有登录界面、也认不出标题页时，持续多久按「已登录」继续（例如游戏已在主界面）。
#: 冷启动的加载页（只有版本号）也算「认不出」，所以给足加载时间，别在半路就判成已登录。
_ALREADY_LOGGED_SECONDS = 60.0
#: 连续多少帧都认成标题页才动手登出，避免偶发误识别点到别处。
_TITLE_SETTLE_POLLS = 3
#: 点退出图标后等「确认」弹窗的上限。
_LOGOUT_DIALOG_SECONDS = 15.0
#: 确认登出后等「登录记录」面板出现的上限。
_LOGIN_PANEL_SECONDS = 20.0
#: 登录面板消失后再稳一下，把进游戏留给 M9A 的启动任务。
_TITLE_SETTLE_SECONDS = 3.0

#: 隐私提示「同意」按钮中心点范围（相对屏幕宽高，取自实机 16:9 面板）。
_AGREE_X_RANGE = (0.48, 0.68)
_AGREE_Y_RANGE = (0.60, 0.85)
#: 登录记录里账号昵称中心点范围（列表区域）。
_ACCOUNT_X_RANGE = (0.40, 0.57)
_ACCOUNT_Y_RANGE = (0.37, 0.70)
#: 收起态「切换其他账号」行右侧展开箭头的位置（相对屏幕）。
_EXPAND_POINT = (0.608, 0.43)

Box = tuple[int, int, int, int]


def _mask(text: str) -> str:
    """日志里的账号只留首字符，别把昵称整串写进运行日志。"""

    value = str(text or "")
    if len(value) <= 1:
        return value
    return f"{value[0]}{'*' * (len(value) - 1)}"


def _center(box: Box) -> tuple[float, float]:
    x, y, width, height = box
    return x + width / 2, y + height / 2


def _pick(
    items: list[tuple[str, Box]],
    predicate: Callable[[str], bool],
    frame: np.ndarray,
    *,
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
) -> list[Box]:
    """按文本与中心点范围筛识别框；``frame`` 只用来取屏幕宽高。"""

    height, width = frame.shape[:2]
    picked: list[Box] = []
    for text, box in items:
        if not predicate(text):
            continue
        center_x, center_y = _center(box)
        if x_range is not None and not (
            x_range[0] * width <= center_x <= x_range[1] * width
        ):
            continue
        if y_range is not None and not (
            y_range[0] * height <= center_y <= y_range[1] * height
        ):
            continue
        picked.append(box)
    return picked


def _has(items: list[tuple[str, Box]], *texts: str) -> bool:
    wanted = set(texts)
    return any(text in wanted for text, _ in items)


def _privacy_prompt(items: list[tuple[str, Box]]) -> bool:
    """隐私政策提示弹层：标题 OCR 常连成一整串（如「bilibili游戏隐私政策提示」），用包含匹配。"""

    return any(_PRIVACY_HINT in text for text, _ in items)


def _title_like(items: list[tuple[str, Box]]) -> bool:
    """标题页的样子：OCR 读到「START」这类按钮文字（登录面板与主界面都读不到）。"""

    return any(any(hint in text.upper() for hint in _TITLE_HINTS) for text, _ in items)


class _Device:
    """一台 ADB 设备上的截图 / 点击 / 前台判断，全部走 ``adb`` 命令（不依赖 MaaFramework）。"""

    def __init__(self, adb_path: str | None, address: str) -> None:
        self.program = str(adb_path or "adb")
        self.address = address

    def _run(
        self, *args: str, timeout: float = 20.0
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [self.program, "-s", self.address, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def screencap(self) -> np.ndarray:
        # exec-out 是二进制安全通道（与 shell 不同，不会把 \n 转成 \r\n），原样交给 PIL
        result = self._run("exec-out", "screencap", "-p", timeout=20.0)
        data = result.stdout
        if result.returncode != 0 or not data:
            detail = result.stderr.decode("utf-8", "ignore").strip()
            suffix = f"（{detail}）" if detail else ""
            raise MaaFWLoginRequired(f"B 服登录失败：ADB 截图失败{suffix}")
        with Image.open(io.BytesIO(data)) as image:
            return np.asarray(image.convert("RGB"))

    def tap(self, box: Box) -> None:
        center_x, center_y = _center(box)
        self.tap_point(center_x, center_y)

    def tap_point(self, x: float, y: float) -> None:
        self._run("shell", "input", "tap", str(int(x)), str(int(y)), timeout=15.0)

    def foreground(self, package: str) -> bool:
        result = self._run("shell", "dumpsys", "activity", "activities", timeout=20.0)
        text = result.stdout.decode("utf-8", "ignore")
        prefix = f"{package}/"
        return any(
            prefix in line and any(marker in line for marker in _FOREGROUND_MARKERS)
            for line in (text or "").splitlines()
        )

    def start(self, package: str) -> None:
        """按包名拉起客户端；启动组件按 ``resolve-activity`` 取，取不到用 SDK 启动页兜底。"""

        component = ""
        result = self._run(
            "shell", "cmd", "package", "resolve-activity", "--brief", package
        )
        for line in reversed(result.stdout.decode("utf-8", "ignore").splitlines()):
            stripped = line.strip()
            if stripped.startswith(f"{package}/"):
                component = stripped
                break
        if not component:
            component = f"{package}/{BILIBILI_START_ACTIVITY}"
        self._run("shell", "am", "start", "-n", component, timeout=30.0)


async def _ocr(device: _Device) -> tuple[np.ndarray, list[tuple[str, Box]]]:
    """截图并 OCR；OCR 引擎与图像解码都放到线程里，别卡事件循环。"""

    from app.tools.common.ocr import ocr_image

    frame = await asyncio.to_thread(device.screencap)
    items = await asyncio.to_thread(ocr_image, frame)
    return frame, items


async def _progress(progress: Progress | None, text: str) -> None:
    if progress is not None:
        await progress(text)


async def _agree_privacy(
    device: _Device,
    frame: np.ndarray,
    items: list[tuple[str, Box]],
    *,
    progress: Progress | None,
) -> tuple[np.ndarray, list[tuple[str, Box]]]:
    """点掉隐私政策提示里的「同意」；返回点击后的新一帧。识别不明确时响亮失败。"""

    buttons = _pick(
        items,
        lambda text: bool(_AGREE_RE.match(text)),
        frame,
        x_range=_AGREE_X_RANGE,
        y_range=_AGREE_Y_RANGE,
    )
    if len(buttons) != 1:
        raise MaaFWLoginRequired("B 服登录失败：隐私政策提示中未找到唯一的「同意」按钮")
    await asyncio.to_thread(device.tap, buttons[0])
    await _progress(progress, "已同意 B 服隐私政策提示")
    logger.info("已同意 B 服隐私政策提示")
    await asyncio.sleep(1.0)
    return await _ocr(device)


async def _wait_foreground(
    device: _Device,
    package: str,
    *,
    progress: Progress | None,
) -> None:
    """等游戏到前台；没在前台就拉起一次，等满 ``_LAUNCH_TIMEOUT`` 还没到就失败。"""

    await _progress(progress, "正在等待 B 服客户端进入前台")
    deadline = time.monotonic() + _LAUNCH_TIMEOUT
    started = False
    while True:
        if await asyncio.to_thread(device.foreground, package):
            return
        if not started:
            started = True
            logger.info(f"B 服客户端未在前台，正在拉起: {package}")
            await asyncio.to_thread(device.start, package)
        if time.monotonic() > deadline:
            raise MaaFWLoginRequired(
                f"B 服登录失败：等待游戏进入前台超时（{package}，请确认包名与模拟器内的客户端一致）"
            )
        await asyncio.sleep(_POLL_SECONDS)


async def _select_account(
    device: _Device,
    frame: np.ndarray,
    items: list[tuple[str, Box]],
    account: str,
    *,
    progress: Progress | None,
) -> None:
    """在「登录记录」面板里选中已保存的账号并点「登录」；返回时面板正在关闭。"""

    masked = _mask(account)
    await _progress(progress, f"检测到 B 服登录记录，正在选择账号「{masked}」")

    if _privacy_prompt(items):
        frame, items = await _agree_privacy(device, frame, items, progress=progress)

    # 收起态只有「切换其他账号」这一行；点右侧箭头展开登录记录列表。展开态右侧是删除按钮，
    # 所以只在看见这行文字时才点，避免误触。
    if _has(items, _SWITCH_OTHER):
        height, width = frame.shape[:2]
        await asyncio.to_thread(
            device.tap_point, width * _EXPAND_POINT[0], height * _EXPAND_POINT[1]
        )
        await asyncio.sleep(1.0)
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            frame, items = await _agree_privacy(device, frame, items, progress=progress)

    matches = _pick(
        items,
        lambda text: text == account,
        frame,
        x_range=_ACCOUNT_X_RANGE,
        y_range=_ACCOUNT_Y_RANGE,
    )
    if len(matches) != 1:
        found = len(matches)
        reason = (
            "当前页有多个同名账号，无法确定切换哪一个"
            if found > 1
            else "当前页未找到该昵称（账号需已保存过登录记录，且列表在可见范围内）"
        )
        raise MaaFWLoginRequired(
            f"B 服登录失败：登录记录里未找到唯一的账号「{masked}」——{reason}"
        )
    await asyncio.to_thread(device.tap, matches[0])
    await asyncio.sleep(1.0)

    frame, items = await _ocr(device)
    if _privacy_prompt(items):
        frame, items = await _agree_privacy(device, frame, items, progress=progress)

    selected = _pick(
        items,
        lambda text: text == account,
        frame,
        x_range=_ACCOUNT_X_RANGE,
        y_range=_ACCOUNT_Y_RANGE,
    )
    login_buttons = _pick(items, lambda text: bool(_LOGIN_RE.match(text)), frame)
    if len(selected) != 1 or len(login_buttons) != 1 or not _has(items, _SWITCH_OTHER):
        raise MaaFWLoginRequired("B 服登录失败：无法确认所选账号，已停止登录")

    await asyncio.to_thread(device.tap, login_buttons[0])
    await _progress(progress, f"已选择账号「{masked}」并点击登录")
    logger.info(f"B 服已选择账号 {masked} 并点击登录")


async def _wait_panel_closed(
    device: _Device,
    *,
    progress: Progress | None,
) -> str:
    """登录后等哔哩哔哩面板消失（回到游戏标题页）；等不到就失败。"""

    deadline = time.monotonic() + _LOGIN_TIMEOUT
    while True:
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            await _agree_privacy(device, frame, items, progress=progress)
            continue
        if not _has(items, _LOGIN_RECORD, _SWITCH_OTHER):
            await asyncio.sleep(_TITLE_SETTLE_SECONDS)
            return "B 服登录完成，已回到游戏标题页，交给 M9A 进游戏运行"
        if time.monotonic() > deadline:
            raise MaaFWLoginRequired(
                "B 服登录失败：点击登录后未回到游戏标题页（哔哩哔哩面板仍在）"
            )
        await asyncio.sleep(_POLL_SECONDS)


async def _logout_to_login_panel(
    device: _Device,
    frame: np.ndarray,
    *,
    progress: Progress | None,
) -> None:
    """标题页已登录时切号：点退出图标 → 唯一的「确认」→ 等登录面板出现。"""

    height, width = frame.shape[:2]
    await _progress(progress, "B 服已登录：正在切换账号（先登出当前账号）")
    await asyncio.to_thread(
        device.tap_point, width * _EXIT_POINT[0], height * _EXIT_POINT[1]
    )

    deadline = time.monotonic() + _LOGOUT_DIALOG_SECONDS
    confirmed = False
    while time.monotonic() <= deadline:
        await asyncio.sleep(_POLL_SECONDS)
        frame, items = await _ocr(device)
        confirms = _pick(items, lambda text: bool(_CONFIRM_RE.match(text)), frame)
        if len(confirms) == 1:
            await asyncio.to_thread(device.tap, confirms[0])
            confirmed = True
            break
    if not confirmed:
        raise MaaFWLoginRequired(
            "B 服登录失败：标题页的登出确认按钮未出现（标题页布局可能已变）"
        )
    await _progress(progress, "已确认登出当前账号，等待登录记录面板")

    deadline = time.monotonic() + _LOGIN_PANEL_SECONDS
    while time.monotonic() <= deadline:
        await asyncio.sleep(_POLL_SECONDS)
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            await _agree_privacy(device, frame, items, progress=progress)
            continue
        if _has(items, _LOGIN_RECORD):
            return
    raise MaaFWLoginRequired("B 服登录失败：登出后没有出现登录记录面板")


async def ensure_logged_in(
    *,
    script_config: Any,
    user_config: Any,
    resource_name: str | None,
    package_name: str | None,
    adb_path: str | None,
    adb_address: str,
    progress: Progress | None,
) -> str:
    """MAS 原生登录入口（契约见 MaaFW ``flavor.py`` 的 ``ensure_logged_in``）。

    只在 ``Run.LoginMode == "Mas"`` 时做事；返回写进运行日志的一句话，没做事就是空串。
    """

    del resource_name  # 资源名只用于引擎日志，登录只看登录模式
    mode = ""
    try:
        mode = str(getattr(getattr(script_config, "Run"), "LoginMode") or "")
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按默认项目登录处理
        mode = ""
    if mode.strip() != "Mas":
        return ""

    account = str(getattr(getattr(user_config, "Info", None), "Account") or "").strip()
    if not account:
        raise MaaFWLoginRequired(
            "B 服登录失败：账号为空，请在本账号的「账号」里填写登录记录中显示的完整昵称"
        )
    package = str(package_name or "").strip() or BILIBILI_PACKAGE
    device = _Device(adb_path, adb_address)

    await _progress(
        progress, f"B 服登录：使用账号「{_mask(account)}」，客户端 {package}"
    )
    await _wait_foreground(device, package, progress=progress)

    deadline = time.monotonic() + _LOGIN_TIMEOUT
    idle_since: float | None = None
    title_polls = 0
    logout_tried = False
    while True:
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            await _agree_privacy(device, frame, items, progress=progress)
            continue
        if _has(items, _LOGIN_RECORD):
            await _select_account(device, frame, items, account, progress=progress)
            return await _wait_panel_closed(device, progress=progress)

        # 标题页 = 已登录：MAS 不知道当前是哪个号，为了保证切到目标账号，登出后重选。
        if not logout_tried and _title_like(items):
            title_polls += 1
            if title_polls >= _TITLE_SETTLE_POLLS:
                logout_tried = True
                await _logout_to_login_panel(device, frame, progress=progress)
                idle_since = None
                continue
        elif not _title_like(items):
            title_polls = 0

        # 既没有登录界面也不是标题页（例如游戏已在主界面）：等不到就按已登录继续。
        if idle_since is None:
            idle_since = time.monotonic()
        elif time.monotonic() - idle_since >= _ALREADY_LOGGED_SECONDS:
            logger.info("B 服未出现登录界面，按已登录继续")
            return "B 服未出现登录界面（游戏可能已登录），直接交给 M9A 运行"

        if time.monotonic() > deadline:
            raise MaaFWLoginRequired(
                "B 服登录失败：等待登录界面超时（游戏可能未启动或加载过慢）"
            )
        await asyncio.sleep(_POLL_SECONDS)


__all__ = [
    "BILIBILI_PACKAGE",
    "BILIBILI_START_ACTIVITY",
    "ensure_logged_in",
]
