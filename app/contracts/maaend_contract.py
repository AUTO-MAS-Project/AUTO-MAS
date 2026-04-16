from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contract_model
from app.models.maaend import MaaEndConfig as RuntimeMaaEndConfig
from app.models.maaend import MaaEndUserConfig as RuntimeMaaEndUserConfig


_MaaEndConfigBase = derive_config_contract_model(
    RuntimeMaaEndConfig,
    model_name="MaaEndConfig",
)
_MaaEndUserConfigBase = derive_config_contract_model(
    RuntimeMaaEndUserConfig,
    model_name="MaaEndUserConfig",
)


class MaaEndConfig(_MaaEndConfigBase):
    type: Literal["MaaEndConfig"] = Field(
        default="MaaEndConfig", description="配置类型"
    )


class MaaEndUserConfig(_MaaEndUserConfigBase):
    type: Literal["MaaEndUserConfig"] = Field(
        default="MaaEndUserConfig", description="配置类型"
    )


__all__ = [
    "MaaEndConfig",
    "MaaEndUserConfig",
]
