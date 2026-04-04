from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase


class QueueIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueConfig"] = Field(..., description="配置类型")


class QueueItemIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueItem"] = Field(..., description="配置类型")


class TimeSetIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["TimeSet"] = Field(..., description="配置类型")


class QueueItemInfoRead(ApiModel):
    ScriptId: str = Field(default="-", description="任务所对应的脚本ID")


class QueueItemInfoPatch(ApiModel):
    ScriptId: str | None = Field(default=None, description="任务所对应的脚本ID")


class QueueItemRead(ApiModel):
    Info: QueueItemInfoRead = Field(default_factory=QueueItemInfoRead, description="队列项")


class QueueItemPatch(ApiModel):
    Info: QueueItemInfoPatch | None = Field(default=None, description="队列项")


class TimeSetInfoRead(ApiModel):
    Enabled: bool = Field(default=True, description="是否启用")
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
        description="执行周期, 可多选",
    )
    Time: str = Field(default="00:00", description="时间设置, 格式为HH:MM")


class TimeSetInfoPatch(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用")
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
    ] | None = Field(default=None, description="执行周期, 可多选")
    Time: str | None = Field(default=None, description="时间设置, 格式为HH:MM")


class TimeSetRead(ApiModel):
    Info: TimeSetInfoRead = Field(default_factory=TimeSetInfoRead, description="时间项")


class TimeSetPatch(ApiModel):
    Info: TimeSetInfoPatch | None = Field(default=None, description="时间项")


class QueueInfoRead(ApiModel):
    Name: str = Field(default="新队列", description="队列名称")
    TimeEnabled: bool = Field(default=False, description="是否启用定时")
    StartUpEnabled: bool = Field(default=False, description="是否启动时运行")
    AfterAccomplish: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] = Field(default="NoAction", description="完成后操作")


class QueueInfoPatch(ApiModel):
    Name: str | None = Field(default=None, description="队列名称")
    TimeEnabled: bool | None = Field(default=None, description="是否启用定时")
    StartUpEnabled: bool | None = Field(default=None, description="是否启动时运行")
    AfterAccomplish: Literal[
        "NoAction",
        "Shutdown",
        "ShutdownForce",
        "Reboot",
        "Hibernate",
        "Sleep",
        "KillSelf",
    ] | None = Field(default=None, description="完成后操作")


class QueueRead(ApiModel):
    Info: QueueInfoRead = Field(default_factory=QueueInfoRead, description="队列信息")


class QueuePatch(ApiModel):
    Info: QueueInfoPatch | None = Field(default=None, description="队列信息")


class QueueCreateOut(OutBase):
    queueId: str = Field(..., description="新创建的队列ID")
    data: QueueRead = Field(..., description="队列配置数据")


class QueueGetIn(ApiModel):
    queueId: str | None = Field(
        default=None, description="队列ID, 未携带时表示获取所有队列数据"
    )


class QueueGetOut(OutBase):
    index: list[QueueIndexItem] = Field(..., description="队列索引列表")
    data: dict[str, QueueRead] = Field(
        ..., description="队列数据字典, key来自于index列表的uid"
    )


class QueueUpdateIn(ApiModel):
    queueId: str = Field(..., description="队列ID")
    data: QueuePatch = Field(..., description="队列更新数据")


class QueueDeleteIn(ApiModel):
    queueId: str = Field(..., description="队列ID")


class QueueReorderIn(ApiModel):
    indexList: list[str] = Field(..., description="按新顺序排列的调度队列UID列表")


class QueueSetInBase(ApiModel):
    queueId: str = Field(..., description="所属队列ID")


class TimeSetGetIn(QueueSetInBase):
    timeSetId: str | None = Field(
        default=None, description="时间设置ID, 未携带时表示获取所有时间设置数据"
    )


class TimeSetGetOut(OutBase):
    index: list[TimeSetIndexItem] = Field(..., description="时间设置索引列表")
    data: dict[str, TimeSetRead] = Field(
        ..., description="时间设置数据字典, key来自于index列表的uid"
    )


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(..., description="新创建的时间设置ID")
    data: TimeSetRead = Field(..., description="时间设置配置数据")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")
    data: TimeSetPatch = Field(..., description="时间设置更新数据")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: list[str] = Field(..., description="时间设置ID列表, 按新顺序排列")


class QueueItemGetIn(QueueSetInBase):
    queueItemId: str | None = Field(
        default=None, description="队列项ID, 未携带时表示获取所有队列项数据"
    )


class QueueItemGetOut(OutBase):
    index: list[QueueItemIndexItem] = Field(..., description="队列项索引列表")
    data: dict[str, QueueItemRead] = Field(
        ..., description="队列项数据字典, key来自于index列表的uid"
    )


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(..., description="新创建的队列项ID")
    data: QueueItemRead = Field(..., description="队列项配置数据")


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")
    data: QueueItemPatch = Field(..., description="队列项更新数据")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: list[str] = Field(..., description="队列项ID列表, 按新顺序排列")


__all__ = [
    "QueueIndexItem",
    "QueueItemIndexItem",
    "TimeSetIndexItem",
    "QueueItemInfoRead",
    "QueueItemInfoPatch",
    "QueueItemRead",
    "QueueItemPatch",
    "TimeSetInfoRead",
    "TimeSetInfoPatch",
    "TimeSetRead",
    "TimeSetPatch",
    "QueueInfoRead",
    "QueueInfoPatch",
    "QueueRead",
    "QueuePatch",
    "QueueCreateOut",
    "QueueGetIn",
    "QueueGetOut",
    "QueueUpdateIn",
    "QueueDeleteIn",
    "QueueReorderIn",
    "QueueSetInBase",
    "TimeSetGetIn",
    "TimeSetGetOut",
    "TimeSetCreateOut",
    "TimeSetUpdateIn",
    "TimeSetDeleteIn",
    "TimeSetReorderIn",
    "QueueItemGetIn",
    "QueueItemGetOut",
    "QueueItemCreateOut",
    "QueueItemUpdateIn",
    "QueueItemDeleteIn",
    "QueueItemReorderIn",
]
