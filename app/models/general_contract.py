from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contracts
from .general import GeneralConfig as RuntimeGeneralConfig
from .general import GeneralUserConfig as RuntimeGeneralUserConfig


_GeneralConfigReadBase, _GeneralConfigPatchBase = derive_config_contracts(
    RuntimeGeneralConfig,
    read_name="GeneralConfig",
    patch_name="GeneralConfigPatch",
)
_GeneralUserConfigReadBase, _GeneralUserConfigPatchBase = derive_config_contracts(
    RuntimeGeneralUserConfig,
    read_name="GeneralUserConfig",
    patch_name="GeneralUserConfigPatch",
)


class GeneralConfig(_GeneralConfigReadBase):
    type: Literal["GeneralConfig"] = Field(
        default="GeneralConfig", description="配置类型"
    )


class GeneralConfigPatch(_GeneralConfigPatchBase):
    type: Literal["GeneralConfig"] = Field(
        default="GeneralConfig", description="配置类型"
    )


class GeneralUserConfig(_GeneralUserConfigReadBase):
    type: Literal["GeneralUserConfig"] = Field(
        default="GeneralUserConfig", description="配置类型"
    )


class GeneralUserConfigPatch(_GeneralUserConfigPatchBase):
    type: Literal["GeneralUserConfig"] = Field(
        default="GeneralUserConfig", description="配置类型"
    )


__all__ = [
    "GeneralConfig",
    "GeneralConfigPatch",
    "GeneralUserConfig",
    "GeneralUserConfigPatch",
]
