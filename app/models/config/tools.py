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

"""工具箱配置：明日方舟 PC 键位与游戏社区签到账号组。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    encrypted,
    ui,
    virtual_field,
)
from app.config.shortcuts import collection
from app.config.types import KeyboardKeyString
from app.utils.constants import UTC8

from .tag import TagItem


class GameSignAccount(ConfigEntry):
    """游戏签到账号组。"""

    class Info(ConfigGroup):
        name: str = Field(default="用户 1", description="账号组名称")
        enabled: bool = Field(default=True, description="是否启用")
        miyoushe_token: Annotated[str, encrypted()] = Field(
            default="", description="米游社登录凭证"
        )
        kuro_token: Annotated[str, encrypted()] = Field(
            default="", description="库街区登录凭证"
        )
        skland_token: Annotated[str, encrypted()] = Field(
            default="", description="森空岛登录凭证"
        )
        last_sign_date: date = Field(
            default=date(2000, 1, 1), description="上次签到日期"
        )

    info: Info = Field(default_factory=Info, description="账号组配置")


class Tools(ConfigEntry):
    """工具箱配置（明日方舟 PC 键位 + 游戏签到）。"""

    class ArknightsPc(ConfigGroup):
        enabled: bool = Field(default=False, description="是否启用 ArknightsPC 工具")
        pause_key: KeyboardKeyString = Field(default="f10", description="暂停键位")
        select_deployed_key: KeyboardKeyString = Field(
            default="w", description="选中已部署干员键位"
        )
        use_skill_key: KeyboardKeyString = Field(
            default="r", description="释放技能键位"
        )
        retreat_key: KeyboardKeyString = Field(default="t", description="撤退键位")
        next_frame_key: KeyboardKeyString = Field(default="f", description="下一帧键位")
        another_quit_key: KeyboardKeyString = Field(
            default="space", description="自定义退出、暂停键位"
        )
        status: Virtual[str] = Field(default=None, description="工具状态 Tag")

    class GameSign(ConfigGroup):
        enabled: bool = Field(default=False, description="是否启用游戏签到")
        notify_enabled: bool = Field(default=False, description="签到后是否发送通知")
        window_start: Annotated[datetime, ui(format="hm")] = Field(
            default=datetime(2000, 1, 1, 8, 0, tzinfo=UTC8),
            description="签到窗口起点 HH:mm",
        )
        window_end: Annotated[datetime, ui(format="hm")] = Field(
            default=datetime(2000, 1, 1, 22, 0, tzinfo=UTC8),
            description="签到窗口终点 HH:mm",
        )
        run_on_startup: bool = Field(default=False, description="启动时运行")
        scheduled_run: bool = Field(default=True, description="定时运行")
        auto_start: bool = Field(default=False, description="是否立即开始")
        last_sign_date: date = Field(
            default=date(2000, 1, 1), description="上次签到日期"
        )
        scheduled_time: str = Field(default="", description="今日计划签到时间")
        status: Virtual[str] = Field(default=None, description="签到状态标签")
        result: Virtual[str] = Field(default=None, description="签到结果 JSON")

    arknights_pc: ArknightsPc = Field(
        default_factory=ArknightsPc, description="明日方舟PC工具配置"
    )
    game_sign: GameSign = Field(
        default_factory=GameSign, description="游戏社区签到配置"
    )
    accounts: ConfigCollection[GameSignAccount] = collection(GameSignAccount)

    # 运行时态（不落盘）：由 ArknightWin32 工具与签到流程回写
    _arknights_pc_running: bool = PrivateAttr(default=False)
    _arknights_pc_get_connected: Callable[[], bool] = PrivateAttr(
        default_factory=lambda: (lambda: False)
    )
    # 形状为 {平台: [账号组结果, ...]}，跨天由 Config 清空
    _game_sign_result_data: dict[str, list[dict[str, Any]]] = PrivateAttr(
        default_factory=dict
    )

    @virtual_field("arknights_pc.status")
    def _arknights_pc_status(self) -> str:
        if not self.arknights_pc.enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        if self._arknights_pc_running:
            if self._arknights_pc_get_connected():
                return TagItem(text="运行中", color="green").model_dump_json()
            return TagItem(text="未连接", color="red").model_dump_json()
        return TagItem(text="已暂停", color="yellow").model_dump_json()

    @virtual_field("game_sign.status")
    def _game_sign_status(self) -> str:
        if not self.game_sign.enabled:
            return TagItem(text="未启用", color="gray").model_dump_json()
        return TagItem(text="已启用", color="green").model_dump_json()

    @virtual_field("game_sign.result")
    def _game_sign_result(self) -> str:
        return json.dumps(self._game_sign_result_data, ensure_ascii=False)

    @property
    def arknights_pc_running(self) -> bool:
        return self._arknights_pc_running

    @arknights_pc_running.setter
    def arknights_pc_running(self, value: bool) -> None:
        self._arknights_pc_running = value

    @property
    def arknights_pc_get_connected(self) -> Callable[[], bool]:
        return self._arknights_pc_get_connected

    @arknights_pc_get_connected.setter
    def arknights_pc_get_connected(self, value: Callable[[], bool]) -> None:
        self._arknights_pc_get_connected = value

    @property
    def arknights_pc_keys(self) -> list[str]:
        pc = self.arknights_pc
        return [
            pc.select_deployed_key,
            pc.use_skill_key,
            pc.retreat_key,
            pc.next_frame_key,
            pc.another_quit_key,
        ]

    @property
    def game_sign_result_data(self) -> dict[str, list[dict[str, Any]]]:
        """签到结果原始数据（供 Config 合并、清理与广播时读写）。"""
        return self._game_sign_result_data
