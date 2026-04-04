from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contracts
from .maaend import MaaEndConfig as RuntimeMaaEndConfig
from .maaend import MaaEndUserConfig as RuntimeMaaEndUserConfig


_MaaEndConfigReadBase, _MaaEndConfigPatchBase = derive_config_contracts(
    RuntimeMaaEndConfig,
    read_name="MaaEndConfig",
    patch_name="MaaEndConfigPatch",
)
_MaaEndUserConfigReadBase, _MaaEndUserConfigPatchBase = derive_config_contracts(
    RuntimeMaaEndUserConfig,
    read_name="MaaEndUserConfig",
    patch_name="MaaEndUserConfigPatch",
)


class MaaEndConfig(_MaaEndConfigReadBase):
    type: Literal["MaaEndConfig"] = Field(
        default="MaaEndConfig", description="配置类型"
    )


class MaaEndConfigPatch(_MaaEndConfigPatchBase):
    type: Literal["MaaEndConfig"] | None = Field(
        default=None, description="配置类型"
    )


class MaaEndUserConfig(_MaaEndUserConfigReadBase):
    type: Literal["MaaEndUserConfig"] = Field(
        default="MaaEndUserConfig", description="配置类型"
    )


class MaaEndUserConfigPatch(_MaaEndUserConfigPatchBase):
    type: Literal["MaaEndUserConfig"] | None = Field(
        default=None, description="配置类型"
    )


__all__ = [
    "MaaEndConfig",
    "MaaEndConfigPatch",
    "MaaEndUserConfig",
    "MaaEndUserConfigPatch",
]
