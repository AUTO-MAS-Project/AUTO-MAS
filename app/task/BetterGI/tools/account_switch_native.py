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

"""BetterGI（原神）MAS 侧强制账号切换（官服 miHoYo / B服 bilibili 渠服登录）。

参照 OK-WW / OK-NTE 强制切号骨架（前台 pyautogui + DPI 适配 + 1080p 帧坐标空间，
OCR 复用通用工具集 `app.tools.ocr`）。登录界面部分元素没有文本（退出图标、
切换图标、输入框、下拉箭头），无文本元素按 1080p 帧相对坐标点击；勾选/单选
状态用橙色填充做颜色判定，避免已勾选时二次点击反而取消。

官服流程（有密码/无密码前 4 步相同，取自实机截图「原神账号切换流程」）::

    等待进入可切号态（标题「点击进入」/ 登录对话框 / 账密表单）
    （游戏内滞留时：ESC → 派蒙菜单「退出游戏」→ 退出到标题）
    → 点标题右侧退出图标 → 「退出登录」弹窗选「退出并保留登录记录」→ 点「退出」
    → 有密码（填了密码时）: 点「登录其他账号」→ 点账号框剪贴板粘贴账号
      → 点密码框剪贴板粘贴密码 → 点「进入游戏」
    → 无密码（未填密码时）: 点账号框展开下拉列表 → 按掩码（138******78）匹配
      目标账号（超出可见范围滚轮翻页）→ 点「进入游戏」
    → 协议未勾选时游戏弹「是否同意」确认框 → 点「同意」（登录等待循环统一
      兜底，两版共用；勾选圆点过小不做预勾选）
    → 等待登录界面消失（登录成功，游戏保持运行交还 BGI 一条龙）

B服流程（取自实机截图「B服切换流程」；暂不支持账密登录——验证码无法自动
完成，填了密码也忽略）::

    等待进入可切号态（标题「点击进入」/ 隐私政策弹窗 / 登录记录面板）
    （无登录会话时先弹 bilibili 隐私政策 → 点「同意」进面板）
    → 点标题右下角切换账号图标 → 「确认切换账号?」点「确定」→ 登录记录面板
    → 点账号卡片下拉箭头展开列表 → 按B站昵称匹配点选目标（LCS ≥ 0.7，
      超出可见范围滚轮翻页；排除当前账号卡片防误点收起）
    → 点「登录」→ 等待「点击进入」重新出现（B服登录后回标题而非进游戏）

掩码匹配复用上游切号脚本适配的 `mask_account`（与官服登录界面打码规则一致），
OCR 对 `*` 的识别漂移用宽容正则（`*`/`x`/`＊` 等同处理）兜住；B服昵称按
LCS 相似度匹配（对齐一条龙 find_by_lcs 的 0.7 阈值口径）。
"""

import asyncio
import ctypes
import inspect
import re
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import psutil
from PIL import Image

from app.tools.ocr import Box, OCRItem, ocr_image
from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

from .account_switch import mask_account

if IS_WINDOWS:
    # pyautogui / pywin32 仅 Windows 可用（无图形会话导入即失败），随入口的
    # IS_WINDOWS 检查一并惰性导入，避免非 Windows 环境在未启用切号时导入崩溃
    import pyautogui
    import win32api
    import win32clipboard
    import win32con
    import win32gui
    import win32process

logger = get_logger("BetterGI 账号切换")

# 切换流程互斥锁：两个切换线程并发驱动同一游戏窗口会互相踩踏（2026-09-23 实机：
# 任务反复启停留下僵尸切换线程，与下一个用户的切换并发，一个点开账密表单、
# 另一个在滚轮翻页，最终把隐私政策文档页都点了出来）。非阻塞获取，抢不到
# 直接响亮失败，不排队。
_SWITCH_LOCK = threading.Lock()

# 诊断文件（debug/bgi-account-switch/switch-detail-*.log）：记录切换过程各步骤
# OCR 文本，供用户反馈登录失败时对照定位识别漂移；切换串行独占前台，单例写入。
_DIAGNOSTIC_PATH: Path | None = None


def _write_diagnostic(text: str) -> None:
    """向诊断文件追加一行（旁路，失败时静默忽略）；统一脱敏后落盘。"""
    if _DIAGNOSTIC_PATH is not None:
        try:
            with _DIAGNOSTIC_PATH.open("a", encoding="utf-8") as handle:
                handle.write(_sanitize_ocr_text(text))
        except OSError:
            pass


# 诊断脱敏：OCR 原文会落盘到 debug 目录，账密表单粘贴账号后的全帧识别会把
# 明文账号带进诊断文件——手机号（11 位，与 account_switch 的 _PHONE_DIGITS 同口径，
# 容 OCR 少读/多读一两位）与邮箱地址统一打码后再写入。只认这两种形态，避免把
# 游戏版本号等无关长数字一并打码而损害诊断可读性。
_DIAGNOSTIC_PHONE_RE = re.compile(r"1\d{9,11}")
_DIAGNOSTIC_EMAIL_RE = re.compile(
    r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*([A-Za-z0-9._%+-])@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)


def _sanitize_ocr_text(text: str) -> str:
    """把诊断文本中的手机号与邮箱地址打码（进度日志本就走 mask_account）。"""
    text = _DIAGNOSTIC_PHONE_RE.sub(
        lambda m: f"{m.group()[:3]}******{m.group()[-2:]}", text
    )
    return _DIAGNOSTIC_EMAIL_RE.sub(r"\1****\2@***", text)


# ── 原神客户端窗口识别（与 BetterGI/AutoProxy 的 _BGI_GAME_PROCESS_NAMES 一致）──
_GENSHIN_PROCESS_NAMES = ("YuanShen.exe", "GenshinImpact.exe")

# 游戏窗口就绪宽限期：MAS 托管拉起原神后窗口创建/亮相存在启动延迟（反作弊 +
# 资源加载），账号切换在窗口就绪前无从执行，须在宽限期内轮询等待。
_GAME_WINDOW_WAIT_SECONDS = 120.0
# 窗口轮询间隔。
_WINDOW_POLL_INTERVAL = 1.0
# 可切号态稳定等待：窗口已出现但尚未进入可切号态（启动过渡帧/加载/游戏内更新）
# 时，在硬上限内轮询等待「标题」「登录对话框」「账密表单」之一出现。界面仍在变化
# （有进展）时持续顺延；持续无进展则尝试「游戏内退出到标题」后继续等待。
_IN_GAME_UPDATE_TIMEOUT = 3600.0
# 长时间无进展判定：界面静止达到该时长仍非可切号态则视为滞留游戏内，
# 尝试从派蒙菜单退出到标题界面。
_IN_GAME_STALL_SECONDS = 60.0
# 累计未命中可切号态的派蒙退出间隔：原神大世界待机画面持续变化（云影/水面/
# 角色动画），帧哈希永远「有进展」，滞留兜底不能依赖画面静止——改为累计
# 未进入可切号态达到该时长即周期性尝试退出（不在游戏内时尝试无害静默失败）。
_STATE_ESCAPE_SECONDS = 90.0
# 可切号态等待的轮询间隔（比窗口等待更宽松，降低长等待期 OCR 负载）。
_IN_GAME_POLL_INTERVAL = 3.0
# 长等待期诊断 OCR 的落盘节流：若每个轮询都全量写诊断文件会累积数千行；
# 改为每 N 次轮询（≈ N*3s）写一次，保留过渡帧采样又不膨胀。
_DIAGNOSTIC_DUMP_EVERY_POLLS = 10

# 截图基准分辨率（16:9），OCR 与点击均在此坐标空间计算后再映射回真实窗口
_FRAME_WIDTH = 1920
_FRAME_HEIGHT = 1080

# ── 1080p 帧固定坐标（取自 1024x576 实机截图 ×1.875 映射；无文本元素按位置点击）──
# 标题界面右侧按钮列最底部的退出图标（设置/工具/卡片/退出 竖排的最下一个）
_LOGOUT_ICON_POINT = (1824, 979)
# 登录对话框（下拉选号态）「进入游戏」按钮中心
_LOGIN_ENTER_POINT = (973, 568)
# 登录对话框账号输入框右侧的下拉箭头（展开账号列表的第二入口）
_DROPDOWN_ARROW_POINT = (1202, 497)
# 账号输入框 ROI（当前账号掩码显示区，用于选号后回读校验）。
# ⚠️ ocr_image 的 roi 参数是 (left, top, right, bottom) 语义（与返回识别框的
# (x, y, w, h) 不同）：此前按 (x, y, w, h) 传入导致裁剪为空切片、RapidOCR
# 抛异常，表现为「选号点击已生效却在回读校验时切号失败」（2026-09-22 实机）。
_ACCOUNT_FIELD_ROI: Box = (694, 459, 1238, 534)
# 账密表单：账号输入框 / 密码输入框 / 「进入游戏」按钮中心
_FORM_ACCOUNT_POINT = (958, 399)
_FORM_PASSWORD_POINT = (958, 484)
_FORM_ENTER_POINT = (973, 709)
# 账密表单内部相对锚定：账号/密码输入框纵向间距、密码框到「进入游戏」按钮的
# 偏移。占位符 OCR 只认出一个时据此推算另一个——miHoYo 登录 UI 是内嵌网页，
# 会随游戏/SDK 版本更新重排（B服面板 2026-09-23 实测漂移 ±70px），固定点仅作
# 最后兜底。
_FORM_FIELD_Y_GAP = 85
_FORM_ENTER_Y_OFFSET_FROM_PASSWORD = 225
_FORM_ENTER_Y_OFFSET_FROM_ACCOUNT = 310
# 登录对话框：「登录其他账号」链接到「进入游戏」按钮的纵向偏移（兜底锚定用）
_LOGIN_ENTER_Y_OFFSET_FROM_OTHER = 125
# 账号列表滚动中心（下拉列表展开后的中部），目标账号超出可见范围时滚轮翻页
_LIST_SCROLL_POINT = (966, 620)
# 勾选框/单选圆点相对其右侧文本框的横向偏移（圆点在文本左侧 35px 处）
_CHECK_OFFSET_X = 35

# 仅标题界面出现的文本（底部横条），用于判定「处于标题界面（点击进入）」
_TITLE_TEXTS = ("点击进入",)
# 仅登录对话框（下拉选号态）出现的文本：底部「登录其他账号」链接
_LOGIN_DIALOG_TEXTS = ("登录其他账号",)
# 仅账密表单出现的文本：占位符「输入密码」与协议链接「用户协议」
_PASSWORD_FORM_TEXTS = ("输入密码", "用户协议")
# 「退出登录」确认弹窗内独有的单选项文本
_KEEP_RECORDS_TEXT = "退出并保留登录记录"

# ── B服（bilibili 渠服）登录界面 ─────────────────────────────────────────
# B服与官服共用同一游戏进程（YuanShen.exe），登录 UI 完全不同：入口是标题右下
# 角切换账号图标（非官服的右侧栏退出图标），面板按B站昵称展示登录记录。
#
# ⚠️ 实机结论（2026-09-23）：登录记录面板的纵向位置在两次运行间会漂移约 ±70px
# （1080p 帧空间），固定坐标不可靠——面板内元素一律以「上次登录」标记行
# （每条登录记录都带，OCR 可锚定）为纵向锚点相对定位，x 依赖面板恒定中线。
# 仅B服隐私政策弹窗出现的文本（标题「bilibili游戏隐私政策提示」，点「同意」继续）
_BILI_PRIVACY_TEXTS = ("隐私政策",)
# 仅B服登录记录面板出现的文本（面板标题），出现即可选号
_BILI_PANEL_TEXTS = ("登录记录",)
# B服标题界面右侧图标列最底部的 ≡ 图标（与官服退出图标同一 UI 槽位：官服点它
# 弹「退出登录」，B服点它弹「确认切换账号?」）。⚠️ 不要点屏幕最角落的 B站 SDK
# 悬浮控件——那是第三方悬浮窗，且该位置落在「点击进入」横条热区内，误点会
# 直接用当前账号进游戏（2026-09-23 实机踩坑）
_BILI_SWITCH_ICON_POINT = (1824, 979)
# B服账号卡片行右侧展开箭头：相对卡片锚行（最顶部「上次登录」标记中心）的
# 校准偏移。箭头命中框很小且必须精确命中（点卡片其他区域无效），实机校准
# （2026-09-23）：箭头中心 = 锚行中心上移 16px、x=1129；点击后必须逐次验证
# 展开状态（点击是翻转开关），未展开则在校准点周围 ±12/±10px 候选网格继续尝试
_BILI_ARROW_X = 1129
_BILI_ARROW_Y_OFFSET_FROM_CARD = -16
# B服面板「登录」按钮中心（粉色按钮，OCR 失败时兜底点击；y 相对卡片锚行偏移）
_BILI_LOGIN_POINT = (962, 703)
_BILI_LOGIN_Y_OFFSET_FROM_CARD = 150
# B服隐私政策弹窗「同意」按钮中心（粉色按钮，OCR 失败时兜底点击）
_BILI_AGREE_POINT = (1000, 622)
# 点击「登录」后面板关闭的等待上限：超时说明登录未生效，响亮失败而非继续
# 等待（后续标题等待的派蒙退出兜底会按 ESC 关掉面板，把「没切成」误判成完成）
_BILI_LOGIN_EFFECT_TIMEOUT = 60.0
# B服登录记录列表滚动中心（目标账号不在可见范围时滚轮翻页）
_BILI_LIST_SCROLL_POINT = (962, 656)
# 每条登录记录都带的「上次登录」时间戳文本；列表展开后面板内出现 ≥2 条
_BILI_RECORD_MARK = "上次登录"
# 当前账号卡片行（最顶部的「上次登录」标记）的 y 判定窗口：匹配列表项与
# 选号回读时排除/采信该行附近的文本，防止误点卡片把已展开的列表收起
_BILI_CARD_ROW_WINDOW = 35
# B站昵称与 OCR 文本的相似度阈值（LCS 比例，对齐一条龙 switch_bilibili_account
# 的 percent=0.7 口径，容 OCR 漂移与表情符号丢失）
_BILI_NICKNAME_THRESHOLD = 0.7

# 勾选框/单选圆点选中态的橙色填充（miHoYo UI 主题色）：HSV 宽松区间做在位判定
_CHECK_HUE_RANGE = (8, 28)
_CHECK_SAT_MIN = 60
_CHECK_VAL_MIN = 120


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
    """按所属进程名定位原神主窗口（官服 YuanShen / 国际服 GenshinImpact）。

    用 ``EnumWindows + psutil.Process(pid).name()`` 而非 process_iter 的 name 属性，
    规避提权进程 name 读取被拒导致的漏判；同进程存在多个窗口时取面积最大者。

    Args:
        wait: 为 True 时在宽限期 ``_GAME_WINDOW_WAIT_SECONDS`` 内轮询等待窗口就绪，
            吸收 MAS 拉起游戏后窗口延迟亮相的启动阶段；为 False 时单次枚举立即返回。

    Raises:
        RuntimeError: 宽限期结束仍未定位到原神游戏窗口。
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
            if pid and _process_name(pid) in _GENSHIN_PROCESS_NAMES:
                candidates.append(hwnd)
            return True

        win32gui.EnumWindows(_enum, 0)
        if candidates:
            return max(candidates, key=_window_area)
        if not wait or time.monotonic() >= deadline:
            break
        logger.info(
            f"原神游戏进程已启动但窗口暂未就绪，{_WINDOW_POLL_INTERVAL:g} 秒后重试..."
        )
        time.sleep(_WINDOW_POLL_INTERVAL)
    raise RuntimeError(
        f"未找到原神游戏窗口（进程 {_GENSHIN_PROCESS_NAMES}），"
        "请确认游戏已由 MAS 启动或已在运行"
    )


# ── 截图 / 交互（前台 pyautogui + DPI 适配）─────────────────────────────


def _activate_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("原神游戏窗口已失效")
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
        if win32gui.GetForegroundWindow() != hwnd:
            # Windows 前台锁：后台进程不能直接抢占前台。先附着当前前台窗口线程
            # 的输入队列，再置前，绕过系统限制（与 OK-WW/OK-NTE 切号同理）。
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
        logger.debug("原神游戏窗口焦点请求被系统忽略，继续按前置窗口处理")
    time.sleep(0.1)


def _client_size(hwnd: int) -> tuple[int, int]:
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("原神游戏窗口尺寸异常")
    if abs(width / height - 16 / 9) > 0.02:
        logger.warning(f"原神窗口非 16:9（{width}x{height}），账号切换坐标可能偏移")
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


def _click_point(hwnd: int, px: int, py: int, *, after_sleep: float = 0.3) -> None:
    _click_box(hwnd, (px, py, 1, 1), after_sleep=after_sleep)


def _press_escape(hwnd: int, *, after_sleep: float = 1.5) -> None:
    _activate_window(hwnd)
    pyautogui.press("esc")
    time.sleep(after_sleep)


def _scroll_list(
    hwnd: int, point: tuple[int, int] = _LIST_SCROLL_POINT
) -> None:
    """在指定滚动中心区域滚轮下翻一页（目标账号不在可见范围时使用）。"""
    with _per_monitor_dpi():
        width, height = _client_size(hwnd)
        px, py = point
        client_x = round(px * width / _FRAME_WIDTH)
        client_y = round(py * height / _FRAME_HEIGHT)
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    pyautogui.moveTo(screen_x, screen_y)
    time.sleep(0.2)
    pyautogui.scroll(-3)
    time.sleep(0.5)


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


def _on_title_screen(hwnd: int) -> bool:
    """标题界面（「点击进入」横条）。"""
    return _find_text(_read_texts(hwnd), _TITLE_TEXTS) is not None


def _on_login_dialog(hwnd: int) -> bool:
    """登录对话框（下拉选号态）：底部「登录其他账号」链接。"""
    return _find_text(_read_texts(hwnd), _LOGIN_DIALOG_TEXTS) is not None


def _on_password_form(hwnd: int) -> bool:
    """账密表单：占位符「输入密码」或协议链接「用户协议」。"""
    return _find_text(_read_texts(hwnd), _PASSWORD_FORM_TEXTS) is not None


def _frame_signature(frame: np.ndarray) -> int:
    """对下采样的帧做哈希，用于判断界面是否仍在变化（有加载/更新进展）。"""
    small = frame[::40, ::40]
    return hash(small.tobytes())


def _check_is_marked(frame: np.ndarray, point: tuple[int, int]) -> bool:
    """判定勾选框/单选圆点是否已选中（橙色填充）。

    在 1080p 帧空间取圆点附近小邻域，统计橙色像素占比； miHoYo UI 的选中态
    为橙色实心、未选中为空心灰框，占比超过阈值即视为已选中。
    """
    cx, cy = point
    half = 14
    x0, y0 = max(cx - half, 0), max(cy - half, 0)
    region = frame[y0 : cy + half, x0 : cx + half]
    if region.size == 0:
        return False
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    hue_lo, hue_hi = _CHECK_HUE_RANGE
    mask = cv2.inRange(
        hsv,
        np.array([hue_lo, _CHECK_SAT_MIN, _CHECK_VAL_MIN], dtype=np.uint8),
        np.array([hue_hi, 255, 255], dtype=np.uint8),
    )
    return int(np.count_nonzero(mask)) >= region.shape[0] * region.shape[1] * 0.08


def _click_checkbox_near_text(
    hwnd: int, text_box: Box, *, expect_checked: bool | None = None
) -> None:
    """点击文本左侧的勾选框/单选圆点（圆点在文本左侧 ``_CHECK_OFFSET_X`` 处）。

    Args:
        text_box: OCR 识别到的文本框（1080p 帧空间）。
        expect_checked: 传入时先做橙色在位判定——已处于期望状态则跳过点击
            （二次点击会把勾选/单选改回另一态）。
    """
    x, y, _, h = text_box
    point = (max(x - _CHECK_OFFSET_X, 0), y + h // 2)
    if expect_checked is not None:
        marked = _check_is_marked(_capture_window(hwnd, activate=False), point)
        if marked == expect_checked:
            return
    _click_point(hwnd, *point, after_sleep=0.8)


# ── 剪贴板输入（参照一条龙 PcClipboard 的成熟做法）──────────────────────


def _clipboard_copy_and_paste(text: str) -> None:
    """把文本写入剪贴板后向游戏窗口粘贴（Ctrl+V），用后清空剪贴板。

    原神登录框的密码输入对逐键模拟过滤严格，剪贴板粘贴是一条龙验证过的
    输入通道；全程不落日志明文。
    """
    if not IS_WINDOWS:
        raise RuntimeError("账号切换仅支持 Windows 平台")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    try:
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.8)
    finally:
        # 粘贴完成后立即清空，避免明文账密残留在系统剪贴板
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass


# ── 掩码账号匹配（复用上游切号脚本适配的打码规则）────────────────────────

# OCR 对掩码 `*` 的识别漂移（`*`/`x`/`＊`/`﹡` 等）统一按该字符类匹配
_MASK_CHAR_CLASS = r"[*xX＊﹡✳]"


def _mask_pattern(account: str) -> re.Pattern[str] | None:
    """由完整账号生成登录界面掩码（138******78 / 11****1@919.com）的宽容匹配正则。

    第三方登录账号（mask_account 原样返回、无打码锚点）无法按掩码匹配，
    返回 None，由调用方显式报错。
    """
    mask = mask_account(account)
    parts = [p for p in re.split(r"\*+", mask) if p]
    if len(parts) < 2:
        return None
    # 字面片段之间用「宽松掩码字符类（可含空白）」连接：
    # 138******78 → 138\s*[*xX＊﹡]+\s*78；11****1@919.com → 11\s*[*xX＊﹡]+\s*1@919\.com
    pieces = [re.escape(parts[0])]
    for part in parts[1:]:
        pieces.append(rf"\s*{_MASK_CHAR_CLASS}+\s*{re.escape(part)}")
    return re.compile("".join(pieces))


def _box_center_in(box: Box, region: Box) -> bool:
    """判断识别框中心是否落在 (left, top, right, bottom) 区域内。"""
    x, y, w, h = box
    left, top, right, bottom = region
    return left <= x + w / 2 <= right and top <= y + h / 2 <= bottom


def _find_masked_account(
    hwnd: int, pattern: re.Pattern[str], *, exclude: Box | None = None
) -> Box | None:
    """在当前画面中查找匹配目标掩码的账号文本框。

    Args:
        pattern: 目标账号的宽容掩码匹配正则。
        exclude: 传入时跳过中心落在该区域内的命中——选号时用它排除账号
            输入框本身（输入框文本同样匹配掩码且排在列表项之前，误点会把
            已展开的下拉列表收起而不是选中目标账号）。
    """
    for text, box in _read_texts(hwnd):
        if pattern.search(text):
            if exclude is not None and _box_center_in(box, exclude):
                continue
            return box
    return None


# ── 游戏内退出到标题（多用户循环时上一账号仍登录在游戏内的兜底）──────────


def _exit_to_title_from_game(hwnd: int, on_log: Callable[[str], None]) -> bool:
    """从游戏内（大世界/任意界面）经派蒙菜单退出到标题界面。

    ESC 打开派蒙菜单 → 点左下角「退出游戏」→ 如弹出确认框点「确认/确定」。
    原神游戏内没有「返回登录」入口，只能退出到标题后再按流程图切号。
    返回是否成功触发退出（标题出现与否由调用方继续等待确认）。
    """
    for attempt in range(1, 4):
        on_log(f"尝试从游戏内退出到标题界面（{attempt}/3）")
        _press_escape(hwnd, after_sleep=1.5)
        items = _read_texts(hwnd)
        exit_box = _find_text(items, ("退出游戏",))
        if exit_box is None:
            # ESC 可能先关掉了某个已打开界面，再按一次
            _press_escape(hwnd, after_sleep=1.5)
            exit_box = _find_text(_read_texts(hwnd), ("退出游戏",))
        if exit_box is None:
            continue
        _click_box(hwnd, exit_box, after_sleep=2)
        # 部分版本弹出确认框，出现「确认/确定」即点击（取最右，避开取消）
        confirm_items = _read_texts(hwnd)
        confirms = [
            (t, b)
            for t, b in confirm_items
            if t in ("确认", "确定") or ("确认" in t and "取消" not in t and "？" not in t)
        ]
        if confirms:
            _click_box(hwnd, max(confirms, key=lambda item: item[1][0])[1], after_sleep=2)
        on_log("已点击退出游戏，等待回到标题界面")
        return True
    return False


def _wait_until_state(
    hwnd: int,
    on_log: Callable[[str], None],
    states: tuple[tuple[str, ...], ...],
) -> int:
    """等待画面进入任一目标文本态，返回当前有效窗口句柄。

    通用「进展续延」等待驱动，官服可切号态等待与B服各阶段等待共用：

    - 命中 ``states`` 中任一组文本 → 返回当前有效句柄；
    - 界面仍在变化（有加载/更新进展）→ 持续顺延，硬上限 ``_IN_GAME_UPDATE_TIMEOUT``；
    - 界面静止 ``_IN_GAME_STALL_SECONDS``（模态弹窗等确认的典型形态）→ 识别并
      点击确认类按钮继续；
    - 累计 ``_STATE_ESCAPE_SECONDS`` 仍未命中 → 周期性尝试经派蒙菜单退出到
      标题（覆盖大世界滞留——原神待机画面持续变化，帧哈希永远「有进展」，
      滞留兜底不能依赖画面静止；不在游戏内时尝试无害静默失败）；
    - 等待期间窗口句柄失效（版本更新确认后游戏本体退出、交由启动器更新重启）
      → 重新定位原神窗口继续等待，而非直接失败。

    进度日志按约 5 条/轮询节流，避免向调度台频繁刷屏。
    """
    deadline = time.monotonic() + _IN_GAME_UPDATE_TIMEOUT
    state_wait_start = time.monotonic()
    last_progress = time.monotonic()
    last_sig: int | None = None
    items_full: list[OCRItem] = []
    iter_count = 0
    while time.monotonic() < deadline:
        try:
            frame = _capture_window(hwnd, activate=False)
        except (RuntimeError, win32gui.error):
            # 窗口句柄失效：版本更新确认后游戏本体退出（更新由启动器接手），
            # 在宽限期内重新定位原神窗口继续等待，更新完回到标题后照常切号。
            # 注意句柄销毁抛的是 pywintypes.error（即 win32gui.error）而非
            # RuntimeError——后者只覆盖 _client_size 的零尺寸分支
            hwnd = _reacquire_game_hwnd(on_log)
            state_wait_start = last_progress = time.monotonic()
            last_sig = None
            continue
        sig = _frame_signature(frame)
        if sig != last_sig:
            # 画面有变化才跑 OCR；帧哈希未变时沿用上次识别结果
            items_full = ocr_image(frame)
            last_sig = sig
            last_progress = time.monotonic()
        if iter_count % _DIAGNOSTIC_DUMP_EVERY_POLLS == 0:
            _dump_ocr_items(items_full)
        if any(_find_text(items_full, st) is not None for st in states):
            return hwnd
        if time.monotonic() - last_progress >= _IN_GAME_STALL_SECONDS:
            # 画面静止常是模态弹窗在等确认（游戏内更新提示、版本更新引导等）：
            # 点击确认类按钮继续（不影响下面的累计退出兜底计时）
            try:
                confirmed = _click_confirm_dialog(hwnd, on_log)
            except (RuntimeError, win32gui.error):
                hwnd = _reacquire_game_hwnd(on_log)
                state_wait_start = last_progress = time.monotonic()
                last_sig = None
                continue
            if confirmed:
                # 弹窗已处理属有效进展，重新起算累计退出计时
                state_wait_start = time.monotonic()
            last_progress = time.monotonic()
        if time.monotonic() - state_wait_start >= _STATE_ESCAPE_SECONDS:
            # 累计仍未命中目标态（大世界滞留 / 卡在未知界面）：周期性尝试
            # 经派蒙菜单退出到标题；不在游戏内时找不到「退出游戏」，静默无害
            state_wait_start = time.monotonic()
            escaped = False
            with suppress(Exception):
                escaped = _exit_to_title_from_game(hwnd, on_log)
            if not escaped:
                on_log("未找到游戏内退出入口（可能不在游戏内），继续等待...")
        if iter_count % 5 == 0:
            on_log("原神仍在启动/加载过渡帧或游戏内，继续等待目标界面...")
        iter_count += 1
        time.sleep(_IN_GAME_POLL_INTERVAL)
    raise RuntimeError(
        "等待原神目标界面超时：长时间无进展或超过硬上限"
        f"（{_IN_GAME_UPDATE_TIMEOUT:g}s），请人工确认游戏状态后重试"
    )


def _wait_for_actionable_state(hwnd: int, on_log: Callable[[str], None]) -> int:
    """等待进入官服可执行的切号态（标题 / 登录对话框 / 账密表单），返回有效句柄。"""
    return _wait_until_state(
        hwnd,
        on_log,
        (_TITLE_TEXTS, _LOGIN_DIALOG_TEXTS, _PASSWORD_FORM_TEXTS),
    )


# 等待确认类模态弹窗的按钮文本（精确匹配，参照一条龙 match_login_error 的
# 「确定/重试」口径 + 原神更新引导的「确认」）；不用「更新」等宽泛词防误点
_CONFIRM_DIALOG_TEXTS = ("确认", "确定", "重试")


def _click_confirm_dialog(hwnd: int, on_log: Callable[[str], None]) -> bool:
    """静止画面的模态弹窗兜底：识别「确认/确定/重试」按钮并点击。

    游戏内更新提示、版本更新引导等弹窗会停住画面等确认（帧静止触发本兜底）；
    按钮文本精确匹配、多个命中取最右（确认在取消右侧），避免误点说明文本。

    Returns:
        是否找到并点击了确认类按钮。
    """
    candidates = [
        (t, b) for t, b in _read_texts(hwnd) if t in _CONFIRM_DIALOG_TEXTS
    ]
    if not candidates:
        return False
    text, box = max(candidates, key=lambda item: item[1][0] + item[1][2])
    on_log(f"识别到等待确认的弹窗按钮「{text}」，点击继续")
    _click_box(hwnd, box, after_sleep=2)
    return True


def _reacquire_game_hwnd(on_log: Callable[[str], None]) -> int:
    """窗口句柄失效（版本更新确认后游戏退出/重启）时重新定位原神窗口。

    在宽限期内轮询等待；更新流程会先回到启动器再重启游戏本体，宽限期够
    游戏退出后的短暂空窗，若更新耗时过长（启动器接手）则最终抛出失败。
    """
    on_log("游戏窗口句柄已失效（可能进入更新流程），重新定位原神窗口...")
    return _find_game_hwnd(wait=True)


# ── 退出登录弹窗 → 登录对话框 ───────────────────────────────────────────


def _find_logout_confirm_box(items: list[OCRItem]) -> Box | None:
    """在 OCR 条目中定位退出弹窗的「退出」按钮。

    弹窗内还有标题「退出登录」与单选项「退出并清除/保留登录记录」，均含
    「退出」子串必须排除；按钮文本恰为「退出」，与左侧「取消」区分，多个
    命中取最右（确认按钮在弹窗右侧）。
    """
    candidates = [
        (t, b)
        for t, b in items
        if "退出" in t
        and "并" not in t
        and "登录" not in t
        and "取消" not in t
        and "？" not in t
        and "?" not in t
    ]
    if not candidates:
        return None
    for t, b in candidates:
        if t == "退出":
            logger.info("原神退出按钮精确命中「退出」")
            return b
    text, box = max(candidates, key=lambda item: item[1][0] + item[1][2])
    logger.info(f"原神退出按钮命中候选文本: {text}")
    return box


def _open_login_dialog(hwnd: int, on_log: Callable[[str], None]) -> None:
    """标题界面 → 点右侧退出图标 → 「退出登录」弹窗选保留记录并退出。

    该图标点击是双入口：已登录（有记录会话）时弹出「退出登录」确认弹窗，
    未登录时直接打开登录对话框，按点击后弹出的界面分流。
    """
    on_log("正在点击标题界面右侧退出图标")
    _click_point(hwnd, *_LOGOUT_ICON_POINT, after_sleep=1.5)

    confirm: Box | None = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        items = _read_texts(hwnd)
        if _find_text(items, _LOGIN_DIALOG_TEXTS) is not None:
            on_log("登录对话框已打开（当前无登录会话）")
            return
        if _find_text(items, _PASSWORD_FORM_TEXTS) is not None:
            on_log("账密登录表单已打开（当前无登录会话）")
            return
        keep = _find_text(items, (_KEEP_RECORDS_TEXT,))
        if keep is not None:
            confirm = _find_logout_confirm_box(items)
            if confirm is not None:
                # 「退出并保留登录记录」单选默认不在选中态，未选中先点选
                _click_checkbox_near_text(hwnd, keep, expect_checked=True)
                time.sleep(0.5)
                break
        time.sleep(1)

    if confirm is None:
        raise RuntimeError(
            "点击退出图标后未出现退出确认或登录对话框，请人工确认当前处于标题界面"
        )
    on_log("已选择「退出并保留登录记录」，点击「退出」")
    _click_box(hwnd, confirm, after_sleep=2)

    if (
        _wait_ocr_text(hwnd, _LOGIN_DIALOG_TEXTS, timeout=30) is None
        and not _on_password_form(hwnd)
    ):
        raise RuntimeError("退出账号后登录界面未打开（30s 未识别到登录对话框）")
    on_log("已退出当前账号，登录界面已打开")


# ── 无密码版：下拉列表按掩码选号 ────────────────────────────────────────


def _detect_field_account(hwnd: int, pattern: re.Pattern[str]) -> bool:
    """回读账号输入框当前掩码，判断是否已选中目标账号。"""
    items = _read_texts(hwnd, _ACCOUNT_FIELD_ROI)
    if any(pattern.search(text) for text, _ in items):
        return True
    # ROI 内 OCR 瞬时失败时退回全帧查找（展开的列表可能未收起）
    return _find_masked_account(hwnd, pattern) is not None


def _expand_account_list(hwnd: int, on_log: Callable[[str], None]) -> None:
    """点击当前账号框（或其下拉箭头）直至账号列表展开（出现多个掩码账号）。

    若始终识别不到任何掩码账号，说明无法确认账号列表已打开（OCR 失败或
    登录界面布局变化）；继续选号可能落在错误账号上，按失败抛出而非静默返回。
    """
    found_masked = False
    for _ in range(3):
        items = _read_texts(hwnd)
        masked = [
            box
            for text, box in items
            if re.search(rf"\d{{3}}\s*{_MASK_CHAR_CLASS}+\d{{2}}", text)
            or "@" in text
        ]
        if len(masked) >= 2:
            return
        if not masked:
            # 可能 OCR 瞬时失败或列表已展开但只有一条记录，先点箭头兜底
            on_log("未识别到掩码账号，点击账号框下拉箭头")
            _click_point(hwnd, *_DROPDOWN_ARROW_POINT, after_sleep=1)
            continue
        found_masked = True
        _click_box(hwnd, masked[0], after_sleep=1)
    if not found_masked:
        raise RuntimeError(
            "未识别到任何掩码账号，无法确认账号列表已打开；"
            "若目标账号从未在本机登录过（无登录记录），请改用填密码的账号+密码方式"
        )


def _click_target_account(
    hwnd: int, pattern: re.Pattern[str], on_log: Callable[[str], None]
) -> bool:
    """在账号列表中点击目标掩码账号；不在可见范围时滚轮翻页（上限 5 页）。

    匹配时排除账号输入框区域：输入框文本同样命中掩码且排在列表项之前，
    误点输入框只会把已展开的下拉列表收起，而不是选中目标账号。
    """
    for page in range(6):
        box = _find_masked_account(hwnd, pattern, exclude=_ACCOUNT_FIELD_ROI)
        if box is not None:
            _click_box(hwnd, box, after_sleep=1)
            return True
        if page < 5:
            on_log(f"目标账号不在当前可见列表，滚轮翻页（{page + 1}/5）")
            _scroll_list(hwnd)
    return False


def _select_and_enter(hwnd: int, account: str, on_log: Callable[[str], None]) -> None:
    """下拉列表选号 → 点「进入游戏」→ 等待登录完成。"""
    pattern = _mask_pattern(account)
    if pattern is None:
        raise RuntimeError(
            f"账号 {mask_account(account)} 无法按登录界面掩码匹配"
            "（第三方登录账号），请改用填密码的账号+密码方式"
        )
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        _activate_window(hwnd)
        time.sleep(1)
        _expand_account_list(hwnd, on_log)
        time.sleep(0.5)
        if _click_target_account(hwnd, pattern, on_log):
            time.sleep(1)
            if _detect_field_account(hwnd, pattern):
                on_log(f"已选中目标账号 {mask_account(account)}")
                break
        if attempt < max_retries:
            on_log(f"账号选择结果未确认，重试（{attempt}/{max_retries}）")
            time.sleep(1)
        else:
            raise RuntimeError(
                "下拉列表选号失败：登录记录中未确认到目标账号，已重试 3 次；"
                "请确认该账号已在本机登录过（有登录记录），或改用填密码方式"
            )
    enter = _find_text(_read_texts(hwnd), ("进入游戏",))
    if enter is not None:
        _click_box(hwnd, enter, after_sleep=3)
    else:
        # 兜底锚定「登录其他账号」链接（对话框内稳定文本），面板漂移时比固定点可靠
        other = _find_text(_read_texts(hwnd), _LOGIN_DIALOG_TEXTS)
        if other is not None:
            on_log("未识别到「进入游戏」按钮文本，按「登录其他账号」相对位置兜底点击")
            _click_point(
                hwnd,
                _LOGIN_ENTER_POINT[0],
                other[1] + other[3] // 2 - _LOGIN_ENTER_Y_OFFSET_FROM_OTHER,
                after_sleep=3,
            )
        else:
            on_log("未识别到「进入游戏」按钮文本，按对话框固定位置兜底点击")
            _click_point(hwnd, *_LOGIN_ENTER_POINT, after_sleep=3)
    _wait_login_success(hwnd, on_log)


# ── 有密码版：登录其他账号 + 剪贴板输入账密 ─────────────────────────────


def _input_credentials(
    hwnd: int, account: str, password: str, on_log: Callable[[str], None]
) -> None:
    """账密表单输入账号与密码（剪贴板粘贴，参照一条龙 EnterGame 流程）。

    输入框优先按占位符 OCR 定位（「输入手机号/邮箱」「输入密码」）；一个
    占位符识别失败时按另一个的 y 推算（表单纵向间距固定），两个都失败才
    回退实机截图标定的固定点。
    """
    on_log(f"正在输入账号 {mask_account(account)}")
    items = _read_texts(hwnd)
    account_field = _find_text(items, ("输入手机号", "输入邮箱", "输入账号"))
    password_field = _find_text(items, ("输入密码",))
    if account_field is not None:
        _click_box(hwnd, account_field, after_sleep=0.5)
    elif password_field is not None:
        _click_point(
            hwnd,
            _FORM_ACCOUNT_POINT[0],
            password_field[1] + password_field[3] // 2 - _FORM_FIELD_Y_GAP,
            after_sleep=0.5,
        )
    else:
        _click_point(hwnd, *_FORM_ACCOUNT_POINT, after_sleep=0.5)
    _clipboard_copy_and_paste(account)

    time.sleep(1)
    on_log("正在输入密码")
    items = _read_texts(hwnd)
    password_field = _find_text(items, ("输入密码",))
    account_field = _find_text(items, ("输入手机号", "输入邮箱", "输入账号"))
    if password_field is not None:
        _click_box(hwnd, password_field, after_sleep=0.5)
    elif account_field is not None:
        _click_point(
            hwnd,
            _FORM_PASSWORD_POINT[0],
            account_field[1] + account_field[3] // 2 + _FORM_FIELD_Y_GAP,
            after_sleep=0.5,
        )
    else:
        _click_point(hwnd, *_FORM_PASSWORD_POINT, after_sleep=0.5)
    _clipboard_copy_and_paste(password)

    # 勾选《用户协议》和《隐私政策》：勾选圆点在「同意」文本左侧且命中框小
    # （用户实测点偏会误触《用户协议》链接、打开隐私政策文档页）——按候选偏移
    # 逐个点击并用橙色填充验证，命中即停，避免盲点
    time.sleep(1)
    on_log("正在勾选《用户协议》和《隐私政策》")
    agree = _find_text(_read_texts(hwnd), ("同意",))
    if agree is None:
        on_log("未识别到协议勾选文本，跳过勾选直接登录（若打开隐私文档页将失败）")
        return
    frame = _capture_window(hwnd, activate=False)
    for offset in (25, 35, 15):
        point = (max(agree[0] - offset, 0), agree[1] + agree[3] // 2)
        if _check_is_marked(frame, point):
            on_log("协议已处于勾选状态，跳过点击")
            return
        _click_point(hwnd, *point, after_sleep=0.5)
        frame = _capture_window(hwnd, activate=False)
        if _check_is_marked(frame, point):
            on_log("协议勾选成功")
            return
    on_log("协议勾选未确认（圆点过小），继续点击「进入游戏」")


def _select_other_account_entry(hwnd: int, on_log: Callable[[str], None]) -> None:
    """从登录对话框进入账密表单：点「登录其他账号」；已在该表单则直接返回。"""
    if _on_password_form(hwnd):
        on_log("已处于账密登录表单")
        return
    other = _wait_ocr_text(hwnd, _LOGIN_DIALOG_TEXTS, timeout=10)
    if other is None:
        raise RuntimeError("未找到「登录其他账号」入口，请人工确认登录界面状态")
    _click_box(hwnd, other, after_sleep=2)
    if not _on_password_form(hwnd):
        raise RuntimeError("点击「登录其他账号」后账密表单未出现，请人工确认")
    on_log("账密登录表单已打开")


def _enter_with_password(
    hwnd: int, account: str, password: str, on_log: Callable[[str], None]
) -> None:
    """账密表单登录 → 直接点「进入游戏」→ 等待登录完成。

    不点协议勾选框（勾选圆点过小、点偏有误触《用户协议》链接的风险）：
    协议未勾选时点「进入游戏」会弹「是否同意」确认框，由登录等待循环统一
    点「同意」继续——对下拉选号版同样生效，作为二重保障。
    """
    _input_credentials(hwnd, account, password, on_log)
    on_log("正在点击「进入游戏」登录")
    items = _read_texts(hwnd)
    enter = _find_text(items, ("进入游戏",))
    if enter is not None:
        _click_box(hwnd, enter, after_sleep=3)
    else:
        # 兜底优先锚定已识别的表单元素（密码/账号占位符），面板漂移时比固定点可靠
        password_field = _find_text(items, ("输入密码",))
        account_field = _find_text(items, ("输入手机号", "输入邮箱", "输入账号"))
        if password_field is not None:
            on_log("未识别到「进入游戏」按钮文本，按密码框相对位置兜底点击")
            _click_point(
                hwnd,
                _FORM_ENTER_POINT[0],
                password_field[1] + password_field[3] // 2
                + _FORM_ENTER_Y_OFFSET_FROM_PASSWORD,
                after_sleep=3,
            )
        elif account_field is not None:
            on_log("未识别到「进入游戏」按钮文本，按账号框相对位置兜底点击")
            _click_point(
                hwnd,
                _FORM_ENTER_POINT[0],
                account_field[1] + account_field[3] // 2
                + _FORM_ENTER_Y_OFFSET_FROM_ACCOUNT,
                after_sleep=3,
            )
        else:
            on_log("未识别到「进入游戏」按钮文本，按表单固定位置兜底点击")
            _click_point(hwnd, *_FORM_ENTER_POINT, after_sleep=3)
    _wait_login_success(hwnd, on_log)


# ── 登录完成等待 ────────────────────────────────────────────────────────


def _wait_login_success(
    hwnd: int, on_log: Callable[[str], None], *, timeout: int = 180
) -> None:
    """点击「进入游戏」后等待登录界面消失（登录成功进入加载/游戏内）。

    等待期间处理两类中途弹窗：

    - 协议确认框（「同意/不同意」）：点「同意」继续登录——协议未勾选时点
      「进入游戏」必弹，点完即登录，是两版流程共用的最后一步兜底；
    - 「验证」类文本：提前失败，滑块/扫码验证 MAS 无法自动完成，继续等待
      只会白耗超时预算并误导排查方向。
    """
    deadline = time.monotonic() + timeout
    absent_count = 0
    while time.monotonic() < deadline:
        items = _read_texts(hwnd)
        if _find_text(items, ("验证", "扫码")) is not None:
            raise RuntimeError(
                "登录出现安全验证（滑块/扫码等），MAS 无法自动完成；"
                "请手动完成验证后重试，或改用无密码的下拉列表方式"
            )
        # 协议勾选失效时点「进入游戏」会打开隐私政策文档页（整页文档而非确认
        # 弹窗），继续等待只会白耗超时——明确失败
        if _find_text(items, ("米哈游用户个人信息及隐私保护政策",)) is not None:
            raise RuntimeError(
                "登录跳转到了隐私政策文档页（协议勾选未生效），请重试；"
                "若反复出现请手动登录一次该账号"
            )
        # 协议确认框：按钮文本恰为「同意」（精确匹配并取最右，排除左侧
        # 「不同意」，防 OCR 丢字误点）
        agrees = [b for t, b in items if t == "同意"]
        agree = max(agrees, key=lambda b: b[0] + b[2]) if agrees else None
        if agree is not None:
            on_log("检测到协议确认弹窗，点击「同意」继续登录")
            _click_box(hwnd, agree, after_sleep=2)
            absent_count = 0
            continue
        on_login_ui = (
            _find_text(items, _LOGIN_DIALOG_TEXTS) is not None
            or _find_text(items, _PASSWORD_FORM_TEXTS) is not None
        )
        if not on_login_ui:
            absent_count += 1
            if absent_count >= 2:
                on_log("登录界面已消失，登录成功")
                return
        else:
            absent_count = 0
        time.sleep(1)
    raise RuntimeError("等待登录完成超时（登录界面未消失），可能账密有误或网络异常")


# ── B服（bilibili 渠服）：登录记录面板按昵称选号 ────────────────────────
# B服暂不支持账密登录（验证码无法自动完成），仅有下拉选号一版；目标账号按
# B站昵称匹配（用户在 MAS「账户」字段填写B站用户名）。


def _mask_nickname(nickname: str) -> str:
    """B站昵称打码（诊断/日志展示用）：前 2 + * + 后 1，过短原样。"""
    if len(nickname) <= 3:
        return nickname
    return f"{nickname[:2]}{'*' * (len(nickname) - 3)}{nickname[-1:]}"


def _nickname_match_ratio(text: str, nickname: str) -> float:
    """B站昵称与 OCR 文本的相似度（LCS 比例，对齐一条龙 find_by_lcs 口径）。"""
    if not text or not nickname:
        return 0.0
    if nickname in text:
        return 1.0
    return SequenceMatcher(None, text, nickname, autojunk=False).ratio()


def _on_bili_panel(hwnd: int) -> bool:
    """B服登录记录面板是否已打开（面板标题「登录记录」）。"""
    return _find_text(_read_texts(hwnd), _BILI_PANEL_TEXTS) is not None


def _click_bili_agree(hwnd: int, on_log: Callable[[str], None]) -> None:
    """隐私政策弹窗点「同意」。

    按钮文本恰为「同意」；正文含「已知悉并同意」「不同意」等干扰，只认精确
    命中并取最右（同意按钮在「不同意」右侧，防 OCR 把「不同意」丢字误读成
    「同意」），OCR 失败回退实机截图标定的按钮固定点。
    """
    on_log("检测到隐私政策提示，点击「同意」")
    agrees = [b for t, b in _read_texts(hwnd) if t == "同意"]
    agree = max(agrees, key=lambda b: b[0] + b[2]) if agrees else None
    if agree is not None:
        _click_box(hwnd, agree, after_sleep=2)
    else:
        on_log("未识别到「同意」按钮文本，按弹窗相对位置兜底点击")
        _click_point(hwnd, *_BILI_AGREE_POINT, after_sleep=2)
    if _wait_ocr_text(hwnd, _BILI_PANEL_TEXTS, timeout=30) is None:
        raise RuntimeError("同意隐私政策后登录记录面板未打开（30s 未识别到面板）")
    on_log("登录记录面板已打开")


def _open_bili_panel_from_title(hwnd: int, on_log: Callable[[str], None]) -> None:
    """标题界面 → 点右下角切换账号图标 → 「确认切换账号?」点「确定」→ 面板。

    图标点击是双入口：已登录（有会话）时弹「确认切换账号?」确认框，未登录
    时直接打开登录记录面板，按点击后画面分流。
    """
    for attempt in range(1, 4):
        on_log(f"正在点击标题界面右下角切换账号图标（{attempt}/3）")
        _click_point(hwnd, *_BILI_SWITCH_ICON_POINT, after_sleep=1.5)
        deadline = time.monotonic() + 20
        confirmed = False
        while time.monotonic() < deadline:
            items = _read_texts(hwnd)
            if _find_text(items, _BILI_PANEL_TEXTS) is not None:
                on_log("登录记录面板已打开")
                return
            if not confirmed:
                confirms = [b for t, b in items if t == "确定"]
                confirm = (
                    max(confirms, key=lambda b: b[0] + b[2]) if confirms else None
                )
                if confirm is not None:
                    on_log("检测到「确认切换账号」弹窗，点击「确定」")
                    _click_box(hwnd, confirm, after_sleep=2)
                    confirmed = True
                    continue
            time.sleep(1)
        on_log("登录记录面板未打开，重试点击切换账号图标")
    raise RuntimeError(
        "点击切换账号图标后登录记录面板未打开（已重试 3 次），请人工确认当前处于标题界面"
    )


def _bili_card_row_y(hwnd: int) -> int | None:
    """当前账号卡片锚行（最顶部的「上次登录」标记）的 y 中心；找不到返回 None。

    面板纵向位置会漂移（2026-09-23 实机 ±70px），面板内元素的点击/排除一律
    以本锚行相对定位，不用固定坐标。
    """
    marks = [b for t, b in _read_texts(hwnd) if _BILI_RECORD_MARK in t]
    if not marks:
        return None
    top = min(marks, key=lambda box: box[1])
    return top[1] + top[3] // 2


def _find_bili_account(
    hwnd: int, nickname: str, *, exclude_y: int | None = None
) -> Box | None:
    """在当前画面找与目标B站昵称最相似的文本框（LCS ≥ 阈值，取最高分）。

    Args:
        nickname: 目标B站用户名（用户在 MAS「账户」字段填写）。
        exclude_y: 传入时跳过中心 y 落在 ``exclude_y ± 窗口`` 内的命中——
            列表展开后当前账号卡片同样显示昵称且在列表上方，误点卡片会把
            列表收起而不是选中目标账号。
    """
    best: tuple[float, Box] | None = None
    for text, box in _read_texts(hwnd):
        if exclude_y is not None:
            center_y = box[1] + box[3] // 2
            if abs(center_y - exclude_y) <= _BILI_CARD_ROW_WINDOW:
                continue
        ratio = _nickname_match_ratio(text, nickname)
        if ratio >= _BILI_NICKNAME_THRESHOLD and (best is None or ratio > best[0]):
            best = (ratio, box)
    return best[1] if best else None


def _expand_bili_list(hwnd: int, on_log: Callable[[str], None]) -> None:
    """点当前账号卡片行右侧的展开箭头直至登录记录列表展开（≥2 条记录）。

    每条登录记录（含输入卡片）都带「上次登录」时间戳，出现 ≥2 条即列表已
    展开。箭头命中框很小且必须精确命中（点卡片其他区域无效），面板纵向又
    会漂移——以锚行校准点为中心铺 ±12/±10px 候选网格逐个尝试，每次点击后
    立即验证展开状态（点击是翻转开关，盲点会把展开的列表再点收起）。
    """
    for _ in range(3):
        marks = [b for t, b in _read_texts(hwnd) if _BILI_RECORD_MARK in t]
        if len(marks) >= 2:
            return
        if marks:
            top = min(marks, key=lambda box: box[1])
            base_y = top[1] + top[3] // 2 + _BILI_ARROW_Y_OFFSET_FROM_CARD
            candidates = (
                (_BILI_ARROW_X, base_y),
                (_BILI_ARROW_X, base_y + 10),
                (_BILI_ARROW_X, base_y - 10),
                (_BILI_ARROW_X - 12, base_y),
                (_BILI_ARROW_X + 12, base_y),
            )
        else:
            # 无锚行（面板结构异常）：按参考面板位置盲点，点后同样验证
            candidates = (
                (_BILI_ARROW_X, 476),
                (_BILI_ARROW_X, 486),
                (_BILI_ARROW_X, 466),
            )
        for point in candidates:
            on_log(f"点击账号卡片展开箭头 {point}")
            _click_point(hwnd, *point, after_sleep=1)
            if (
                len([b for t, b in _read_texts(hwnd) if _BILI_RECORD_MARK in t])
                >= 2
            ):
                return
    raise RuntimeError(
        "无法展开B服登录记录列表（展开箭头候选点全部未命中），"
        "请人工确认面板状态；诊断文件与错误截图见 debug/bgi-account-switch/"
    )


def _select_bili_account(
    hwnd: int, nickname: str, on_log: Callable[[str], None]
) -> None:
    """展开登录记录列表 → 按昵称匹配点选目标 → 回读卡片确认（重试 3 次）。"""
    masked = _mask_nickname(nickname)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        _activate_window(hwnd)
        time.sleep(1)
        _expand_bili_list(hwnd, on_log)
        time.sleep(0.5)
        card_row_y = _bili_card_row_y(hwnd)
        for page in range(6):
            box = _find_bili_account(hwnd, nickname, exclude_y=card_row_y)
            if box is not None:
                _click_box(hwnd, box, after_sleep=1)
                time.sleep(1)
                # 回读当前账号卡片行确认已选中目标（列表收起后卡片显示目标昵称）
                confirmed = any(
                    _nickname_match_ratio(t, nickname) >= _BILI_NICKNAME_THRESHOLD
                    and abs(t_box[1] + t_box[3] // 2 - card_row_y)
                    <= _BILI_CARD_ROW_WINDOW
                    for t, t_box in _read_texts(hwnd)
                    if card_row_y is not None
                )
                if confirmed:
                    on_log(f"已选中B服账号 {masked}")
                    return
                break
            if page < 5:
                on_log(f"目标账号不在当前可见列表，滚轮翻页（{page + 1}/5）")
                _scroll_list(hwnd, _BILI_LIST_SCROLL_POINT)
        if attempt < max_retries:
            on_log(f"B服账号选择结果未确认，重试（{attempt}/{max_retries}）")
        else:
            raise RuntimeError(
                f"未能在登录记录中选中B服账号 {masked}（已重试 3 次）；"
                "请确认该账号已在本机登录过（登录记录面板可见），"
                "且「账户」字段填写的用户名与面板显示的昵称一致"
            )


def _click_bili_login(hwnd: int, on_log: Callable[[str], None]) -> None:
    """点面板「登录」按钮（按钮文本恰为「登录」，OCR 失败回退锚行相对位置）。"""
    on_log("正在点击「登录」")
    logins = [b for t, b in _read_texts(hwnd) if t == "登录"]
    login = max(logins, key=lambda b: b[0] + b[2]) if logins else None
    if login is not None:
        _click_box(hwnd, login, after_sleep=3)
        return
    on_log("未识别到「登录」按钮文本，按卡片锚行相对位置兜底点击")
    card_row_y = _bili_card_row_y(hwnd)
    point = (
        (_BILI_LOGIN_POINT[0], card_row_y + _BILI_LOGIN_Y_OFFSET_FROM_CARD)
        if card_row_y is not None
        else _BILI_LOGIN_POINT
    )
    _click_point(hwnd, *point, after_sleep=3)


def _wait_bili_panel_closed(hwnd: int, on_log: Callable[[str], None]) -> None:
    """点击「登录」后先等登录记录面板关闭（登录已受理），再等标题重现。

    面板不关闭说明登录未生效，必须响亮失败而非继续等待：后续标题等待的
    派蒙退出兜底会按 ESC 把面板关掉、让标题「点击进入」出现，把「没切成」
    误判成「切换完成」（对齐官服 _wait_login_success 的登录界面消失门控）。
    等待期间出现「验证/扫码」立即明确失败（滑块/扫码 MAS 无法自动完成）。
    纯轮询、无 ESC/确认点击等副作用，不会自行把面板关掉掩蔽失败。
    """
    deadline = time.monotonic() + _BILI_LOGIN_EFFECT_TIMEOUT
    absent_count = 0
    while time.monotonic() < deadline:
        items = _read_texts(hwnd)
        if _find_text(items, ("验证", "扫码")) is not None:
            raise RuntimeError(
                "登录出现安全验证（滑块/扫码等），MAS 无法自动完成；"
                "请手动完成验证后重试"
            )
        if _find_text(items, _BILI_PANEL_TEXTS) is None:
            absent_count += 1
            if absent_count >= 2:
                return
        else:
            absent_count = 0
        time.sleep(1)
    raise RuntimeError(
        "点击登录后登录记录面板未关闭（登录可能未生效），请人工确认后重试"
    )


def _switch_account_bili(
    hwnd: int, nickname: str, on_log: Callable[[str], None]
) -> None:
    """B服切号主流程：进面板 → 按昵称选号 → 登录 → 等「点击进入」重现。

    与官服的差异：入口是标题右下角切换账号图标（确认弹窗点「确定」）；无登录
    会话时先弹隐私政策（点「同意」）；完成信号是标题「点击进入」重新出现
    （B服登录后回到标题而非直接进游戏），且点「登录」后必须先确认面板已
    关闭（登录已受理）再等标题，防止登录未生效被误判为完成。
    """
    masked = _mask_nickname(nickname)
    hwnd = _wait_until_state(
        hwnd, on_log, (_TITLE_TEXTS, _BILI_PRIVACY_TEXTS, _BILI_PANEL_TEXTS)
    )
    if _find_text(_read_texts(hwnd), _BILI_PRIVACY_TEXTS) is not None:
        _click_bili_agree(hwnd, on_log)
    if not _on_bili_panel(hwnd):
        _open_bili_panel_from_title(hwnd, on_log)
    _select_bili_account(hwnd, nickname, on_log)
    _click_bili_login(hwnd, on_log)
    on_log("已点击登录，等待登录记录面板关闭")
    _wait_bili_panel_closed(hwnd, on_log)
    on_log("登录已受理，等待回到标题界面")
    _wait_until_state(hwnd, on_log, (_TITLE_TEXTS,))
    on_log(f"B服账号切换完成：{masked}")


def _save_error_screenshot(hwnd: int) -> None:
    """保存切换失败时的原始窗口截图，便于排查 OCR 文本漂移。"""
    try:
        screenshot_dir = Path.cwd() / "debug" / "bgi-account-switch"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / (
            f"switch-error-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
        )
        _capture_window_image(hwnd, activate=False).save(screenshot_path, format="PNG")
        logger.warning(f"账号切换错误截图已保存: {screenshot_path}")
    except Exception as error:
        # 截图是诊断旁路，失败时不能覆盖原始切换异常
        logger.warning(f"账号切换错误截图保存失败: {error}")


# ── 对外入口 ─────────────────────────────────────────────────────────────


def account_switch(
    account: str,
    password: str = "",
    *,
    resource: str = "官服",
    on_log: Callable[[str], None] | None = None,
) -> bool:
    """强制切换原神登录账号（按服务器分流官服/B服流程）。

    Args:
        account: 目标账号。官服为手机号/邮箱（未填密码时按登录界面掩码匹配
            选号，要求该账号已在本机登录过）；B服为B站用户名（按登录记录
            面板显示的昵称匹配选号）。
        password: 账号密码；官服非空时走「登录其他账号 + 剪贴板输入账密」
            版本。B服暂不支持账密登录（验证码无法自动完成），填了也忽略。
        resource: 目标服务器（用户配置 Switch.Resource），决定走哪套登录 UI。
        on_log: 流程进度回调（供 MAS 推送调度台日志），默认仅写日志。

    Returns:
        切换成功返回 True；失败抛出带原因描述的 RuntimeError。

    Raises:
        RuntimeError: 未找到游戏窗口 / 界面状态不符 / 选号或登录失败 / 超时。
    """
    on_log = on_log or (lambda msg: logger.info(msg))
    if not IS_WINDOWS:
        raise RuntimeError("BetterGI 账号切换仅支持 Windows 平台")
    account = str(account or "").strip()
    password = str(password or "")
    resource = (str(resource or "官服").strip() or "官服")
    if not account:
        raise RuntimeError("未配置账号，无法切换")
    is_bili = resource == "B服"
    if is_bili and password:
        # 密码在 B服无可用通道（登录必触发验证码），显式告知避免用户误以为生效
        on_log("B服暂不支持账密登录（验证码无法自动完成），忽略密码，按B站用户名匹配选号")
    use_password = bool(password) and not is_bili
    if is_bili:
        mode_label = "B服·用户名匹配"
    else:
        mode_label = "账号+密码" if use_password else "下拉列表"

    # 开启诊断记录：进度日志与各步骤 OCR 文本写入 debug/bgi-account-switch/，
    # 供登录失败时用户反馈定位（文件随时间戳命名，一次切换一个文件）
    global _DIAGNOSTIC_PATH
    diagnostic_dir = Path.cwd() / "debug" / "bgi-account-switch"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    _DIAGNOSTIC_PATH = diagnostic_dir / (
        f"switch-detail-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    )

    def _on_log(msg: str) -> None:
        _write_diagnostic(f"[{datetime.now():%H:%M:%S}] {msg}\n")
        on_log(msg)

    display = _mask_nickname(account) if is_bili else mask_account(account)
    _on_log(f"开始切换原神账号（{mode_label}）：{display}")

    # 互斥：并发切换会双线程抢占同一游戏窗口（僵尸线程 + 新流程互相踩踏），
    # 抢不到锁直接响亮失败
    if not _SWITCH_LOCK.acquire(blocking=False):
        raise RuntimeError(
            "上一个账号切换流程仍在执行中（可能因画面卡住而未退出），"
            "请重启任务后再试"
        )
    try:
        # 屏保运行时截图全黑会导致 OCR 全盲，开工前先轻推鼠标退出（对齐 OK-NTE）
        _dismiss_screensaver()
        try:
            hwnd = _find_game_hwnd()
            _activate_window(hwnd)
            if is_bili:
                _switch_account_bili(hwnd, account, _on_log)
            else:
                # 启动稳定化：等界面进入「标题 / 登录对话框 / 账密表单」之一再分流，
                # 滞留游戏内时自动经派蒙菜单退出到标题（多用户循环的常见起点）；
                # 等待期间窗口失效重定位后的新句柄经返回值带回，后续流程不再用死句柄
                hwnd = _wait_for_actionable_state(hwnd, _on_log)
                if not (_on_login_dialog(hwnd) or _on_password_form(hwnd)):
                    _open_login_dialog(hwnd, _on_log)
                if use_password:
                    _select_other_account_entry(hwnd, _on_log)
                    _enter_with_password(hwnd, account, password, _on_log)
                else:
                    _select_and_enter(hwnd, account, _on_log)
        except Exception:
            try:
                # wait=False：主流程已等待过窗口，此处单次枚举即可，避免失败后再空等宽限期。
                _save_error_screenshot(_find_game_hwnd(wait=False))
            except Exception:
                pass
            raise
    finally:
        _SWITCH_LOCK.release()
        _DIAGNOSTIC_PATH = None
    logger.success(f"原神账号切换成功：{display}")
    return True


def _dismiss_screensaver() -> None:
    """屏保运行时轻推鼠标将其退出（旁路：失败仅记日志，不阻断切号流程）。"""
    if not IS_WINDOWS:
        return
    _SPI_GETSCREENSAVERRUNNING = 0x0072
    running = ctypes.c_int(0)
    if not ctypes.windll.user32.SystemParametersInfoW(
        _SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(running), 0
    ):
        return
    if not running.value:
        return
    logger.info("检测到屏幕保护程序正在运行，轻推鼠标退出...")
    try:
        x, y = pyautogui.position()
        deadline = time.monotonic() + 10
        offset = 50
        while time.monotonic() < deadline:
            running = ctypes.c_int(0)
            if not ctypes.windll.user32.SystemParametersInfoW(
                _SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(running), 0
            ) or not running.value:
                break
            pyautogui.moveTo(x + offset, y)
            offset = -offset
            time.sleep(1)
        pyautogui.moveTo(x, y)
    except Exception as error:
        logger.warning(f"退出屏幕保护程序失败（忽略，继续切号流程）: {error}")


async def async_switch_account(
    account: str,
    password: str = "",
    *,
    resource: str = "官服",
    on_log: Callable[[str], None] | None = None,
) -> bool:
    """async 版本：在后台线程执行完整切换流程，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        account_switch, account, password, resource=resource, on_log=on_log
    )
