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

"""计划表配置上界；具体排期字段由脚本适配插件子类扩展。"""

from __future__ import annotations

from pydantic import Field

from app.config import ConfigEntry, ConfigGroup


class PlanEntry(ConfigEntry):
    """计划表配置上界。"""

    class Info(ConfigGroup):
        name: str = Field(default="新计划表", description="计划表名称")

    info: Info = Field(default_factory=Info, description="计划表信息")
