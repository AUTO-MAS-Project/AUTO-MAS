"""再导出宿主 ``app.utils``（整包；运行时懒取，编写期可提示）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils import (
        ProcessInfo,
        ProcessManager,
        ProcessResult,
        ProcessRunner,
        WebSocketClient,
        busy_wait,
        create_ws_client,
        decode_bytes,
        dpapi_decrypt,
        dpapi_encrypt,
        get_logger,
        get_path_runtime_lock,
        is_process_running,
        read_file,
        sanitize_log_message,
        to_pep440,
        write_file,
    )

__all__ = [
    "ProcessInfo",
    "ProcessManager",
    "ProcessResult",
    "ProcessRunner",
    "WebSocketClient",
    "busy_wait",
    "create_ws_client",
    "decode_bytes",
    "dpapi_decrypt",
    "dpapi_encrypt",
    "get_logger",
    "get_path_runtime_lock",
    "get_setting",
    "is_process_running",
    "read_file",
    "sanitize_log_message",
    "to_pep440",
    "write_file",
]


def get_setting(group: str, name: str, default: Any = None) -> Any:
    """读 ``Config.setting.<group>.<name>``；键名支持 PascalCase 或 snake_case。"""
    from auto_mas_core import Config

    def snake(s: str) -> str:
        s = s.strip()
        if not s:
            return s
        s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()

    try:
        grp = getattr(Config.setting, snake(group), None)
        if grp is None:
            return default
        return getattr(grp, snake(name), default)
    except Exception:
        return default


def __getattr__(name: str) -> Any:
    if name == "EMULATOR_PATH_BOOK":
        from app.utils.constants import EMULATOR_PATH_BOOK

        return EMULATOR_PATH_BOOK
    import app.utils as host_utils

    if hasattr(host_utils, name):
        return getattr(host_utils, name)
    from importlib import import_module

    for mod_name in (
        "app.utils.io",
        "app.utils.constants",
        "app.utils.config_archive",
        "app.utils.config_restore",
        "app.utils.paths",
        "app.utils.platform.process",
        "app.utils.OCR.OCRtool",
        "app.utils.security",
    ):
        mod = import_module(mod_name)
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    import app.utils as host_utils

    return sorted(set(__all__) | {"EMULATOR_PATH_BOOK"} | set(dir(host_utils)))
