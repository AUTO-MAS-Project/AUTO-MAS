from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contract_model
from app.models.general import GeneralConfig as RuntimeGeneralConfig
from app.models.general import GeneralUserConfig as RuntimeGeneralUserConfig


_GeneralConfigBase = derive_config_contract_model(
    RuntimeGeneralConfig,
    model_name="GeneralConfig",
)
_GeneralUserConfigBase = derive_config_contract_model(
    RuntimeGeneralUserConfig,
    model_name="GeneralUserConfig",
)


class GeneralConfig(_GeneralConfigBase):
    type: Literal["GeneralConfig"] = Field(
        default="GeneralConfig", description="配置类型"
    )


class GeneralUserConfig(_GeneralUserConfigBase):
    type: Literal["GeneralUserConfig"] = Field(
        default="GeneralUserConfig", description="配置类型"
    )


__all__ = [
    "GeneralConfig",
    "GeneralUserConfig",
]
