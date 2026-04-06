from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.common import QueueConfig, QueueItem, TimeSet
from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    derive_config_contract_model,
)


_QueueBase = derive_config_contract_model(
    QueueConfig,
    model_name="QueueRead",
    include_groups=("Info",),
)
_TimeSetBase = derive_config_contract_model(
    TimeSet,
    model_name="TimeSetRead",
    include_groups=("Info",),
)
_QueueItemBase = derive_config_contract_model(
    QueueItem,
    model_name="QueueItemRead",
    include_groups=("Info",),
)


class QueueRead(_QueueBase):
    """队列配置读取/写入模型。"""


class TimeSetRead(_TimeSetBase):
    """时间集合读取/写入模型。"""


class QueueItemRead(_QueueItemBase):
    """任务项读取/写入模型。"""


class QueueIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueConfig"] = Field(..., description="配置类型")


class QueueItemIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueItem"] = Field(..., description="配置类型")


class TimeSetIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["TimeSet"] = Field(..., description="配置类型")


QueueCreateOut = ResourceCreateOut[QueueRead]
QueueDetailOut = ResourceItemOut[QueueRead]
QueueGetOut = ResourceCollectionOut[QueueIndexItem, QueueRead]

TimeSetCreateOut = ResourceCreateOut[TimeSetRead]
TimeSetDetailOut = ResourceItemOut[TimeSetRead]
TimeSetGetOut = ResourceCollectionOut[TimeSetIndexItem, TimeSetRead]

QueueItemCreateOut = ResourceCreateOut[QueueItemRead]
QueueItemDetailOut = ResourceItemOut[QueueItemRead]
QueueItemGetOut = ResourceCollectionOut[QueueItemIndexItem, QueueItemRead]


__all__ = [
    "QueueRead",
    "TimeSetRead",
    "QueueItemRead",
    "QueueIndexItem",
    "QueueItemIndexItem",
    "TimeSetIndexItem",
    "QueueCreateOut",
    "QueueDetailOut",
    "QueueGetOut",
    "TimeSetCreateOut",
    "TimeSetDetailOut",
    "TimeSetGetOut",
    "QueueItemCreateOut",
    "QueueItemDetailOut",
    "QueueItemGetOut",
]
