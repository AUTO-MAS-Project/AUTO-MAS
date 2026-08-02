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


from .constants import *
from .logger import get_logger
from .security import dpapi_encrypt, dpapi_decrypt, sanitize_log_message

_LAZY_EXPORTS = {
    "ImageUtils": (".ImageUtils", "ImageUtils"),
    "LogMonitor": (".LogMonitor", "LogMonitor"),
    "strptime": (".LogMonitor", "strptime"),
    "ProcessManager": (".ProcessManager", "ProcessManager"),
    "ProcessRunner": (".ProcessManager", "ProcessRunner"),
    "ProcessInfo": (".ProcessManager", "ProcessInfo"),
    "ProcessResult": (".ProcessManager", "ProcessResult"),
    "is_process_running": (".ProcessManager", "is_process_running"),
    "MumuManager": (".emulator", "MumuManager"),
    "LDManager": (".emulator", "LDManager"),
    "search_all_emulators": (".emulator", "search_all_emulators"),
    "EMULATOR_TYPE_BOOK": (".emulator", "EMULATOR_TYPE_BOOK"),
    "decode_bytes": (".tools", "decode_bytes"),
    "busy_wait": (".tools", "busy_wait"),
    "WebSocketClient": (".websocket", "WebSocketClient"),
    "create_ws_client": (".websocket", "create_ws_client"),
    "get_path_runtime_lock": (".runtime_lock", "get_path_runtime_lock"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "constants",
    "get_logger",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "sanitize_log_message",
]
