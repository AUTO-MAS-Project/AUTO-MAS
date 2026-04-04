from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import derive_config_contracts
from .src import SrcConfig as RuntimeSrcConfig
from .src import SrcUserConfig as RuntimeSrcUserConfig


_SrcConfigReadBase, _SrcConfigPatchBase = derive_config_contracts(
    RuntimeSrcConfig,
    read_name="SrcConfig",
    patch_name="SrcConfigPatch",
)
_SrcUserConfigReadBase, _SrcUserConfigPatchBase = derive_config_contracts(
    RuntimeSrcUserConfig,
    read_name="SrcUserConfig",
    patch_name="SrcUserConfigPatch",
)


class SrcConfig(_SrcConfigReadBase):
    type: Literal["SrcConfig"] = Field(default="SrcConfig", description="配置类型")


class SrcConfigPatch(_SrcConfigPatchBase):
    type: Literal["SrcConfig"] | None = Field(default=None, description="配置类型")


class SrcUserConfig(_SrcUserConfigReadBase):
    type: Literal["SrcUserConfig"] = Field(
        default="SrcUserConfig", description="配置类型"
    )


class SrcUserConfigPatch(_SrcUserConfigPatchBase):
    type: Literal["SrcUserConfig"] | None = Field(
        default=None, description="配置类型"
    )


__all__ = [
    "SrcConfig",
    "SrcConfigPatch",
    "SrcUserConfig",
    "SrcUserConfigPatch",
]
