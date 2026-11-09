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
   - 已登录停在标题页（OCR 到「START」，或标题 logo 下的「REVERSE」副标题——实机常只读到 `ERSE`，
     或登录成功后顶栏的「<昵称> 欢迎回来」横幅；START 有时太淡读不到）：MAS 无法知道当前登录的是哪个
     账号，为了保证切到目标账号，点标题页右下角退出图标 → 唯一的「确认」→ 等「登录记录」面板出现后按
     上一条选号；
3. 登录后等哔哩哔哩面板消失（游戏回到标题页），把这之后的进游戏与任务执行交给 M9A 的
   ``StartUp`` 与用户任务队列。

沿用的是哔哩哔哩 SDK 登录面板与标题页的 UI 锚点；布局改版后这里要跟着改。脚本能自己登录的
项目照旧走 ``Run.LoginMode == "Project"``，本模块只在 MAS 原生登录模式下生效。

协议与"完成"的判定边界（按评审要求收紧）：

- 自动同意只复用全局 ``Config.setting.Function.IfAgreeBilibili``（默认关闭）：开关没开时
  不点「同意」，提示手动处理并停止本次登录，不新增第二份协议开关；
- 既认不出登录记录、也认不出标题页（例如游戏停在别的账号的主界面）时，**明确停止**并让用户
  把游戏放到标题页——不能把"没认出登录页"当成"目标账号已登录"，否则任务会跑在错的账号上；
  等待时长服从脚本的 `Game.WaitTime`（加载画面同样认不出，不能按固定 60 秒截断慢启动的客户端），
  总时长仍受登录主循环的 240 秒约束；
- 登录后必须连续若干帧认出标题页才算完成；过渡黑屏 / 加载 / OCR 漏字只算未知画面，继续
  有界等待，到点仍未确认就失败；
- 所有循环都先检查总时限，``adb input tap`` 失败直接抛错，不让点击失败被静默吞掉；
- 只在 `Mas` 模式、资源是「B 服」、且实际要启动的客户端是 B 服包名时干活：配错客户端要立刻
  报错，不能拿官服客户端去走哔哩哔哩登录面板。

上游评估：当前上游 M9A 的 interface 已声明 B 服资源（运行任务可用），但「切换账号」任务仍只
声明官服、也没有按 B 站昵称选号的入口，因此这里按**临时补位**处理并标注移除计划（上游提供等价
入口后删除本模块的选号逻辑）。登录、登出与选号属于上游领域，运行前调用并不改变其归属。
维护者已在 PR #1882 明确隐私协议不由 M9A 处理，且不再作为该 PR 的评审阻断：
https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/1882#issuecomment-6721059637
该决定不扩大为其他游戏内能力的通用豁免；其余补位范围仍需上游评估依据或维护者明确接受。

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
from contextlib import suppress
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.task.MaaFW.tools.embedded.flavor import MaaFWLoginRequired
from app.utils import get_logger
from app.utils.common.process.runner import create_subprocess, stop_process

logger = get_logger("M9A B 服登录")

Progress = Callable[[str], Awaitable[None]]

#: 官服包名是 ``com.shenlan.m.reverse1999``，B 服是 ``.bilibili`` 后缀的另一个客户端。
BILIBILI_PACKAGE = "com.shenlan.m.reverse1999.bilibili"
#: 上游 M9A interface 里 B 服资源的名字（实测写作「B 服」；比较时忽略空格）。
_BILIBILI_RESOURCE_NAME = "B服"
#: 哔哩哔哩 SDK 启动页 Activity；``resolve-activity`` 拿不到启动组件时兜底。
BILIBILI_START_ACTIVITY = "com.ssgame.mobile.gamesdk.frame.AppStartUpActivity"

_PRIVACY_HINT = "隐私政策"
_WELCOME_HINT = "欢迎回来"
#: 冷启动的健康警告页标题（「警告：请在游戏前阅读」），点一下继续。
_WARNING_HINT = "请在游戏前阅读"
_LOGIN_RECORD = "登录记录"
_SWITCH_OTHER = "切换其他账号"
_AGREE_RE = re.compile(r"^同意$")
_LOGIN_RE = re.compile(r"^登录$")
_CONFIRM_RE = re.compile(r"^确认$")

#: 标题页可读的 OCR 文字：「START」按钮（允许 OCR 漏掉首字母）与标题 logo 下的「REVERSE」
#: 副标题（实机常只读到 ERSE）。登录面板与主界面都读不到这两处。
_TITLE_HINTS = ("START", "TART", "REVERSE", "ERSE")
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
#: 主循环（等登录界面 / 标题页）与登录后等面板关闭各自的上限。两处**分别计时**，不是共享
#: 一个 240 秒总预算；隐私提示循环也受本时限约束。
_LOGIN_TIMEOUT = 240.0
#: 既没有登录界面、也认不出标题页时，**至少**等多久再判「无法确认当前账号」。
#: 冷启动的加载页（只有版本号）也算认不出；上限由脚本的 ``Game.WaitTime`` 抬到用户愿意
#: 为启动等的时间（见 ``_unknown_screen_budget``），不能按这个固定值截断慢启动的客户端。
_UNKNOWN_SCREEN_SECONDS = 60.0
#: 连续多少帧都认出标题页才判「已回到标题页」，避免过渡帧 / OCR 漏字误判。
_TITLE_CONFIRM_FRAMES = 2
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


def _welcome_like(items: list[tuple[str, Box]]) -> bool:
    """标题页的「<昵称> 欢迎回来」横幅。

    登录成功后标题页顶部会出现这条横幅，START 有时被它盖住或太淡 OCR 读不到；横幅本身
    是「已登录并回到标题页」的正向信号。只在标题页出现，登录面板与主界面都读不到。
    """

    return any(_WELCOME_HINT in text for text, _ in items)


def _warning_like(items: list[tuple[str, Box]]) -> bool:
    """冷启动的健康警告页（「警告：请在游戏前阅读」）：点一下继续。

    它会挡在标题页 / 登录面板前面，而 MAS 的登录钩子跑在 M9A ``StartUp`` 之前，不处理就
    会在「认不出的画面」上等到超时。
    """

    return any(_WARNING_HINT in text for text, _ in items)


def _title_like(items: list[tuple[str, Box]]) -> bool:
    """标题页的样子：OCR 读到「START」这类按钮文字（登录面板与主界面都读不到）。"""

    return any(text.strip().upper() in _TITLE_HINTS for text, _ in items)


def _is_bilibili_resource(resource_name: str | None) -> bool:
    """脚本资源是不是 B 服：上游 interface 里的名字是「B 服」（带空格），比较时忽略空格。"""

    return str(resource_name or "").replace(" ", "").strip() == _BILIBILI_RESOURCE_NAME


def _unknown_screen_budget(script_config: Any) -> float:
    """认不出画面时最多等多久：服从脚本的「游戏启动等待」（``Game.WaitTime``）。

    登录钩子跑在 worker 的启动等待之前，冷启动的加载画面在这里同样认不出；只看固定
    60 秒会把加载慢的客户端在就绪前判成「无法确认当前账号」。``Game.WaitTime`` 正是
    MAS 本来愿意为启动等的时间，取两者较大值；总时长仍不超过登录主循环的 ``_LOGIN_TIMEOUT``。
    """

    budget = _UNKNOWN_SCREEN_SECONDS
    try:
        wait = float(getattr(getattr(script_config, "Game", None), "WaitTime", 0) or 0)
    except (AttributeError, TypeError, ValueError):  # 假配置对象缺项时用固定预算
        return budget
    if wait > budget:
        budget = min(wait, _LOGIN_TIMEOUT)
    return budget


class _Device:
    """一台 ADB 设备上的截图 / 点击 / 前台判断，全部走 ``adb`` 命令（不依赖 MaaFramework）。

    子进程走 MAS 的受管进程入口：任务被停止时命令随任务作用域一起结束，不会出现
    「停止后迟到的点击 / 拉起还落在模拟器上」。
    """

    def __init__(
        self, adb_path: str | None, address: str, host_adb: Any = None
    ) -> None:
        self.program = str(adb_path or "adb")
        self.address = address
        self.host_adb = host_adb
        self._aspect_checked = False

    async def _exec(
        self, *args: str, timeout: float = 20.0
    ) -> tuple[int, bytes, bytes]:
        """跑一条 adb 命令，返回 ``(返回码, 原始 stdout, 原始 stderr)``。

        stdout 不能先解码：``exec-out screencap -p`` 是 PNG，一旦按文本解码就再也拼不回来。
        超时或任务被停止时都先结束子进程再抛出，不留下还在跑的命令。
        """

        try:
            process = await create_subprocess(
                self.program,
                "-s",
                self.address,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise MaaFWLoginRequired(
                f"B 服登录失败：找不到 ADB 可执行文件「{self.program}」；"
                "请在脚本设置里填写 ADB 路径（可执行文件名不一定是 adb.exe）"
            ) from exc
        try:
            async with asyncio.timeout(timeout):
                stdout, stderr = await process.communicate()
        except (TimeoutError, asyncio.CancelledError):
            with suppress(Exception):
                await stop_process(process, kill_tree=True)
            raise
        return (
            process.returncode if process.returncode is not None else -1,
            stdout or b"",
            stderr or b"",
        )

    async def _run(
        self, *args: str, timeout: float = 20.0
    ) -> subprocess.CompletedProcess[bytes]:
        if self.host_adb is not None:
            code, output = await self.host_adb(*args, timeout=timeout)
            data = output.encode("utf-8")
            return subprocess.CompletedProcess(args, code, data, data if code else b"")
        code, stdout, stderr = await self._exec(*args, timeout=timeout)
        return subprocess.CompletedProcess(args, code, stdout, stderr)

    async def screencap(self) -> np.ndarray:
        # exec-out 是二进制安全通道（与 shell 不同，不会把 \n 转成 \r\n），原样交给 PIL
        if self.host_adb is not None:
            data = await self.host_adb.screencap_png(timeout=20.0)
            code, stderr = 0, b""
        else:
            code, data, stderr = await self._exec(
                "exec-out", "screencap", "-p", timeout=20.0
            )
        if code != 0 or not data:
            detail = stderr.decode("utf-8", "ignore").strip()
            suffix = f"（{detail}）" if detail else ""
            raise MaaFWLoginRequired(f"B 服登录失败：ADB 截图失败{suffix}")
        with Image.open(io.BytesIO(data)) as image:
            frame = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        if not self._aspect_checked:
            self._aspect_checked = True
            height, width = frame.shape[:2]
            if abs(width / height - 16 / 9) > 0.05:
                logger.warning(
                    "B 服登录坐标按 16:9 验证，当前宽高比可能导致点击偏移，请调整模拟器分辨率"
                )
        return frame

    async def tap(self, box: Box) -> None:
        center_x, center_y = _center(box)
        await self.tap_point(center_x, center_y)

    async def tap_point(self, x: float, y: float) -> None:
        result = await self._run(
            "shell", "input", "tap", str(int(x)), str(int(y)), timeout=15.0
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "ignore").strip()
            suffix = f"（{detail}）" if detail else ""
            raise MaaFWLoginRequired(f"B 服登录失败：ADB 点击失败{suffix}")

    async def foreground(self, package: str) -> bool:
        result = await self._run(
            "shell", "dumpsys", "activity", "activities", timeout=20.0
        )
        text = result.stdout.decode("utf-8", "ignore")
        prefix = f"{package}/"
        return any(
            prefix in line and any(marker in line for marker in _FOREGROUND_MARKERS)
            for line in (text or "").splitlines()
        )

    async def start(self, package: str) -> None:
        """按包名拉起客户端；启动组件按 ``resolve-activity`` 取，取不到用 SDK 启动页兜底。"""

        component = ""
        result = await self._run(
            "shell", "cmd", "package", "resolve-activity", "--brief", package
        )
        for line in reversed(result.stdout.decode("utf-8", "ignore").splitlines()):
            stripped = line.strip()
            if stripped.startswith(f"{package}/"):
                component = stripped
                break
        if not component:
            component = f"{package}/{BILIBILI_START_ACTIVITY}"
        result = await self._run("shell", "am", "start", "-n", component, timeout=30.0)
        if result.returncode != 0:
            raise MaaFWLoginRequired("B 服登录失败：ADB 无法拉起客户端")


async def _ocr(device: _Device) -> tuple[np.ndarray, list[tuple[str, Box]]]:
    """异步截图并 OCR；OCR 引擎放到线程里，避免阻塞事件循环。"""

    from app.tools.common.ocr import ocr_image

    frame = await device.screencap()
    items = await asyncio.to_thread(ocr_image, frame)
    return frame, items


async def _progress(progress: Progress | None, text: str) -> None:
    if progress is not None:
        await progress(text)


def _if_agree_bilibili() -> bool:
    """全局「同意哔哩哔哩用户协议」开关；读不到按默认关闭处理（不自动同意）。"""

    try:
        from app.core import Config

        return bool(Config.setting.Function.IfAgreeBilibili)
    except Exception:  # noqa: BLE001 - 配置不可用时按默认关闭，绝不擅自同意
        return False


async def _agree_privacy(
    device: _Device,
    frame: np.ndarray,
    items: list[tuple[str, Box]],
    *,
    progress: Progress | None,
) -> tuple[np.ndarray, list[tuple[str, Box]]]:
    """点掉隐私政策提示里的「同意」；返回点击后的新一帧。

    自动同意必须复用全局「同意哔哩哔哩用户协议」开关（默认关闭）：开关没开时
    不点、提示手动处理并停止本次登录，不新增另一份协议入口。识别不明确时响亮失败。
    """

    if not _if_agree_bilibili():
        raise MaaFWLoginRequired(
            "B 服登录失败：检测到 bilibili 隐私政策提示，但未开启「托管Bilibili游戏隐私政策」；"
            "请手动同意，或在「设置 → 功能设置 → 神秘入口」里打开该开关后重试"
        )
    buttons = _pick(
        items,
        lambda text: bool(_AGREE_RE.match(text)),
        frame,
        x_range=_AGREE_X_RANGE,
        y_range=_AGREE_Y_RANGE,
    )
    if len(buttons) != 1:
        raise MaaFWLoginRequired("B 服登录失败：隐私政策提示中未找到唯一的「同意」按钮")
    await device.tap(buttons[0])
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
        if await device.foreground(package):
            return
        if not started:
            started = True
            logger.info(f"B 服客户端未在前台，正在拉起: {package}")
            await device.start(package)
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
        await device.tap_point(width * _EXPAND_POINT[0], height * _EXPAND_POINT[1])
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
    await device.tap(matches[0])
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

    await device.tap(login_buttons[0])
    await _progress(progress, f"已选择账号「{masked}」并点击登录")
    logger.info(f"B 服已选择账号 {masked} 并点击登录")


async def _wait_panel_closed(
    device: _Device,
    *,
    progress: Progress | None,
) -> str:
    """登录后等哔哩哔哩面板消失，并用标题页的正向信号确认已回到标题页。

    「一帧没有登录记录文字」不算完成：过渡黑屏、加载动画、OCR 漏字都可能满足；
    只有连续 ``_TITLE_CONFIRM_FRAMES`` 帧认出标题页才算成功，其余画面继续有界等待，
    等满总时限仍没确认就失败。标题页的正向信号有两种：OCR 读到「START」，或读到登录成功
    后的「<昵称> 欢迎回来」横幅（横幅有时会盖住或淡化 START）。
    """

    deadline = time.monotonic() + _LOGIN_TIMEOUT
    title_frames = 0
    while True:
        if time.monotonic() > deadline:
            raise MaaFWLoginRequired(
                "B 服登录失败：点击登录后未确认回到游戏标题页（等待超时）"
            )
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            await _agree_privacy(device, frame, items, progress=progress)
            title_frames = 0
            continue
        if _has(items, _LOGIN_RECORD, _SWITCH_OTHER):
            title_frames = 0
        elif _title_like(items) or _welcome_like(items):
            title_frames += 1
            if title_frames >= _TITLE_CONFIRM_FRAMES:
                await asyncio.sleep(_TITLE_SETTLE_SECONDS)
                return "B 服登录完成，已确认回到游戏标题页，交给 M9A 进游戏运行"
        else:
            # 过渡帧（黑屏 / 加载 / OCR 漏字）：不提前判成功，继续有界等待
            title_frames = 0
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
    await device.tap_point(width * _EXIT_POINT[0], height * _EXIT_POINT[1])

    deadline = time.monotonic() + _LOGOUT_DIALOG_SECONDS
    confirmed = False
    while time.monotonic() <= deadline:
        await asyncio.sleep(_POLL_SECONDS)
        frame, items = await _ocr(device)
        confirms = _pick(items, lambda text: bool(_CONFIRM_RE.match(text)), frame)
        if len(confirms) == 1:
            await device.tap(confirms[0])
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
    host_adb: Any = None,
) -> str:
    """MAS 原生登录入口（契约见 MaaFW ``flavor.py`` 的 ``ensure_logged_in``）。

    只在 ``Run.LoginMode == "Mas"`` 时做事；返回写进运行日志的一句话，没做事就是空串。
    """

    mode = ""
    try:
        mode = str(getattr(getattr(script_config, "Run"), "LoginMode") or "")
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按默认项目登录处理
        mode = ""
    if mode.strip() != "Mas":
        return ""

    if not adb_address:
        raise MaaFWLoginRequired(
            "MAS B 服登录仅支持 ADB 控制器，请切换控制器或使用项目登录"
        )

    account = str(getattr(getattr(user_config, "Info", None), "Account") or "").strip()
    if not account:
        raise MaaFWLoginRequired(
            "B 服登录失败：账号为空，请在本账号的「账号」里填写登录记录中显示的完整昵称"
        )
    package = str(package_name or "").strip() or BILIBILI_PACKAGE
    if package != BILIBILI_PACKAGE:
        raise MaaFWLoginRequired(
            f"B 服登录失败：登录方式选了「Mas」，但要启动的客户端是「{package}」；"
            f"Mas 登录只能用于 B 服客户端（{BILIBILI_PACKAGE}）。"
            "请把脚本资源与游戏包名都改成 B 服，或把登录方式改回「Project」"
        )
    if not _is_bilibili_resource(resource_name):
        raise MaaFWLoginRequired(
            f"B 服登录失败：登录方式选了「Mas」，但脚本资源是「{resource_name or '未选择'}」；"
            "Mas 登录只支持「B 服」资源，请改选后再运行（或把登录方式改回「Project」）"
        )
    device = _Device(adb_path, adb_address, host_adb)

    await _progress(
        progress, f"B 服登录：使用账号「{_mask(account)}」，客户端 {package}"
    )
    await _wait_foreground(device, package, progress=progress)

    deadline = time.monotonic() + _LOGIN_TIMEOUT
    unknown_since: float | None = None
    unknown_budget = _unknown_screen_budget(script_config)
    title_polls = 0
    logout_tried = False
    while True:
        if time.monotonic() > deadline:
            raise MaaFWLoginRequired(
                "B 服登录失败：等待登录界面超时（游戏可能未启动或加载过慢）"
            )
        frame, items = await _ocr(device)
        if _privacy_prompt(items):
            await _agree_privacy(device, frame, items, progress=progress)
            unknown_since = None
            continue
        if _warning_like(items):
            # 冷启动的健康警告页：点一下继续（M9A 的 StartUp 也会处理，但登录跑在它前面）
            height, width = frame.shape[:2]
            await _progress(progress, "已关闭游戏健康警告页")
            await device.tap_point(width * 0.5, height * 0.5)
            await asyncio.sleep(1.0)
            unknown_since = None
            continue
        if _has(items, _LOGIN_RECORD):
            await _select_account(device, frame, items, account, progress=progress)
            return await _wait_panel_closed(device, progress=progress)

        # 标题页 = 已登录：MAS 不知道当前是哪个号，为了保证切到目标账号，登出后重选。
        # 「START」与「<昵称> 欢迎回来」横幅都算标题页已登录。
        if not logout_tried and (_title_like(items) or _welcome_like(items)):
            title_polls += 1
            if title_polls >= _TITLE_SETTLE_POLLS:
                logout_tried = True
                await _logout_to_login_panel(device, frame, progress=progress)
                unknown_since = None
                title_polls = 0
                continue
        else:
            title_polls = 0

        # 既不是登录界面、也认不出标题页（例如游戏停在别的账号的主界面）：
        # 无法确认当前账号，明确停止，不能把「没认出来」当成「目标账号已登录」。
        # 冷启动的加载画面同样落在这里，所以预算服从 Game.WaitTime，不能按固定 60 秒截断。
        if unknown_since is None:
            unknown_since = time.monotonic()
        elif time.monotonic() - unknown_since >= unknown_budget:
            raise MaaFWLoginRequired(
                "B 服登录失败：无法确认当前账号（画面既不是登录记录也不是游戏标题页，"
                f"已等待 {int(unknown_budget)} 秒）；"
                "请把游戏停在标题页或退出到登录界面后重试"
            )
        await asyncio.sleep(_POLL_SECONDS)


__all__ = [
    "BILIBILI_PACKAGE",
    "BILIBILI_START_ACTIVITY",
    "ensure_logged_in",
]
