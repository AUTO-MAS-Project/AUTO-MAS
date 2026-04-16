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


class EmulatorGetOut(ResourceCollectionOut[EmulatorConfigIndexItem, EmulatorRead]):
    """模拟器列表响应模型"""


class EmulatorDetailOut(ResourceItemOut[EmulatorRead]):
    """模拟器详情响应模型"""


class EmulatorCreateOut(ResourceCreateOut[EmulatorRead]):
    """模拟器创建响应模型"""


class EmulatorActionBody(ApiModel):
    index: str = Field(..., description="模拟器索引")


class EmulatorStatusOut(ResourceItemOut[dict[str, dict[str, DeviceInfo]]]):
    """模拟器状态响应模型"""


class EmulatorDeviceStatusOut(ResourceItemOut[dict[str, DeviceInfo]]):
    """模拟器设备状态响应模型"""


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
