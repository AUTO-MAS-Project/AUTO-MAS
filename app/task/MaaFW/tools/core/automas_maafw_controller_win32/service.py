from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWController

MAX_REGEX_PATTERN_LENGTH = 256
MAX_REGEX_VALUE_LENGTH = 4096
DANGEROUS_NESTED_QUANTIFIER_RE = re.compile(
    r"\([^)]*(?:[*+]|\{\d+(?:,\d*)?\})[^)]*\)(?:[*+]|\{\d+(?:,\d*)?\})"
)


@dataclass(frozen=True)
class MaaFWWin32Window:
    hWnd: int
    className: str
    windowName: str


@dataclass(frozen=True)
class MaaFWWindowMatch(MaaFWWin32Window):
    controllerName: str
    controllerType: str


class MaaFWWin32ControllerService:
    """maafw.controller.win32 service."""

    key = "win32"
    display_name = "Win32"
    controller_types = ["Win32"]

    def get_provider_definition(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "displayName": self.display_name,
            "controllerTypes": list(self.controller_types),
            "capabilities": ["window_scan", "device_spec"],
        }

    def list_windows(self) -> list[MaaFWWin32Window]:
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

    def match_controller_windows(
        self,
        controller: BaseModel | dict[str, Any],
        windows: Iterable[MaaFWWin32Window] | None = None,
    ) -> list[MaaFWWindowMatch]:
        if isinstance(controller, MaaFWController):
            controller_model = controller
        else:
            controller_payload = (
                controller.model_dump(mode="json", by_alias=True)
                if hasattr(controller, "model_dump")
                else controller
            )
            controller_model = MaaFWController.model_validate(controller_payload)
        if controller_model.type != "Win32":
            return []

        class_regex, window_regex = _controller_window_regex(controller_model)
        source_windows = list(windows) if windows is not None else self.list_windows()
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
                    controllerName=controller_model.name,
                    controllerType=controller_model.type,
                )
            )

        return matched

    def build_device_spec(
        self,
        *,
        h_wnd: int | None = None,
        screencap_method: int = 0,
        mouse_method: int = 0,
        keyboard_method: int = 0,
    ) -> dict[str, Any]:
        return {
            "type": "Win32",
            "hWnd": h_wnd,
            "screencapMethod": screencap_method,
            "mouseMethod": mouse_method,
            "keyboardMethod": keyboard_method,
        }


def _controller_window_regex(
    controller: MaaFWController,
) -> tuple[str | None, str | None]:
    if controller.type == "Win32" and controller.win32 is not None:
        return controller.win32.class_regex, controller.win32.window_regex
    return None, None


def _matches_regex(pattern: str | None, value: str) -> bool:
    if not pattern:
        return True
    try:
        compiled_pattern = _compile_safe_regex(pattern)
        return compiled_pattern.search(value[:MAX_REGEX_VALUE_LENGTH]) is not None
    except re.error as exc:
        raise RuntimeError(f"interface 窗口匹配正则无效: {pattern}") from exc


def _compile_safe_regex(pattern: str) -> re.Pattern[str]:
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise RuntimeError("interface window regex is too long")
    if DANGEROUS_NESTED_QUANTIFIER_RE.search(pattern):
        raise RuntimeError("interface window regex contains nested quantifiers")
    return re.compile(pattern)


def _normalize_hwnd(value: Any) -> int:
    if hasattr(value, "value"):
        value = value.value
    if value is None:
        return 0
    return int(value)
