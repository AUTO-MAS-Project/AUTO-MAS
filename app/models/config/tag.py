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

"""配置虚拟字段的展示标签。

被多个配置域（用户、工具箱）当作 Virtual 字段的输出形状，独立成模块避免
``script`` 与 ``tools`` 互相 import。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TagItem(BaseModel):
    """前端标签：文本 + 预置色板颜色。"""

    text: str = Field(..., description="标签文本")
    color: Literal[
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "brown",
        "black",
        "white",
        "gray",
        "silver",
        "gold",
    ] = Field(..., description="标签颜色")
