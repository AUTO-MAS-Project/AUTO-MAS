from __future__ import annotations

from pydantic import Field

from .common_contract import ApiModel, OutBase


class UpdateCheckIn(ApiModel):
    current_version: str = Field(..., description="当前前端版本号")
    if_force: bool = Field(default=False, description="是否强制拉取更新信息")


class UpdateCheckOut(OutBase):
    if_need_update: bool = Field(..., description="是否需要更新前端")
    latest_version: str = Field(..., description="最新前端版本号")
    update_info: dict[str, list[str]] = Field(..., description="版本更新信息字典")


__all__ = ["UpdateCheckIn", "UpdateCheckOut"]
