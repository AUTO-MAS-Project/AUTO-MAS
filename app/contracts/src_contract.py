from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contract_model
from app.models.src import SrcConfig as RuntimeSrcConfig
from app.models.src import SrcUserConfig as RuntimeSrcUserConfig


_SrcConfigBase = derive_config_contract_model(
    RuntimeSrcConfig,
    model_name="SrcConfig",
)
_SrcUserConfigBase = derive_config_contract_model(
    RuntimeSrcUserConfig,
    model_name="SrcUserConfig",
)


class SrcConfig(_SrcConfigBase):
    type: Literal["SrcConfig"] = Field(default="SrcConfig", description="配置类型")


class SrcUserConfig(_SrcUserConfigBase):
    type: Literal["SrcUserConfig"] = Field(
        default="SrcUserConfig", description="配置类型"
    )


__all__ = [
    "SrcConfig",
    "SrcUserConfig",
]
