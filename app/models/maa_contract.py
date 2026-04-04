from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contracts
from .maa import MaaConfig as RuntimeMaaConfig
from .maa import MaaPlanConfig as RuntimeMaaPlanConfig
from .maa import MaaUserConfig as RuntimeMaaUserConfig


_MaaConfigReadBase, _MaaConfigPatchBase = derive_config_contracts(
    RuntimeMaaConfig,
    read_name="MaaConfig",
    patch_name="MaaConfigPatch",
)
_MaaUserConfigReadBase, _MaaUserConfigPatchBase = derive_config_contracts(
    RuntimeMaaUserConfig,
    read_name="MaaUserConfig",
    patch_name="MaaUserConfigPatch",
)
_MaaPlanConfigReadBase, _MaaPlanPatchBase = derive_config_contracts(
    RuntimeMaaPlanConfig,
    read_name="MaaPlanConfig",
    patch_name="MaaPlanPatch",
)


class MaaConfig(_MaaConfigReadBase):
    type: Literal["MaaConfig"] = Field(default="MaaConfig", description="配置类型")


class MaaConfigPatch(_MaaConfigPatchBase):
    type: Literal["MaaConfig"] | None = Field(default=None, description="配置类型")


class MaaUserConfig(_MaaUserConfigReadBase):
    type: Literal["MaaUserConfig"] = Field(
        default="MaaUserConfig", description="配置类型"
    )


class MaaUserConfigPatch(_MaaUserConfigPatchBase):
    type: Literal["MaaUserConfig"] | None = Field(
        default=None, description="配置类型"
    )


class MaaPlanConfig(_MaaPlanConfigReadBase):
    type: Literal["MaaPlanConfig"] = Field(
        default="MaaPlanConfig", description="配置类型"
    )


class MaaPlanPatch(_MaaPlanPatchBase):
    type: Literal["MaaPlanConfig"] | None = Field(
        default=None, description="配置类型"
    )


__all__ = [
    "MaaConfig",
    "MaaConfigPatch",
    "MaaUserConfig",
    "MaaUserConfigPatch",
    "MaaPlanConfig",
    "MaaPlanPatch",
]
