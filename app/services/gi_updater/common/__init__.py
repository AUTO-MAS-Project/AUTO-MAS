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

"""通用基础设施：版本号、ini、进度、日志、路径工具。"""

from app.services.gi_updater.common.ini import IniFile
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.paths import (
    UnsafePathError,
    safe_join,
    split_rel_path,
)
from app.services.gi_updater.common.progress import (
    ProgressBase,
    ProgressListener,
    ProgressSnapshot,
    SilentProgressListener,
    summarize_size,
)
from app.services.gi_updater.common.version import GameVersion

__all__ = [
    "GameVersion",
    "IniFile",
    "UnsafePathError",
    "safe_join",
    "split_rel_path",
    "ProgressBase",
    "ProgressListener",
    "ProgressSnapshot",
    "SilentProgressListener",
    "summarize_size",
    "get_logger",
]
