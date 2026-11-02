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


from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .community import Community as Community
    from .config import Config as Config
    from .desktop_guard import DesktopGuard as DesktopGuard
    from .emulator_manager import EmulatorManager as EmulatorManager
    from .game_calendar import GameCalendar as GameCalendar
    from .game_maintenance import GameMaintenance as GameMaintenance
    from .history import History as History
    from .i18n import I18n as I18n
    from .lifecycle import ShutdownCoordinator as ShutdownCoordinator
    from .maa_manager import MaaFWManager as MaaFWManager
    from .notify import Notify as Notify
    from .runtime_tasks import RuntimeTasks as RuntimeTasks
    from .task_manager import TaskManager as TaskManager
    from .taskboard import Taskboard as Taskboard
    from .timer import MainTimer as MainTimer
    from .update import Updater as Updater
    from .ws import Commands as Commands
    from .ws import Dispatcher as Dispatcher
    from .ws import MainConnection as MainConnection
    from .ws import Publisher as Publisher

_LAZY_EXPORTS = {
    "Config": (".config", "Config"),
    "Notify": (".notify", "Notify"),
    "RuntimeTasks": (".runtime_tasks", "RuntimeTasks"),
    "TaskManager": (".task_manager", "TaskManager"),
    "MainTimer": (".timer", "MainTimer"),
    "EmulatorManager": (".emulator_manager", "EmulatorManager"),
    "Updater": (".update", "Updater"),
    "MaaFWManager": (".maa_manager", "MaaFWManager"),
    "DesktopGuard": (".desktop_guard", "DesktopGuard"),
    "GameCalendar": (".game_calendar", "GameCalendar"),
    "GameMaintenance": (".game_maintenance", "GameMaintenance"),
    "History": (".history", "History"),
    "I18n": (".i18n", "I18n"),
    "ShutdownCoordinator": (".lifecycle", "ShutdownCoordinator"),
    "Community": (".community", "Community"),
    "Taskboard": (".taskboard", "Taskboard"),
    "MainConnection": (".ws", "MainConnection"),
    "Commands": (".ws", "Commands"),
    "Dispatcher": (".ws", "Dispatcher"),
    "Publisher": (".ws", "Publisher"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "Config",
    "Notify",
    "RuntimeTasks",
    "TaskManager",
    "MainTimer",
    "EmulatorManager",
    "Updater",
    "MaaFWManager",
    "DesktopGuard",
    "GameCalendar",
    "GameMaintenance",
    "History",
    "I18n",
    "ShutdownCoordinator",
    "Community",
    "Taskboard",
    "MainConnection",
    "Commands",
    "Dispatcher",
    "Publisher",
]
