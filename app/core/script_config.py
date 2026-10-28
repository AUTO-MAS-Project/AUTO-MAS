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

"""专项配置操作契约；具体实现由宿主按配置类型注入。"""

from pathlib import Path
from typing import Any, Protocol

from app.config import ConfigEntry


class ScriptConfigHandler(Protocol):
    """公共配置入口在业务锁检查后调用的专项操作。"""

    async def initialize(self, script: ConfigEntry) -> None: ...

    def validate_update(self, data: dict[str, Any]) -> None: ...

    def import_config(
        self,
        script: ConfigEntry,
        target_directory: Path,
        *,
        user_id: str | None = None,
    ) -> None: ...
