#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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


from .mumu import MumuManager
from .ldplayer import LDManager
from .general import GeneralDeviceManager
from .tools import search_all_emulators

EMULATOR_TYPE_BOOK = {
    "mumu": MumuManager,
    "ldplayer": LDManager,
    "general": GeneralDeviceManager,
}

__all__ = [
    "MumuManager",
    "LDManager",
    "GeneralDeviceManager",
    "search_all_emulators",
    "EMULATOR_TYPE_BOOK",
]
