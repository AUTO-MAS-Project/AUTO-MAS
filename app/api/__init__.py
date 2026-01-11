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

from .core import router as core_router
from .info import router as info_router
from .scripts import router as scripts_router
from .plan import router as plan_router
from .emulator import router as emulator_router
from .queue import router as queue_router
from .dispatch import router as dispatch_router
from .history import router as history_router
from .setting import router as setting_router
from .update import router as update_router
from .ocr import router as ocr_router
from .ws_debug import router as ws_debug_router
from .llm import router as llm_router

__all__ = [
    "core_router",
    "info_router",
    "scripts_router",
    "plan_router",
    "emulator_router",
    "queue_router",
    "dispatch_router",
    "history_router",
    "setting_router",
    "update_router",
    "ocr_router",
    "ws_debug_router",
    "llm_router",
]
