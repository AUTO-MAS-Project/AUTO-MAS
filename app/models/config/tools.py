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
from typing import Annotated, Callable

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
from app.config.types import KeyboardKeyString
from app.utils.constants import UTC8

from ..schema import TagItem
from .base import DomainEntry


class GameSignAccountGroup(DomainEntry):
    "游戏社区账号组配置"

    class GameSignAccountFields(ConfigGroup):
        CloudGenshinToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 云原神 combo token (DPAPI 加密)",
        )
        Enabled: bool = Field(
            default_factory=lambda: True,
            description="GameSignAccount - 是否启用（该用户是否参与签到）",
        )

        KuroToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 库街区登录凭证 (DPAPI 加密)",
        )
        LastSignDate: Annotated[datetime, tz(UTC8), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC8),
            description="GameSignAccount - 上次签到日期 (按用户隔离，防止重复触发)",
        )

        MiyousheDeviceFp: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 米游社安卓设备指纹 (DPAPI 加密，仅用于绝区零便笺)",
        )
        MiyousheDeviceId: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 米游社安卓设备 ID (DPAPI 加密，仅用于绝区零便笺)",
        )
        MiyousheToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 米游社登录凭证 (DPAPI 加密)",
        )
        Name: str = Field(
            default_factory=lambda: "用户 1", description="GameSignAccount - 账号组名称"
        )

        SklandToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 森空岛登录凭证 (DPAPI 加密)",
        )
        TaygedoToken: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="GameSignAccount - 塔吉多及云异环登录凭证 (DPAPI 加密) 支持 refreshToken 纯文本或包含 cloudToken/cloudUserId 的 JSON。",
        )

    GameSignAccount: GameSignAccountFields = Field(
        default_factory=GameSignAccountFields
    )


class ToolsConfig(DomainEntry):
    "工具配置"

    class ArknightsPCFields(ConfigGroup):
        AnotherQuitKey: KeyboardKeyString = Field(
            description="自定义退出、暂停键位", default_factory=lambda: "space"
        )

        Enabled: bool = Field(
            description="是否启用 ArknightsPC 工具", default_factory=lambda: False
        )

        NextFrameKey: KeyboardKeyString = Field(
            description="下一帧键位", default_factory=lambda: "f"
        )

        PauseKey: KeyboardKeyString = Field(
            description="暂停键位", default_factory=lambda: "f10"
        )

        RetreatKey: KeyboardKeyString = Field(
            description="撤退键位", default_factory=lambda: "t"
        )

        SelectDeployedKey: KeyboardKeyString = Field(
            description="选中已部署干员键位", default_factory=lambda: "w"
        )

        Status: Virtual[str] = Field(
            description="工具状态 Tag", default_factory=lambda: None
        )
        UseSkillKey: KeyboardKeyString = Field(
            description="释放技能键位", default_factory=lambda: "r"
        )

    ArknightsPC: ArknightsPCFields = Field(default_factory=ArknightsPCFields)

    class GameSignFields(ConfigGroup):
        ActivityEnabled: bool = Field(
            default_factory=lambda: True, description="GameSign - 启用日常便笺"
        )

        AutoStart: bool = Field(
            default_factory=lambda: False, description="GameSign - 是否立即开始"
        )

        Enabled: bool = Field(
            default_factory=lambda: False, description="GameSign - 启用签到"
        )

        LastSignDate: Annotated[datetime, tz(UTC8), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC8),
            description="GameSign - 上次签到日期 (防止重复触发)",
        )

        NotifyEnabled: bool = Field(
            default_factory=lambda: False, description="GameSign - 签到后发送通知"
        )

        Result: Virtual[str] = Field(
            default_factory=lambda: None,
            description="GameSign - 签到结果详情 (虚拟字段)",
        )
        RunOnStartup: bool = Field(
            default_factory=lambda: False, description="GameSign - 启动时运行"
        )

        Status: Virtual[str] = Field(
            default_factory=lambda: None,
            description="GameSign - 签到状态标签 (虚拟字段)",
        )

    GameSign: GameSignFields = Field(default_factory=GameSignFields)
    _game_sign_accounts: ConfigCollection = PrivateAttr(
        default_factory=lambda: ConfigCollection.build([GameSignAccountGroup])
    )

    @property
    def GameSign_Accounts(self) -> ConfigCollection:
        return self._game_sign_accounts

    arknights_pc_running: bool = Field(default=False, exclude=True)
    arknights_pc_get_connected: Callable = Field(default=lambda: False, exclude=True)
    _game_sign_result_data: dict = PrivateAttr(default_factory=dict)

    @property
    def arknights_pc_connected(self) -> bool:
        return self.arknights_pc_get_connected()

    def arknights_pc_status(self) -> str:
        if not self.ArknightsPC.Enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        elif self.arknights_pc_running:
            if self.arknights_pc_connected:
                return TagItem(text="运行中", color="green").model_dump_json()
            else:
                return TagItem(text="未连接", color="red").model_dump_json()
        else:
            return TagItem(text="已暂停", color="yellow").model_dump_json()

    @property
    def arknights_pc_keys(self) -> list[str]:
        """获取明日方舟 PC 按键配置"""
        return [
            getattr(self.ArknightsPC, _)
            for _ in (
                "SelectDeployedKey",
                "UseSkillKey",
                "RetreatKey",
                "NextFrameKey",
                "AnotherQuitKey",
            )
        ]

    def game_sign_status(self) -> str:
        """游戏社区状态标签"""
        if not self.GameSign.Enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        return TagItem(text="已启用", color="green").model_dump_json()

    def game_sign_result(self) -> str:
        """游戏社区结果 JSON"""
        return json.dumps(self._game_sign_result_data, ensure_ascii=False)

    @virtual_field("ArknightsPC.Status")
    def compute_ArknightsPC_Status(self):
        try:
            return self.arknights_pc_status()
        except Exception as exc:
            return str(exc)

    @virtual_field("GameSign.Result")
    def compute_GameSign_Result(self):
        try:
            return self.game_sign_result()
        except Exception as exc:
            return str(exc)

    @virtual_field("GameSign.Status")
    def compute_GameSign_Status(self):
        try:
            return self.game_sign_status()
        except Exception as exc:
            return str(exc)


__all__ = ["GameSignAccountGroup", "ToolsConfig"]
