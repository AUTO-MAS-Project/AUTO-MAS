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

"""Emulator 2.0：一条配置纳管多条模拟器路径。

与 `app.utils.emulator` 的关系：本包只负责「设备号编排」与「实例设置」，
运行时（启动/关闭/显示）仍然复用 `app.utils.emulator` 里的旧管理器。
"""

from .bosskey import BossKey, decode_boss_key, read_boss_key
from .detect import DetectResult, probe_install_path
from .facade import DeviceUnavailableError, Emulator2Manager, dump_paths, load_paths
from .ldplayer14 import BossKeyUnavailableError, LDPlayer14Manager
from .slots import PathRecord, SlotRecord, SlotTable, make_path_id

__all__ = [
    "BossKey",
    "BossKeyUnavailableError",
    "DetectResult",
    "DeviceUnavailableError",
    "Emulator2Manager",
    "LDPlayer14Manager",
    "PathRecord",
    "SlotRecord",
    "SlotTable",
    "decode_boss_key",
    "dump_paths",
    "load_paths",
    "make_path_id",
    "probe_install_path",
    "read_boss_key",
]
