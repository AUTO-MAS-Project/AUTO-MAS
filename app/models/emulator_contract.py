from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase
from .shared import DeviceInfo


class EmulatorConfigIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["EmulatorConfig"] = Field(..., description="配置类型")


class EmulatorInfoRead(ApiModel):
    Name: str = Field(default="新模拟器", description="模拟器名称")
    Type: Literal["general", "mumu", "ldplayer"] = Field(
        default="general", description="模拟器类型"
    )
    Path: str = Field(default="", description="模拟器路径")
    BossKey: str = Field(default="[ ]", description="老板键快捷键配置")
    MaxWaitTime: int = Field(default=60, description="最大等待时间（秒）")


class EmulatorInfoPatch(ApiModel):
    Name: str | None = Field(default=None, description="模拟器名称")
    Type: Literal["general", "mumu", "ldplayer"] | None = Field(
        default=None, description="模拟器类型"
    )
    Path: str | None = Field(default=None, description="模拟器路径")
    BossKey: str | None = Field(default=None, description="老板键快捷键配置")
    MaxWaitTime: int | None = Field(default=None, description="最大等待时间（秒）")


class EmulatorRead(ApiModel):
    Info: EmulatorInfoRead = Field(
        default_factory=EmulatorInfoRead, description="模拟器基础信息"
    )


class EmulatorPatch(ApiModel):
    Info: EmulatorInfoPatch | None = Field(default=None, description="模拟器基础信息")


class EmulatorGetIn(ApiModel):
    emulatorId: str | None = Field(
        default=None, description="模拟器ID, 未携带时表示获取所有模拟器数据"
    )


class EmulatorGetOut(OutBase):
    index: list[EmulatorConfigIndexItem] = Field(..., description="模拟器索引列表")
    data: dict[str, EmulatorRead] = Field(
        ..., description="模拟器数据字典, key来自于index列表的uid"
    )


class EmulatorCreateOut(OutBase):
    emulatorId: str = Field(..., description="新创建的模拟器 ID")
    data: EmulatorRead = Field(..., description="模拟器配置数据")


class EmulatorUpdateIn(ApiModel):
    emulatorId: str = Field(..., description="模拟器 ID")
    data: EmulatorPatch = Field(..., description="模拟器更新数据")


class EmulatorDeleteIn(ApiModel):
    emulatorId: str = Field(..., description="模拟器 ID")


class EmulatorReorderIn(ApiModel):
    indexList: list[str] = Field(..., description="模拟器 ID列表, 按新顺序排列")


class EmulatorOperateIn(ApiModel):
    emulatorId: str = Field(..., description="模拟器 ID")
    operate: Literal["open", "close", "show"] = Field(..., description="操作类型")
    index: str = Field(..., description="模拟器索引")


class EmulatorStatusOut(OutBase):
    data: dict[str, dict[str, DeviceInfo]] = Field(
        ...,
        description="模拟器状态信息, 外层key为模拟器ID, 内层key为设备索引, value为设备信息",
    )


class EmulatorSearchResult(ApiModel):
    type: str = Field(..., description="模拟器类型")
    path: str = Field(..., description="模拟器路径")
    name: str = Field(..., description="模拟器名称")


class EmulatorSearchOut(OutBase):
    emulators: list[EmulatorSearchResult] = Field(..., description="搜索到的模拟器列表")


__all__ = [
    "EmulatorConfigIndexItem",
    "EmulatorInfoRead",
    "EmulatorInfoPatch",
    "EmulatorRead",
    "EmulatorPatch",
    "EmulatorGetIn",
    "EmulatorGetOut",
    "EmulatorCreateOut",
    "EmulatorUpdateIn",
    "EmulatorDeleteIn",
    "EmulatorReorderIn",
    "EmulatorOperateIn",
    "EmulatorStatusOut",
    "EmulatorSearchResult",
    "EmulatorSearchOut",
]
