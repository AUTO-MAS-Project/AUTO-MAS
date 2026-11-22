#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""扫桌面上的 Win32 窗口（运行一侧）：给 ``match_controller_windows`` 的 ``list_windows``。

原样搬自 ``controller_win32/service.py`` 的 ``MaaFWWin32ControllerService.list_windows`` 与
``_normalize_hwnd``：扫描要 MaaFramework 绑定（``maa.toolkit``），解析库只依赖 pydantic、json5，
所以扫描留在运行一侧，由调用方把这个函数交给解析库。只依赖解析库与 ``maa.toolkit``（用到时才导入），
桌面分身进程也直接用它。
"""

from __future__ import annotations

import sys
from typing import Any

from app.task.MaaFW.blocks.maafw_interface.controller_win32.service import (
    MaaFWWin32Window,
)


def list_maafw_desktop_windows() -> list[MaaFWWin32Window]:
    if sys.platform != "win32":
        raise RuntimeError("Win32 窗口扫描仅支持 Windows")

    from maa.toolkit import Toolkit

    return [
        MaaFWWin32Window(
            hWnd=_normalize_hwnd(window.hwnd),
            className=str(window.class_name or ""),
            windowName=str(window.window_name or ""),
        )
        for window in Toolkit.find_desktop_windows()
    ]


def _normalize_hwnd(value: Any) -> int:
    if hasattr(value, "value"):
        value = value.value
    if value is None:
        return 0
    return int(value)


__all__ = ["list_maafw_desktop_windows"]
