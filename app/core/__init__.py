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


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broadcast import Broadcast as Broadcast
    from .plugins import PluginManager as PluginManager
    from .emulator_manager import EmulatorManager as EmulatorManager
    from .task_manager import TaskManager as TaskManager
    from .maa_manager import MaaFWManager as MaaFWManager
    from .timer import MainTimer as MainTimer
    from .config import Config as Config

__all__ = [
    "Broadcast",
    "Config",
    "MainTimer",
    "TaskManager",
    "EmulatorManager",
    "MaaFWManager",
    "PluginManager",
]


def __getattr__(name: str):
    if name == "Broadcast":
        from .broadcast import Broadcast

        return Broadcast
    if name == "EmulatorManager":
        from .emulator_manager import EmulatorManager

        return EmulatorManager
    if name == "PluginManager":
        from .plugins import PluginManager

        return PluginManager
    if name == "TaskManager":
        from .task_manager import TaskManager

        return TaskManager
    if name == "MaaFWManager":
        from .maa_manager import MaaFWManager

        return MaaFWManager
    if name == "MainTimer":
        from .timer import MainTimer

        return MainTimer
    if name == "Config":
        from .config import Config

        return Config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
