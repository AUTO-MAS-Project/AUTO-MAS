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
from datetime import datetime, timedelta
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigGroup,
    Trigger,
    UiVisibility,
    Virtual,
    collection,
    legacy,
    ref,
    trigger_field,
    tz,
    ui,
    virtual_field,
)
from app.config.types import (
    FilePath,
    JsonDictString,
    UrlString,
)

from .base import DomainEntry
from .shared import local_timezone

Weekday = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]
_DEFAULT_DAYS: tuple[Weekday, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


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

    related_config: ClassVar[dict[str, object]] = {}

    class InfoFields(ConfigGroup):
        ScriptId: Annotated[
            UUID | str,
            ref(
                "ScriptConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="托管 ID")

    Info: InfoFields = Field(default_factory=InfoFields)

    class ScheduleFields(ConfigGroup):
        Days: list[Weekday] = Field(
            default_factory=lambda: list(_DEFAULT_DAYS),
            description="该队列项允许执行的星期，由 L2 判断是否跳过",
        )

    Schedule: ScheduleFields = Field(default_factory=ScheduleFields)


class TimeSet(DomainEntry):
    "时间设置配置"

    class InfoFields(ConfigGroup):
        Days: list[Weekday] = Field(
            default_factory=lambda: list(_DEFAULT_DAYS),
            description="执行周期",
        )

        Enabled: bool = Field(default_factory=lambda: True, description="是否启用")

        Time: Annotated[datetime, tz(local_timezone), ui(format="hm")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=local_timezone()),
            description="执行时间",
        )

    Info: Annotated[
        InfoFields, ui(visibility=lambda entry: entry.time_visibility())
    ] = Field(default_factory=InfoFields)

    def time_visibility(self) -> UiVisibility:
        queue = self.parent.parent if self.parent is not None else None
        return (
            UiVisibility.DISABLE
            if isinstance(queue, QueueConfig) and not queue.Info.TimeEnabled
            else UiVisibility.SHOW
        )


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

        LastStartTime: Annotated[
            datetime,
            tz(local_timezone),
            ui(format="hms"),
            legacy(group="Data", name="LastTimedStart"),
        ] = Field(
            default_factory=lambda: datetime.fromisoformat("2000-01-01 00:00").replace(
                tzinfo=local_timezone()
            ),
            description="L1 上次成功创建该队列任务的时间",
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
            description="是否启用队列循环触发，可与定时和软件启动触发同时启用",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False,
            description="队列级运行后脚本: 运行结束后执行一次, 先于「完成后操作」",
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False,
            description="队列级运行前脚本: 每次任务快照开始时执行一次",
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

    class CycleFields(ConfigGroup):
        IntervalMinutes: Annotated[int, Field(ge=1, le=10080)] = Field(
            default=480, description="队列循环触发间隔，单位分钟"
        )
        LastRunAt: Annotated[
            datetime | None,
            tz(local_timezone),
            ui(format="hms", visibility=UiVisibility.DISABLE),
        ] = Field(
            default=None,
            description="上次循环成功提交时间；为空时启用循环立即到期",
        )
        NextRunAt: Annotated[
            Virtual[datetime | None], tz(local_timezone), ui(format="hm")
        ] = Field(
            default=None, description="下次循环触发时间，由上次触发时间和间隔计算"
        )
        ResetTimer: Trigger = Field(
            default=False, description="重置循环计时，将上次循环触发时间设为现在"
        )

    Cycle: Annotated[
        CycleFields, ui(visibility=lambda entry: entry.cycle_visibility())
    ] = Field(default_factory=CycleFields)

    @virtual_field("Cycle.NextRunAt")
    def next_cycle_run(self) -> datetime | None:
        """循环到期按本地分钟判定，不沿用上次触发的秒和微秒。"""
        last = self.Cycle.LastRunAt
        return (
            (last + timedelta(minutes=self.Cycle.IntervalMinutes)).replace(
                second=0, microsecond=0
            )
            if last is not None
            else None
        )

    def cycle_visibility(self) -> UiVisibility:
        return UiVisibility.SHOW if self.Info.CycleEnabled else UiVisibility.DISABLE

    @trigger_field("Cycle.ResetTimer")
    async def reset_cycle_timer(self) -> None:
        self.Cycle.LastRunAt = datetime.now().astimezone()
        await self.commit()

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


@TimeSet.connect(group="Info")
@ConfigCollection.connect()
def reject_disabled_time_writes(
    sender: ConfigCollection[TimeSet] | TimeSet, _event: object
) -> None:
    """只拦截运行时写入；禁用队列的历史时间项仍可正常初始化。"""
    collection = sender.parent if isinstance(sender, TimeSet) else sender
    queue = collection.parent if collection is not None else None
    if (
        isinstance(queue, QueueConfig)
        and collection is queue.TimeSet
        and not queue.Info.TimeEnabled
    ):
        raise ValueError("请先启用队列定时设置")


__all__ = ["Webhook", "QueueItem", "TimeSet", "QueueConfig"]
