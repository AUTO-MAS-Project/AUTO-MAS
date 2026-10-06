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


"""工具包入口：统一急加载全部公开符号。"""

from .constants import *
from .logger import get_logger
from .paths import resource_path
from .security import (
    dpapi_decrypt,
    dpapi_encrypt,
    format_exception_reason,
    sanitize_log_message,
)
from .supervision import is_backend_dev_mode, is_supervised

from .io import read_file, write_file
from .lazy import LazyProxy
from .runtime_lock import get_path_runtime_lock

from .LogMonitor import LogMonitor, strptime
from .LogPatternExtractor import (
    LogSignMatcher,
    MultiLineAggregator,
    RegexMatcher,
    apply_patterns,
    compile_log_signs,
    compile_regex,
    debug_pattern,
    flush_patterns,
    load_patterns,
)
from .ProcessManager import (
    ProcessInfo,
    ProcessManager,
    ProcessResult,
    ProcessRunner,
    is_process_alive,
    is_process_running,
)
from .tools import busy_wait, decode_bytes, to_pep440
from .websocket import WebSocketClient, create_ws_client

# `.emulator`（MumuManager/LDManager/search_all_emulators/EMULATOR_TYPE_BOOK）不再顶层导出：
# 子包仍引用已删除的 app.models.config.EmulatorConfig / app.models.emulator，
# 且插件分支已由各自 adapter 接管。
__all__ = [
    "apply_patterns",
    "busy_wait",
    "compile_log_signs",
    "compile_regex",
    "constants",
    "create_ws_client",
    "debug_pattern",
    "decode_bytes",
    "dpapi_decrypt",
    "dpapi_encrypt",
    "flush_patterns",
    "format_exception_reason",
    "get_logger",
    "get_path_runtime_lock",
    "is_backend_dev_mode",
    "is_process_alive",
    "is_process_running",
    "is_supervised",
    "LazyProxy",
    "load_patterns",
    "LogMonitor",
    "LogSignMatcher",
    "MultiLineAggregator",
    "ProcessInfo",
    "ProcessManager",
    "ProcessResult",
    "ProcessRunner",
    "read_file",
    "RegexMatcher",
    "resource_path",
    "sanitize_log_message",
    "strptime",
    "to_pep440",
    "WebSocketClient",
    "write_file",
]
