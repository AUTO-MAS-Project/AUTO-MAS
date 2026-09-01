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
from .paths import resource_path
from .security import (
    dpapi_encrypt,
    dpapi_decrypt,
    format_exception_reason,
    sanitize_log_message,
)
from .supervision import is_supervised

_LAZY_EXPORTS = {
    "LogMonitor": (".LogMonitor", "LogMonitor"),
    "strptime": (".LogMonitor", "strptime"),
    "ProcessManager": (".ProcessManager", "ProcessManager"),
    "ProcessRunner": (".ProcessManager", "ProcessRunner"),
    "ProcessInfo": (".ProcessManager", "ProcessInfo"),
    "ProcessResult": (".ProcessManager", "ProcessResult"),
    "is_process_running": (".ProcessManager", "is_process_running"),
    "is_process_alive": (".ProcessManager", "is_process_alive"),
    "activate_window_by_pid": (".ProcessManager", "activate_window_by_pid"),
    "has_visible_window": (".ProcessManager", "has_visible_window"),
    "RegexMatcher": (".LogPatternExtractor", "RegexMatcher"),
    "MultiLineAggregator": (".LogPatternExtractor", "MultiLineAggregator"),
    "compile_regex": (".LogPatternExtractor", "compile_regex"),
    "load_patterns": (".LogPatternExtractor", "load_patterns"),
    "apply_patterns": (".LogPatternExtractor", "apply_patterns"),
    "flush_patterns": (".LogPatternExtractor", "flush_patterns"),
    "debug_pattern": (".LogPatternExtractor", "debug_pattern"),
    "LogSignMatcher": (".LogPatternExtractor", "LogSignMatcher"),
    "compile_log_signs": (".LogPatternExtractor", "compile_log_signs"),
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


class LazyProxy:
    """惰性代理：首次属性访问时才导入真实对象，避免初始化期间的循环导入。

    与模块级 __getattr__ 不同，它绑定为一个真实的模块全局名，因此函数内的
    裸全局名引用（LOAD_GLOBAL）也能正常解析；同时转发属性读写，保证
    ``Config.xxx = yyy`` 这类赋值落到真实对象上。
    """

    def __init__(self, module: str, name: str) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_obj", None)

    def _resolve(self):
        obj = self.__dict__["_obj"]
        if obj is None:
            from importlib import import_module

            obj = getattr(import_module(self._module), self._name)
            object.__setattr__(self, "_obj", obj)
        return obj

    def __getattr__(self, attr: str):
        return getattr(self._resolve(), attr)

    def __setattr__(self, attr: str, value) -> None:
        setattr(self._resolve(), attr, value)


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
    "is_supervised",
    "resource_path",
    "strptime",
    "MumuManager",
    "LDManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
    "decode_bytes",
    "busy_wait",
    "WebSocketClient",
    "create_ws_client",
    "RegexMatcher",
    "MultiLineAggregator",
    "compile_regex",
    "load_patterns",
    "apply_patterns",
    "flush_patterns",
    "debug_pattern",
]
