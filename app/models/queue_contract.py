from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import QueueConfig, QueueItem, TimeSet
from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    derive_config_contracts,
)


_QueueReadBase, _QueuePatchBase = derive_config_contracts(
    QueueConfig,
    read_name="QueueRead",
    patch_name="QueuePatch",
    include_groups=("Info",),
)
_TimeSetReadBase, _TimeSetPatchBase = derive_config_contracts(
    TimeSet,
    read_name="TimeSetRead",
    patch_name="TimeSetPatch",
    include_groups=("Info",),
)
_QueueItemReadBase, _QueueItemPatchBase = derive_config_contracts(
    QueueItem,
    read_name="QueueItemRead",
    patch_name="QueueItemPatch",
    include_groups=("Info",),
)


class QueueRead(_QueueReadBase):
    pass


class QueuePatch(_QueuePatchBase):
    pass


class TimeSetRead(_TimeSetReadBase):
    pass


class TimeSetPatch(_TimeSetPatchBase):
    pass


class QueueItemRead(_QueueItemReadBase):
    pass


class QueueItemPatch(_QueueItemPatchBase):
    pass


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
    "QueuePatch",
    "TimeSetRead",
    "TimeSetPatch",
    "QueueItemRead",
    "QueueItemPatch",
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
