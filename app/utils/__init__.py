from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import app.utils.constants as constants
    from app.utils.ImageUtils import ImageUtils
    from app.utils.LogMonitor import LogMonitor, strptime
    from app.utils.ProcessManager import (
        ProcessInfo,
        ProcessManager,
        ProcessResult,
        ProcessRunner,
    )
    from app.utils.emulator import (
        EMULATOR_TYPE_BOOK,
        LDManager,
        MumuManager,
        search_all_emulators,
    )
    from app.utils.logger import get_logger
    from app.utils.security import (
        dpapi_decrypt,
        dpapi_encrypt,
        sanitize_log_message,
    )
    from app.utils.skland import skland_sign_in
    from app.utils.tools import busy_wait, decode_bytes
    from app.utils.websocket import WebSocketClient, create_ws_client


_EXPORTS: dict[str, tuple[str, str]] = {
    "constants": ("app.utils.constants", ""),
    "get_logger": ("app.utils.logger", "get_logger"),
    "ImageUtils": ("app.utils.ImageUtils", "ImageUtils"),
    "LogMonitor": ("app.utils.LogMonitor", "LogMonitor"),
    "strptime": ("app.utils.LogMonitor", "strptime"),
    "ProcessManager": ("app.utils.ProcessManager", "ProcessManager"),
    "ProcessRunner": ("app.utils.ProcessManager", "ProcessRunner"),
    "ProcessInfo": ("app.utils.ProcessManager", "ProcessInfo"),
    "ProcessResult": ("app.utils.ProcessManager", "ProcessResult"),
    "dpapi_encrypt": ("app.utils.security", "dpapi_encrypt"),
    "dpapi_decrypt": ("app.utils.security", "dpapi_decrypt"),
    "sanitize_log_message": ("app.utils.security", "sanitize_log_message"),
    "skland_sign_in": ("app.utils.skland", "skland_sign_in"),
    "MumuManager": ("app.utils.emulator", "MumuManager"),
    "LDManager": ("app.utils.emulator", "LDManager"),
    "search_all_emulators": ("app.utils.emulator", "search_all_emulators"),
    "EMULATOR_TYPE_BOOK": ("app.utils.emulator", "EMULATOR_TYPE_BOOK"),
    "decode_bytes": ("app.utils.tools", "decode_bytes"),
    "busy_wait": ("app.utils.tools", "busy_wait"),
    "WebSocketClient": ("app.utils.websocket", "WebSocketClient"),
    "create_ws_client": ("app.utils.websocket", "create_ws_client"),
}


__all__ = (
    "constants",
    "get_logger",
    "ImageUtils",
    "LogMonitor",
    "strptime",
    "ProcessManager",
    "ProcessRunner",
    "ProcessInfo",
    "ProcessResult",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "sanitize_log_message",
    "skland_sign_in",
    "MumuManager",
    "LDManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
    "decode_bytes",
    "busy_wait",
    "WebSocketClient",
    "create_ws_client",
)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = module if not attr_name else getattr(module, attr_name)
    globals()[name] = value
    return value
