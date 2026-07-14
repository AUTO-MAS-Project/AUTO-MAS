#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""已迁移到 ok-script 插件的旧控制器兼容层。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core import Config
from app.core.script_types import script_type_registry
from app.models.task import ScriptItem


class OkScriptManager:
    """兼容旧导入路径，实际创建已注册插件的通用 manager。"""

    def __new__(cls, script_info: ScriptItem) -> Any:
        script_uid = uuid.UUID(script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        provider = script_type_registry.get_by_script_config(script_config)
        if provider.type_key != "OkScript":
            raise RuntimeError(
                f"旧 ok-script 控制器仅兼容 OkScript Provider，当前为 {provider.type_key}"
            )
        return provider.manager_factory(script_info)
