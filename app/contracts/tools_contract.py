from __future__ import annotations

from .common_contract import ResourceItemOut, derive_config_contracts
from app.models.global_config import ToolsConfig


_ToolsConfigReadBase, _ToolsConfigPatchBase = derive_config_contracts(
    ToolsConfig,
    read_name="ToolsConfigRead",
    patch_name="ToolsConfigPatch",
)


class ToolsConfigRead(_ToolsConfigReadBase):
    pass


class ToolsConfigPatch(_ToolsConfigPatchBase):
    pass


ToolsGetOut = ResourceItemOut[ToolsConfigRead]


__all__ = [
    "ToolsConfigRead",
    "ToolsConfigPatch",
    "ToolsGetOut",
]
