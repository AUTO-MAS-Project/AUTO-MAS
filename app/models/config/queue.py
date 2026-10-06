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

"""调度队列：队列本体、定时时间点与队列项。"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.config import ConfigCollection, ConfigEntry, ConfigGroup, ui
from app.config.shortcuts import collection
from app.utils.constants import UTC8


class QueueItemEntry(ConfigEntry):
    """队列项：引用脚本 uid。"""

    class Info(ConfigGroup):
        script_id: str = Field(
            default="-",
            description="任务所对应的脚本ID, 为None时表示未选择",
        )

    info: Info = Field(default_factory=Info, description="队列项")


class TimeSetEntry(ConfigEntry):
    """队列定时时间点。"""

    class Info(ConfigGroup):
        enabled: bool = Field(default=True, description="是否启用")
        days: list[str] = Field(
            default_factory=lambda: list(calendar.day_name),
            description="执行周期, 可多选",
        )
        time: Annotated[datetime, ui(format="hm")] = Field(
            default=datetime(2000, 1, 1, 0, 0, tzinfo=UTC8),
            description="时间设置, 格式为HH:MM",
        )

    info: Info = Field(default_factory=Info, description="时间项")


class QueueEntry(ConfigEntry):
    """单条调度队列。"""

    class Info(ConfigGroup):
        name: str = Field(default="新队列", description="队列名称")
        time_enabled: bool = Field(default=False, description="是否启用定时")
        start_up_enabled: bool = Field(default=False, description="是否启动时运行")
        after_accomplish: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ] = Field(default="NoAction", description="完成后操作")

    class Data(ConfigGroup):
        last_timed_start: Annotated[datetime, ui(format="hm")] = Field(
            default=datetime(2000, 1, 1, 0, 0, tzinfo=UTC8),
            description="上次定时启动时间",
        )

    info: Info = Field(default_factory=Info, description="队列信息")
    data: Data = Field(default_factory=Data, description="队列运行时数据")
    time_sets: ConfigCollection[TimeSetEntry] = collection(TimeSetEntry)
    items: ConfigCollection[QueueItemEntry] = collection(QueueItemEntry)
