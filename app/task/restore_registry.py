#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""消费宿主生成的有序恢复登记，匹配后才加载专项池表。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.config import ConfigEntry

if TYPE_CHECKING:
    from app.utils.common.config.restore import ConfigRestorePool


class RestorePoolResolver:
    def __init__(
        self,
        entries: tuple[
            tuple[type[ConfigEntry], Callable[[], list[ConfigRestorePool]] | None], ...
        ],
    ) -> None:
        seen = set()
        for entry_type, _ in entries:
            if entry_type in seen:
                raise ValueError(f"重复的恢复登记: {entry_type.__name__}")
            seen.add(entry_type)
        self._entries = entries

    def __call__(self, script: ConfigEntry) -> list[ConfigRestorePool]:
        for entry_type, load in self._entries:
            if isinstance(script, entry_type):
                if load is None:
                    break
                return load()
        raise ValueError("该专项暂不支持配置恢复")
