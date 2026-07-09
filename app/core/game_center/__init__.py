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

"""游戏中心: 统一管理 PC / 模拟器游戏的路径、版本、检查更新、下载安装、启动"""

from __future__ import annotations

from .presets import PRESETS, GamePreset, get_preset, list_presets
from .manager import GameCenterManager, game_center_manager

__all__ = [
    "PRESETS",
    "GamePreset",
    "get_preset",
    "list_presets",
    "GameCenterManager",
    "game_center_manager",
]
