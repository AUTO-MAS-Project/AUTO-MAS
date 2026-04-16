from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.common import Webhook
from app.models.global_config import GlobalConfig
from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    derive_config_contract_model,
)


_WebhookBase = derive_config_contract_model(
    Webhook,
    model_name="WebhookRead",
)
_GlobalConfigBase = derive_config_contract_model(
    GlobalConfig,
    model_name="GlobalConfigRead",
    include_groups=("Function", "Voice", "Start", "UI", "Notify", "Update"),
)


class WebhookRead(_WebhookBase):
    """Webhook 配置读取/写入模型。"""


class GlobalConfigRead(_GlobalConfigBase):
    """全局配置读取/写入模型。"""


class WebhookIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["Webhook"] = Field(..., description="配置类型")


class WebhookGetOut(ResourceCollectionOut[WebhookIndexItem, WebhookRead]):
    """Webhook 列表响应模型"""


class WebhookDetailOut(ResourceItemOut[WebhookRead]):
    """Webhook 详情响应模型"""


class WebhookCreateOut(ResourceCreateOut[WebhookRead]):
    """Webhook 创建响应模型"""


class SettingGetOut(ResourceItemOut[GlobalConfigRead]):
    """全局设置响应模型"""


__all__ = [
    "WebhookRead",
    "GlobalConfigRead",
    "WebhookIndexItem",
    "WebhookGetOut",
    "WebhookDetailOut",
    "WebhookCreateOut",
    "SettingGetOut",
]
