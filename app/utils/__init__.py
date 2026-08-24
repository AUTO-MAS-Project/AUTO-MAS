#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import sys
import types

from .constants import *
from .logger import get_logger
from .security import (
    dpapi_encrypt,
    dpapi_decrypt,
    format_exception_reason,
    sanitize_log_message,
)

_LAZY_EXPORTS = {
    "ImageUtils": (".ImageUtils", "ImageUtils"),
    "LogMonitor": (".LogMonitor", "LogMonitor"),
    "strptime": (".LogMonitor", "strptime"),
    "ProcessManager": (".ProcessManager", "ProcessManager"),
    "ProcessRunner": (".ProcessManager", "ProcessRunner"),
    "ProcessInfo": (".ProcessManager", "ProcessInfo"),
    "ProcessResult": (".ProcessManager", "ProcessResult"),
    "is_process_running": (".ProcessManager", "is_process_running"),
    "PATTERN_TYPE_SPLIT": (".LogPatternExtractor", "PATTERN_TYPE_SPLIT"),
    "PATTERN_TYPE_REGEX": (".LogPatternExtractor", "PATTERN_TYPE_REGEX"),
    "PATTERN_TYPE_MULTILINE": (".LogPatternExtractor", "PATTERN_TYPE_MULTILINE"),
    "SUPPORTED_PATTERN_TYPES": (".LogPatternExtractor", "SUPPORTED_PATTERN_TYPES"),
    "SplitMatcher": (".LogPatternExtractor", "SplitMatcher"),
    "RegexMatcher": (".LogPatternExtractor", "RegexMatcher"),
    "MultiLineAggregator": (".LogPatternExtractor", "MultiLineAggregator"),
    "CompiledMatcher": (".LogPatternExtractor", "CompiledMatcher"),
    "compile_regex": (".LogPatternExtractor", "compile_regex"),
    "compile_pattern": (".LogPatternExtractor", "compile_pattern"),
    "load_patterns": (".LogPatternExtractor", "load_patterns"),
    "serialize_patterns": (".LogPatternExtractor", "serialize_patterns"),
    "apply_patterns": (".LogPatternExtractor", "apply_patterns"),
    "flush_patterns": (".LogPatternExtractor", "flush_patterns"),
    "validate_pattern": (".LogPatternExtractor", "validate_pattern"),
    "debug_pattern": (".LogPatternExtractor", "debug_pattern"),
    "MumuManager": (".emulator", "MumuManager"),
    "LDManager": (".emulator", "LDManager"),
    "search_all_emulators": (".emulator", "search_all_emulators"),
    "EMULATOR_TYPE_BOOK": (".emulator", "EMULATOR_TYPE_BOOK"),
    "decode_bytes": (".tools", "decode_bytes"),
    "busy_wait": (".tools", "busy_wait"),
    "WebSocketClient": (".websocket", "WebSocketClient"),
    "create_ws_client": (".websocket", "create_ws_client"),
}


def _resolve_lazy(name: str):
    """解析惰性导出并缓存到模块命名空间。"""

    from importlib import import_module

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return _resolve_lazy(name)


class _LazyModule(types.ModuleType):
    """拦截 import 系统把惰性子模块挂到本包命名空间的副作用。

    例如 ``app.utils.ProcessManager`` 子模块被直接导入后，
    import 系统会把该模块设为 ``app.utils.ProcessManager`` 属性，
    导致 ``from app.utils import ProcessManager`` 拿到模块而非类。
    此处将命中惰性导出名的模块值解析为真实导出对象。
    """

    def __getattribute__(self, name: str):
        value = super().__getattribute__(name)
        if isinstance(value, types.ModuleType) and name in _LAZY_EXPORTS:
            return _resolve_lazy(name)
        return value


# 替换模块类，使上述守卫对运行期所有属性访问生效
sys.modules[__name__].__class__ = _LazyModule

__all__ = [
    "constants",
    "get_logger",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "format_exception_reason",
    "sanitize_log_message",
    "strptime",
    "MumuManager",
    "LDManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
    "decode_bytes",
    "busy_wait",
    "WebSocketClient",
    "create_ws_client",
    "PATTERN_TYPE_SPLIT",
    "PATTERN_TYPE_REGEX",
    "PATTERN_TYPE_MULTILINE",
    "SUPPORTED_PATTERN_TYPES",
    "SplitMatcher",
    "RegexMatcher",
    "MultiLineAggregator",
    "CompiledMatcher",
    "compile_regex",
    "compile_pattern",
    "load_patterns",
    "serialize_patterns",
    "apply_patterns",
    "flush_patterns",
    "validate_pattern",
    "debug_pattern",
]
