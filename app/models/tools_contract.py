from __future__ import annotations

from pydantic import Field

from .common_contract import ApiModel, OutBase


class ToolsConfigArknightsPCRead(ApiModel):
    Enabled: bool = Field(default=False, description="是否启用 ArknightsPC 工具")
    PauseKey: str = Field(default="f10", description="暂停键位")
    SelectDeployedKey: str = Field(default="w", description="选中已部署干员键位")
    UseSkillKey: str = Field(default="r", description="释放技能键位")
    RetreatKey: str = Field(default="t", description="撤退键位")
    NextFrameKey: str = Field(default="f", description="下一帧键位")
    AnotherQuitKey: str = Field(default="space", description="自定义退出、暂停键位")
    Status: str = Field(default="-", description="工具状态 Tag")


class ToolsConfigArknightsPCPatch(ApiModel):
    Enabled: bool | None = Field(default=None, description="是否启用 ArknightsPC 工具")
    PauseKey: str | None = Field(default=None, description="暂停键位")
    SelectDeployedKey: str | None = Field(default=None, description="选中已部署干员键位")
    UseSkillKey: str | None = Field(default=None, description="释放技能键位")
    RetreatKey: str | None = Field(default=None, description="撤退键位")
    NextFrameKey: str | None = Field(default=None, description="下一帧键位")
    AnotherQuitKey: str | None = Field(default=None, description="自定义退出、暂停键位")


class ToolsConfigRead(ApiModel):
    ArknightsPC: ToolsConfigArknightsPCRead = Field(
        default_factory=ToolsConfigArknightsPCRead, description="明日方舟PC工具配置"
    )


class ToolsConfigPatch(ApiModel):
    ArknightsPC: ToolsConfigArknightsPCPatch | None = Field(
        default=None, description="明日方舟PC工具配置"
    )


class ToolsGetOut(OutBase):
    data: ToolsConfigRead = Field(..., description="工具配置数据")


class ToolsUpdateIn(ApiModel):
    data: ToolsConfigPatch = Field(..., description="工具配置需要更新的数据")


__all__ = [
    "ToolsConfigArknightsPCRead",
    "ToolsConfigArknightsPCPatch",
    "ToolsConfigRead",
    "ToolsConfigPatch",
    "ToolsGetOut",
    "ToolsUpdateIn",
]
