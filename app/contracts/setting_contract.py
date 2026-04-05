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
    derive_config_contracts,
)


_WebhookReadBase, _WebhookPatchBase = derive_config_contracts(
    Webhook,
    read_name="WebhookRead",
    patch_name="WebhookPatch",
)
_GlobalConfigReadBase, _GlobalConfigPatchBase = derive_config_contracts(
    GlobalConfig,
    read_name="GlobalConfigRead",
    patch_name="GlobalConfigPatch",
    include_groups=("Function", "Voice", "Start", "UI", "Notify", "Update"),
)


class WebhookRead(_WebhookReadBase):
    pass


class WebhookPatch(_WebhookPatchBase):
    pass


class GlobalConfigRead(_GlobalConfigReadBase):
    pass


class GlobalConfigPatch(_GlobalConfigPatchBase):
    pass


class WebhookIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["Webhook"] = Field(..., description="配置类型")


WebhookGetOut = ResourceCollectionOut[WebhookIndexItem, WebhookRead]
WebhookDetailOut = ResourceItemOut[WebhookRead]
WebhookCreateOut = ResourceCreateOut[WebhookRead]
SettingGetOut = ResourceItemOut[GlobalConfigRead]


__all__ = [
    "WebhookRead",
    "WebhookPatch",
    "GlobalConfigRead",
    "GlobalConfigPatch",
    "WebhookIndexItem",
    "WebhookGetOut",
    "WebhookDetailOut",
    "WebhookCreateOut",
    "SettingGetOut",
]
