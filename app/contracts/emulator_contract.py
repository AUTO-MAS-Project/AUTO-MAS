from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.common import EmulatorConfig
from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    derive_config_contract_model,
)
from app.models.shared import DeviceInfo


_EmulatorBase = derive_config_contract_model(
    EmulatorConfig,
    model_name="EmulatorRead",
    include_groups=("Info",),
)


class EmulatorRead(_EmulatorBase):
    """模拟器配置读取/写入模型。"""


class EmulatorConfigIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["EmulatorConfig"] = Field(..., description="配置类型")


EmulatorGetOut = ResourceCollectionOut[EmulatorConfigIndexItem, EmulatorRead]
EmulatorDetailOut = ResourceItemOut[EmulatorRead]
EmulatorCreateOut = ResourceCreateOut[EmulatorRead]


class EmulatorActionBody(ApiModel):
    index: str = Field(..., description="模拟器索引")


EmulatorStatusOut = ResourceItemOut[dict[str, dict[str, DeviceInfo]]]
EmulatorDeviceStatusOut = ResourceItemOut[dict[str, DeviceInfo]]


class EmulatorSearchResult(ApiModel):
    type: str = Field(..., description="模拟器类型")
    path: str = Field(..., description="模拟器路径")
    name: str = Field(..., description="模拟器名称")


class EmulatorSearchOut(ResourceItemOut[list[EmulatorSearchResult]]):
    data: list[EmulatorSearchResult] = Field(..., description="搜索到的模拟器列表")


__all__ = [
    "EmulatorRead",
    "EmulatorConfigIndexItem",
    "EmulatorGetOut",
    "EmulatorDetailOut",
    "EmulatorCreateOut",
    "EmulatorActionBody",
    "EmulatorStatusOut",
    "EmulatorDeviceStatusOut",
    "EmulatorSearchResult",
    "EmulatorSearchOut",
]
