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
"""BAAH 配置查询，脚本配置读取能力由宿主注入。"""

import uuid
from collections.abc import Callable

from app.config import ConfigEntry
from app.models.config import BAAHConfig

from .tools import CONFIG_DIR_NAME, list_config_names


class BAAHConfigService:
    """持有 BAAH 安装布局与配置名称查询策略。"""

    def __init__(self, *, get_script: Callable[[uuid.UUID], ConfigEntry]) -> None:
        self._get_script = get_script

    def get_config_names(self, script_id: str) -> list[str]:
        """读取安装目录下已有的配置文件名，不含 .json 后缀。"""
        script_config = self._get_script(uuid.UUID(script_id))
        if not isinstance(script_config, BAAHConfig):
            raise TypeError("脚本配置类型错误, 不是 BAAH 类型")

        baah_path = script_config.Script.BAAHPath
        if baah_path is None:
            return []
        return list_config_names(baah_path.parent / CONFIG_DIR_NAME)
