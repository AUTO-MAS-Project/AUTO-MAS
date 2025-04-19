#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

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

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA核心组件包
v4.3
作者：DLmaster_361
"""

__version__ = "4.2.0"
__author__ = "DLmaster361 <DLmaster_361@163.com>"
__license__ = "GPL-3.0 license"

from .config import QueueConfig, MaaConfig, MaaUserConfig, Config
from .main_info_bar import MainInfoBar
from .network import Network
from .task_manager import Task, TaskManager
from .timer import MainTimer

__all__ = [
    "Config",
    "QueueConfig",
    "MaaConfig",
    "MaaUserConfig",
    "MainInfoBar",
    "Network",
    "Task",
    "TaskManager",
    "MainTimer",
]
