#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""版本管理层：本地版本、远程版本、安装状态机、包清单决策。

原神在 ``versioning/genshin.py``，三款共用的状态机与决策在 ``versioning/base.py``。
"""

from app.services.gi_updater.versioning.base import (
    GAME_STATE_LABELS,
    GameInstallStateEnum,
    GameVersionBase,
)
from app.services.gi_updater.versioning.genshin import (
    ALTERNATIVE_EXEC_NAME,
    AUDIO_VOICE_LANGUAGE_LIST,
    GLOBAL_EXEC_NAME,
    GameTypeGenshinVersion,
)

__all__ = [
    "GameInstallStateEnum",
    "GameVersionBase",
    "GAME_STATE_LABELS",
    "GameTypeGenshinVersion",
    "AUDIO_VOICE_LANGUAGE_LIST",
    "GLOBAL_EXEC_NAME",
    "ALTERNATIVE_EXEC_NAME",
]
