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


from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigGroup,
    UiVisibility,
    collection,
    ref,
    tz,
    ui,
)
from app.config.types import (
    FilePath,
    JsonDictString,
    UrlString,
)

from .base import DomainEntry
from .shared import local_timezone


class Webhook(DomainEntry):
    "Webhook 配置"

    class DataFields(ConfigGroup):
        Headers: JsonDictString = Field(
            default_factory=lambda: "{ }", description="请求头"
        )

        Method: Literal["POST", "GET"] = Field(
            default_factory=lambda: "POST", description="请求方法"
        )

        Template: str = Field(default_factory=lambda: "", description="消息模板")

        Url: UrlString = Field(
            default_factory=lambda: "", description="Webhook URL 地址"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: True, description="是否启用")

        Name: str = Field(
            default_factory=lambda: "新自定义 Webhook 通知", description="Webhook 名称"
        )

    Info: InfoFields = Field(default_factory=InfoFields)


class QueueItem(DomainEntry):
    "队列项配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        LastCycleFinishedAt: Annotated[
            datetime, tz(local_timezone), ui(format="hms")
        ] = Field(
            default_factory=lambda: datetime.fromisoformat(
                "2000-01-01 00:00:00"
            ).replace(tzinfo=local_timezone()),
            description="上次循环结束时间",
        )

        LastCycleStartedAt: Annotated[
            datetime, tz(local_timezone), ui(format="hms")
        ] = Field(
            default_factory=lambda: datetime.fromisoformat(
                "2000-01-01 00:00:00"
            ).replace(tzinfo=local_timezone()),
            description="上次循环开始时间",
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        ScriptId: Annotated[
            UUID | str,
            ref(
                "ScriptConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="脚本 ID")

    Info: InfoFields = Field(default_factory=InfoFields)

    class ScheduleFields(ConfigGroup):
        Days: list[
            Literal[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        ] = Field(
            default_factory=lambda: [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
            description="固定时间模式的执行周期",
        )

        Enabled: bool = Field(
            default_factory=lambda: True, description="是否参与循环调度"
        )

        IntervalAnchor: Literal["start", "finish"] = Field(
            default_factory=lambda: "start",
            description="间隔模式的计时基准: start 为上次开始, finish 为上次结束",
        )

        IntervalMinutes: Annotated[int, Field(ge=1, le=10080)] = Field(
            default_factory=lambda: 480,
            description="间隔模式的间隔分钟数",
        )

        Mode: Literal["fixed_time", "interval"] = Field(
            default_factory=lambda: "fixed_time",
            description="循环调度模式: fixed_time 为固定时间, interval 为间隔",
        )

        NextRunAt: Annotated[datetime, tz(local_timezone), ui(format="hms")] = Field(
            default_factory=lambda: datetime.fromisoformat(
                "2000-01-01 00:00:00"
            ).replace(tzinfo=local_timezone()),
            description="下次运行时间, 空值哨兵表示由调度器按模式推算",
        )

        Time: Annotated[datetime, tz(local_timezone), ui(format="hm")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=local_timezone()),
            description="固定时间模式的执行时间",
        )

    Schedule: ScheduleFields = Field(default_factory=ScheduleFields)


class TimeSet(DomainEntry):
    "时间设置配置"

    class InfoFields(ConfigGroup):
        Days: list[
            Literal[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        ] = Field(
            default_factory=lambda: [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
            description="执行周期",
        )

        Enabled: bool = Field(default_factory=lambda: True, description="是否启用")

        Time: Annotated[datetime, tz(local_timezone), ui(format="hm")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=local_timezone()),
            description="执行时间",
        )

    Info: InfoFields = Field(default_factory=InfoFields)


_TimeSetEntry = TimeSet
_QueueItemEntry = QueueItem


class QueueConfig(DomainEntry):
    "队列配置"

    class DataFields(ConfigGroup):
        LastStartupTime: Annotated[datetime, tz(local_timezone), ui(format="date")] = (
            Field(
                default_factory=lambda: datetime(2000, 1, 1, tzinfo=local_timezone()),
                description="上次启动时运行时间",
            )
        )

        LastTimedStart: Annotated[datetime, tz(local_timezone), ui(format="hm")] = (
            Field(
                default_factory=lambda: datetime.fromisoformat(
                    "2000-01-01 00:00"
                ).replace(tzinfo=local_timezone()),
                description="上次定时启动时间",
            )
        )

    Data: Annotated[DataFields, ui(visibility=UiVisibility.HIDE)] = Field(
        default_factory=DataFields
    )

    class InfoFields(ConfigGroup):
        AfterAccomplish: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "RestartSelf",
            "Logoff",
        ] = Field(default_factory=lambda: "NoAction", description="完成后操作")

        AfterAccomplishDelay: Annotated[int, Field(ge=0, le=1440)] = Field(
            default_factory=lambda: 0,
            description="完成后操作的延时时长, 单位分钟, 0 表示队列结束后直接进入倒计时",
        )

        CycleEnabled: bool = Field(
            default_factory=lambda: False,
            description="是否为循环队列: 定时与循环互斥, 循环队列按队列项各自的周期持续运行",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False,
            description="队列级运行后脚本: 运行结束后执行一次, 先于「完成后操作」",
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False,
            description="队列级运行前脚本: 一次运行只执行一次, 循环队列在整个运行期间不重复执行",
        )

        Name: str = Field(default_factory=lambda: "新队列", description="队列名称")

        ScriptAfterTask: FilePath = Field(
            default_factory=lambda: None, description="队列运行后脚本路径"
        )

        ScriptBeforeTask: FilePath = Field(
            default_factory=lambda: None, description="队列运行前脚本路径"
        )

        StartUpMode: Literal["Never", "Always", "DailyFirst"] = Field(
            default_factory=lambda: "Never", description="是否在启动时自动运行"
        )

        TimeEnabled: bool = Field(
            default_factory=lambda: False, description="是否启用定时启动"
        )

    Info: InfoFields = Field(default_factory=InfoFields)
    TimeSet: ConfigCollection[_TimeSetEntry] = collection(TimeSet)
    QueueItem: ConfigCollection[_QueueItemEntry] = collection(QueueItem)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        info_data = data.get("Info")
        if isinstance(info_data, dict) and "StartUpMode" not in info_data:
            StartUpEnabled = info_data.get("StartUpEnabled")
            if isinstance(StartUpEnabled, bool):
                info_data["StartUpMode"] = "Always" if StartUpEnabled else "Never"
        return data


__all__ = ["Webhook", "QueueItem", "TimeSet", "QueueConfig"]
