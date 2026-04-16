from __future__ import annotations

from importlib import import_module
from typing import Any


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


__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = module if not attr_name else getattr(module, attr_name)
    globals()[name] = value
    return value
