#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

__version__ = "5.0.0"
__author__ = "DLmaster361 <DLmaster_361@163.com>"
__license__ = "GPL-3.0 license"


from .constants import *
from .logger import get_logger
from .ImageUtils import ImageUtils
from .LogMonitor import LogMonitor, strptime
from .ProcessManager import ProcessManager, ProcessRunner, ProcessInfo, ProcessResult
from .security import dpapi_encrypt, dpapi_decrypt, sanitize_log_message
from .emulator import MumuManager, LDManager, search_all_emulators, EMULATOR_TYPE_BOOK
from .tools import decode_bytes
from .websocket import WebSocketClient, create_ws_client

__all__ = [
    "constants",
    "get_logger",
    "ImageUtils",
    "LogMonitor",
    "ProcessManager",
    "ProcessRunner",
    "ProcessInfo",
    "ProcessResult",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "sanitize_log_message",
    "strptime",
    "MumuManager",
    "LDManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
    "decode_bytes",
    "WebSocketClient",
    "create_ws_client",
]
