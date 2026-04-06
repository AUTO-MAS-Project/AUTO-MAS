from __future__ import annotations

from .common_contract import ResourceItemOut, derive_config_contract_model
from app.models.global_config import ToolsConfig


_ToolsConfigBase = derive_config_contract_model(
    ToolsConfig,
    model_name="ToolsConfigRead",
)


class ToolsConfigRead(_ToolsConfigBase):
    """工具配置读取/写入模型。"""


ToolsGetOut = ResourceItemOut[ToolsConfigRead]


__all__ = [
    "ToolsConfigRead",
    "ToolsGetOut",
]
