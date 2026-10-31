"""独立功能统一入口：按功能选择平台实现，并缓存模块。"""

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .common import community as community
    from .common import error_screenshot as error_screenshot
    from .common import game_calendar as game_calendar
    from .common import ocr as ocr

_COMMON_MODULES = {
    "community": ".common.community",
    "error_screenshot": ".common.error_screenshot",
    "game_calendar": ".common.game_calendar",
    "ocr": ".common.ocr",
}
_PLATFORM_MODULES: dict[str, dict[str, str]] = {"win32": {}, "darwin": {}, "linux": {}}


def __getattr__(name: str):
    module_name = _PLATFORM_MODULES.get(sys.platform, {}).get(
        name
    ) or _COMMON_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = import_module(module_name, __name__)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = ["community", "error_screenshot", "game_calendar", "ocr"]
