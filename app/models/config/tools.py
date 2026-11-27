#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigGroup,
    Virtual,
    encrypted,
    tz,
    ui,
    virtual_field,
)
from app.utils import UTC8

from ..schema import TagItem
from .base import DomainEntry


class SignFlowAccountGroup(DomainEntry):
    "游戏社区账号组配置"

    @classmethod
    def normalize_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        """把旧成员键 ``GameSignAccount`` 搬成 ``SignFlowAccount``。

        成员键既是文档字段名也是分组名，改名后旧键会被当成未知字段丢弃，
        成员的凭据与签到日期会退回默认值；激活发生在任何一次加载，所以
        在这里搬而不是只搬文件。显式给出的新键始终优先。
        """

        normalized = super().normalize_payload(data)
        legacy = normalized.pop("GameSignAccount", None)
        if isinstance(legacy, dict) and "SignFlowAccount" not in normalized:
            normalized["SignFlowAccount"] = legacy
        return normalized

    class SignFlowAccountFields(ConfigGroup):
        CloudGenshinToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 云原神 combo token (DPAPI 加密)",
        )
        Enabled: bool = Field(
            default_factory=lambda: True,
            description="SignFlowAccount - 是否启用（该账号是否参与签到）",
        )

        KuroToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 库街区登录凭证 (DPAPI 加密)",
        )
        LastSignDate: Annotated[datetime, tz(UTC8), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC8),
            description="SignFlowAccount - 上次签到日期 (按账号隔离，防止重复触发)",
        )

        MiyousheDeviceFp: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 米游社安卓设备指纹 (DPAPI 加密，仅用于绝区零便笺)",
        )
        MiyousheDeviceId: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 米游社安卓设备 ID (DPAPI 加密，仅用于绝区零便笺)",
        )
        MiyousheToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 米游社登录凭证 (DPAPI 加密)",
        )
        Name: str = Field(
            default_factory=lambda: "账号 1", description="SignFlowAccount - 账号组名称"
        )

        SklandToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 森空岛登录凭证 (DPAPI 加密)",
        )
        TaygedoToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="SignFlowAccount - 塔吉多及云异环登录凭证 (DPAPI 加密) 支持 refreshToken 纯文本或包含 cloudToken/cloudUserId 的 JSON。",
        )

    SignFlowAccount: SignFlowAccountFields = Field(
        default_factory=SignFlowAccountFields
    )


class ToolsConfig(DomainEntry):
    "工具配置"

    @classmethod
    def normalize_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        """把旧分组 ``GameSign`` 搬成 ``SignFlow``。

        分组名同时是文档键与虚拟字段路径，改名后旧文档里的键会被忽略成默认
        值（签到开关、便笺开关都会掉回默认）。激活发生在任何一次加载，所以
        在这里搬而不是只搬文件。显式给出的新分组始终优先。
        """

        normalized = super().normalize_payload(data)
        legacy = normalized.pop("GameSign", None)
        if isinstance(legacy, dict) and "SignFlow" not in normalized:
            normalized["SignFlow"] = legacy
        return normalized

    class SignFlowFields(ConfigGroup):
        ActivityEnabled: bool = Field(
            default_factory=lambda: True, description="SignFlow - 启用日常便笺"
        )

        AutoStart: bool = Field(
            default_factory=lambda: False, description="SignFlow - 是否立即开始"
        )

        Enabled: bool = Field(
            default_factory=lambda: False, description="SignFlow - 启用签到"
        )

        LastSignDate: Annotated[datetime, tz(UTC8), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC8),
            description="SignFlow - 上次签到日期 (防止重复触发)",
        )

        NotifyEnabled: bool = Field(
            default_factory=lambda: False, description="SignFlow - 签到后发送通知"
        )

        Result: Virtual[str] = Field(
            default_factory=lambda: None,
            description="SignFlow - 签到结果详情 (虚拟字段)",
        )
        RunOnStartup: bool = Field(
            default_factory=lambda: False, description="SignFlow - 启动时运行"
        )

        Status: Virtual[str] = Field(
            default_factory=lambda: None,
            description="SignFlow - 签到状态标签 (虚拟字段)",
        )

    SignFlow: SignFlowFields = Field(default_factory=SignFlowFields)
    _sign_flow_accounts: ConfigCollection[SignFlowAccountGroup] = PrivateAttr(
        default_factory=lambda: ConfigCollection[SignFlowAccountGroup].build(
            [SignFlowAccountGroup]
        )
    )

    @property
    def SignFlow_Accounts(self) -> ConfigCollection[SignFlowAccountGroup]:
        return self._sign_flow_accounts

    _sign_flow_result_data: dict = PrivateAttr(default_factory=dict)

    def sign_flow_status(self) -> str:
        """游戏社区状态标签"""
        if not self.SignFlow.Enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        return TagItem(text="已启用", color="green").model_dump_json()

    def sign_flow_result(self) -> str:
        """游戏社区结果 JSON"""
        return json.dumps(self._sign_flow_result_data, ensure_ascii=False)

    @virtual_field("SignFlow.Result")
    def compute_SignFlow_Result(self):
        try:
            return self.sign_flow_result()
        except Exception as exc:
            return str(exc)

    @virtual_field("SignFlow.Status")
    def compute_SignFlow_Status(self):
        try:
            return self.sign_flow_status()
        except Exception as exc:
            return str(exc)


__all__ = ["SignFlowAccountGroup", "ToolsConfig"]
