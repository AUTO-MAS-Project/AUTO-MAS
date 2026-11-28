"""再导出宿主 ``app.utils``（整包；运行时懒取，编写期可提示）。"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from typing import TYPE_CHECKING, Any

from pydantic.alias_generators import to_snake

if TYPE_CHECKING:
    from app.utils import *  # noqa: F403 - 与宿主公开工具保持同一份静态类型声明。
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
    "integrity",
    "is_process_running",
    "read_file",
    "sanitize_log_message",
    "to_pep440",
    "write_file",
]


def get_setting(group: str, name: str, default: Any = None) -> Any:
    """读 ``Config.setting.<group>.<name>``；键名支持 PascalCase 或 snake_case。"""
    from auto_mas_core import Config

    def matching_names(fields: Collection[str], key: str) -> Iterator[str]:
        """原名优先，随后按规范化名称匹配。"""
        if key in fields:
            yield key
        normalized = to_snake(key.strip())
        yield from (
            field for field in fields if field != key and to_snake(field) == normalized
        )

    setting = Config.setting
    for group_name in matching_names(type(setting)._cfg_group_fields, group):
        section = getattr(setting, group_name)
        field_name = next(matching_names(type(section).model_fields, name), None)
        if field_name is not None:
            return getattr(section, field_name)
    return default


if not TYPE_CHECKING:

    def __getattr__(name: str) -> Any:
        """按需查找并导出宿主公共工具和平台路径常量，无法找到的能力明确报告属性缺失。"""
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

    return sorted(set(__all__) | set(dir(host_utils)))
