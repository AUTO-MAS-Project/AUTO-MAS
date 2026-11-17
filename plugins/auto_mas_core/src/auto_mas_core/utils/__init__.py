"""再导出宿主 ``app.utils``（整包；运行时懒取，编写期可提示）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils import *  # noqa: F403 - 与宿主公开工具保持同一份静态类型声明。
    from app.utils.common.constants import EMULATOR_PATH_BOOK as EMULATOR_PATH_BOOK
    from app.utils.common.io import read_file as read_file
    from app.utils.common.io import write_file as write_file
    from app.utils.common.tools import to_pep440 as to_pep440


__all__ = [
    "ProcessInfo",
    "ProcessManager",
    "ProcessResult",
    "ProcessRunner",
    "WebSocketClient",
    "busy_wait",
    "decode_bytes",
    "dpapi_decrypt",
    "dpapi_encrypt",
    "get_logger",
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
        """将设置名称从 PascalCase 或 camelCase 转为 snake_case，以兼容宿主配置命名。"""
        s = s.strip()
        if not s:
            return s
        s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()

    try:
        grp = getattr(Config.setting, group, None)
        if grp is None:
            grp = getattr(Config.setting, snake(group), None)
        if grp is None:
            return default
        return getattr(grp, name, getattr(grp, snake(name), default))
    except Exception:
        return default


if not TYPE_CHECKING:

    def __getattr__(name: str) -> Any:
        """按需查找并导出宿主公共工具和平台路径常量，无法找到的能力明确报告属性缺失。"""
        if name == "EMULATOR_PATH_BOOK":
            from app.utils.common.constants import EMULATOR_PATH_BOOK

            return EMULATOR_PATH_BOOK
        import app.utils as host_utils

        if hasattr(host_utils, name):
            return getattr(host_utils, name)
        from importlib import import_module

        for mod_name in (
            "app.utils.common.io",
            "app.utils.common.security",
            "app.utils.common.tools",
        ):
            mod = import_module(mod_name)
            if hasattr(mod, name):
                return getattr(mod, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """合并 SDK 声明与宿主工具的可见名称，供插件开发时查看和补全。"""
    import app.utils as host_utils

    return sorted(set(__all__) | {"EMULATOR_PATH_BOOK"} | set(dir(host_utils)))
