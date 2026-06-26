#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from maa.toolkit import Toolkit

from .interface_models import MaaFWController


@dataclass(frozen=True)
class MaaFWDesktopWindow:
    hWnd: int
    className: str
    windowName: str


@dataclass(frozen=True)
class MaaFWWindowMatch(MaaFWDesktopWindow):
    controllerName: str
    controllerType: str


def list_desktop_windows() -> list[MaaFWDesktopWindow]:
    """Return MaaFW Toolkit desktop windows with stable Python-native fields."""

    if sys.platform != "win32":
        raise RuntimeError("Win32/Gamepad 窗口扫描仅支持 Windows")

    return [
        MaaFWDesktopWindow(
            hWnd=_normalize_hwnd(window.hwnd),
            className=str(window.class_name or ""),
            windowName=str(window.window_name or ""),
        )
        for window in Toolkit.find_desktop_windows()
    ]


def match_controller_windows(
    controller: MaaFWController,
    windows: Iterable[MaaFWDesktopWindow] | None = None,
) -> list[MaaFWWindowMatch]:
    """Find windows matched by a Win32/Gamepad controller definition."""

    if controller.type not in {"Win32", "Gamepad"}:
        return []

    class_regex, window_regex = _controller_window_regex(controller)
    source_windows = list(windows) if windows is not None else list_desktop_windows()
    matched: list[MaaFWWindowMatch] = []
    seen_hwnds: set[int] = set()

    for window in source_windows:
        if window.hWnd in seen_hwnds:
            continue
        if not _matches_regex(class_regex, window.className):
            continue
        if not _matches_regex(window_regex, window.windowName):
            continue

        seen_hwnds.add(window.hWnd)
        matched.append(
            MaaFWWindowMatch(
                hWnd=window.hWnd,
                className=window.className,
                windowName=window.windowName,
                controllerName=controller.name,
                controllerType=controller.type,
            )
        )

    return matched


def resolve_window_handle(
    controller: MaaFWController,
    configured_hwnd: Any,
    *,
    send_log: Callable[[str], None] | None = None,
) -> int:
    """Use explicit hWnd first, otherwise scan the desktop by interface regex."""

    logger = send_log or (lambda _: None)
    explicit_hwnd = _optional_hwnd(configured_hwnd)
    if explicit_hwnd:
        logger(f"使用已配置窗口句柄: {explicit_hwnd}")
        return explicit_hwnd

    matches = match_controller_windows(controller)
    if not matches:
        class_regex, window_regex = _controller_window_regex(controller)
        raise RuntimeError(
            "未找到匹配的 PC 客户端窗口，请先启动游戏客户端，或在用户/脚本配置中填写窗口句柄。"
            f" class_regex={class_regex or '*'}, window_regex={window_regex or '*'}"
        )

    selected = matches[0]
    logger(
        "已自动匹配 PC 客户端窗口: "
        f"hWnd={selected.hWnd}, class={selected.className}, title={selected.windowName}"
    )
    if len(matches) > 1:
        logger(f"检测到 {len(matches)} 个匹配窗口，已使用第一个；需要指定时可在用户配置中填写窗口句柄")
    return selected.hWnd


def _controller_window_regex(controller: MaaFWController) -> tuple[str | None, str | None]:
    if controller.type == "Win32" and controller.win32 is not None:
        return controller.win32.class_regex, controller.win32.window_regex
    if controller.type == "Gamepad" and controller.gamepad is not None:
        return controller.gamepad.class_regex, controller.gamepad.window_regex
    return None, None


def _matches_regex(pattern: str | None, value: str) -> bool:
    if not pattern:
        return True
    try:
        return re.search(pattern, value) is not None
    except re.error as exc:
        raise RuntimeError(f"interface 窗口匹配正则无效: {pattern}") from exc


def _normalize_hwnd(value: Any) -> int:
    if hasattr(value, "value"):
        value = value.value
    if value is None:
        return 0
    return int(value)


def _optional_hwnd(value: Any) -> int | None:
    try:
        parsed = _normalize_hwnd(value)
    except (TypeError, ValueError):
        return None
    return parsed or None
