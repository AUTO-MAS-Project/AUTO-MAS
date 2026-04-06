from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contract_model
from app.models.maa import MaaConfig as RuntimeMaaConfig
from app.models.maa import MaaPlanConfig as RuntimeMaaPlanConfig
from app.models.maa import MaaUserConfig as RuntimeMaaUserConfig


_MaaConfigBase = derive_config_contract_model(
    RuntimeMaaConfig,
    model_name="MaaConfig",
)
_MaaUserConfigBase = derive_config_contract_model(
    RuntimeMaaUserConfig,
    model_name="MaaUserConfig",
)
_MaaPlanConfigBase = derive_config_contract_model(
    RuntimeMaaPlanConfig,
    model_name="MaaPlanConfig",
)


class MaaConfig(_MaaConfigBase):
    type: Literal["MaaConfig"] = Field(default="MaaConfig", description="配置类型")


class MaaUserConfig(_MaaUserConfigBase):
    type: Literal["MaaUserConfig"] = Field(
        default="MaaUserConfig", description="配置类型"
    )


class MaaPlanConfig(_MaaPlanConfigBase):
    type: Literal["MaaPlanConfig"] = Field(
        default="MaaPlanConfig", description="配置类型"
    )


__all__ = [
    "MaaConfig",
    "MaaUserConfig",
    "MaaPlanConfig",
]
