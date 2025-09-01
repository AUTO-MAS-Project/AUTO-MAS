#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

__version__ = "5.0.0"
__author__ = "DLmaster361 <DLmaster_361@163.com>"
__license__ = "GPL-3.0 license"

from .broadcast import Broadcast
from .config import Config, MaaConfig, GeneralConfig, MaaUserConfig, GeneralUserConfig
from .timer import MainTimer
from .task_manager import TaskManager

__all__ = [
    "Broadcast",
    "Config",
    "MaaConfig",
    "GeneralConfig",
    "MainTimer",
    "TaskManager",
    "MaaUserConfig",
    "GeneralUserConfig",
]
