#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""主程序配置字段表，按用途分域。

各域只声明字段与自身触发器；配置实例的装配与启动顺序在 ``app.core.config``。
"""

from .emulator import EmulatorDeviceEntry, EmulatorEntry
from .game import GameEntry, GameDeviceEntry
from .plan import PlanEntry
from .plugin import (
    PluginConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from .queue import QueueEntry, QueueItemEntry, TimeSetEntry
from .script import ScriptEntry, UserEntry
from .setting import Setting, Webhook
from .tag import TagItem
from .tools import GameSignAccount, Tools

__all__ = [
    "EmulatorDeviceEntry",
    "EmulatorEntry",
    "GameDeviceEntry",
    "GameEntry",
    "GameSignAccount",
    "PlanEntry",
    "PluginConfig",
    "PluginMeta",
    "PluginRecord",
    "PluginRegistryCollection",
    "QueueEntry",
    "QueueItemEntry",
    "ScriptEntry",
    "Setting",
    "TagItem",
    "TimeSetEntry",
    "Tools",
    "UserEntry",
    "Webhook",
]
