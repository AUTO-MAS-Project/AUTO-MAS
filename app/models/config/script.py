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

"""脚本与用户配置上界；脚本适配插件继承后扩展专项字段。"""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from pydantic import Field, ValidationInfo, field_validator

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    NodeState,
    Trigger,
    Virtual,
    config_manager,
    virtual_field,
)
from app.config.fields import RefDeleteAction
from app.config.shortcuts import collection, ref, trigger_field
from app.config.signals import CollectionChangeEvent, FieldChangeEvent

from .game import device_removed
from .tag import TagItem


class UserEntry(ConfigEntry):
    """用户配置上界：插件子类扩展；删用户时由宿主订阅清本地 data/。"""

    class Info(ConfigGroup):
        name: str = Field(default="新用户", description="用户名")
        enabled: bool = Field(default=True, description="是否启用")
        config_path: str = Field(default="", description="配置文件来源路径")
        # 代理情况（专项可扩展字段；基类仅保留日代理摘要）
        proxy_status: str = Field(default="", description="代理情况摘要")
        # 人工排查：结果 + 一键通过 Trigger
        review_passed: bool = Field(default=False, description="人工排查是否通过")
        pass_review: Trigger = Field(
            default=False, description="人工排查置为通过（写 True 开闸）"
        )
        last_result: str = Field(default="", description="上次任务结果记录")
        # 计划表选择：存 PlanEntry.uid；选项走 /api/info/combox/plan（禁 ref name=）
        plan_id: str = Field(default="-", description="关联计划表 uid；- 表示未选")
        tags: Virtual[list[TagItem]] = None

    info: Info = Field(default_factory=Info, description="用户信息")

    @trigger_field("info.pass_review")
    async def on_pass_review(self) -> None:
        """将人工排查结果置为通过。"""
        self.info.review_passed = True
        await self.commit()

    @virtual_field("info.tags")
    def compute_tags(self) -> list[TagItem]:
        """基类 tag：代理情况 + 人工排查；子类可覆盖补全。"""
        tags: list[TagItem] = []
        proxy = (self.info.proxy_status or "").strip()
        if proxy:
            tags.append(TagItem(text=f"代理：{proxy}", color="blue"))
        else:
            tags.append(TagItem(text="代理：未记录", color="orange"))
        if self.info.review_passed:
            tags.append(TagItem(text="人工排查：通过", color="green"))
        else:
            tags.append(TagItem(text="人工排查：未通过", color="red"))
        return tags


class ScriptEntry(ConfigEntry):
    """脚本配置上界：至少脚本名 + 游戏选择；users 由适配器挂具体 user_type。"""

    class Info(ConfigGroup):
        name: str = Field(default="新脚本", description="脚本名称")
        # 游戏：games 池外键；游戏被删 → 置 "-"
        game_id: Annotated[
            UUID | str,
            ref("games", default="-", on_delete=RefDeleteAction.SET_DEFAULT),
        ] = Field(default="-", description="关联游戏配置 uid；- 表示未选")
        # 设备：不走外键，由下方校验器按所选游戏的 devices 归一；须声明在 game_id 之后
        game_device_id: UUID | str = Field(
            default="-", description="关联游戏设备 uid；- 表示只订游戏不订实例"
        )

        @field_validator("game_device_id")
        @classmethod
        def _normalize_device(
            cls, value: UUID | str, info: ValidationInfo
        ) -> UUID | str:
            """热态：仅保留所选游戏 devices 内的 uid，否则 ``-``；冷态原样。"""
            entry = (info.context or {}).get("entry")
            if entry is None or entry.activation_state == NodeState.INACTIVE:
                return value
            # info.data 为同组其它字段的当前值（赋值校验时即工作区里的 game_id）
            game_id = info.data.get("game_id")
            try:
                uid = value if isinstance(value, UUID) else UUID(value)
                game = config_manager.get_collection("games").get(UUID(str(game_id)))
            except ValueError:
                return "-"
            if game is None or uid not in game.devices:
                return "-"
            return uid

    info: Info = Field(default_factory=Info, description="脚本信息")
    users: ConfigCollection[UserEntry] = collection(UserEntry)

    @staticmethod
    async def on_add_script(sender: object, event: CollectionChangeEvent) -> None:
        """ScriptConfig 实例级 add / init_add：订本脚本的 ``game_id`` 变更。

        各子类信号独立，类级订阅覆盖不到插件子类，故按实例订。
        """
        _ = sender
        if not isinstance(event.entry, ScriptEntry):
            raise TypeError(f"非 ScriptEntry: {event.entry}")
        event.entry.connect(
            ScriptEntry.on_game_changed, phase="runtime", group="info", field="game_id"
        )

    @staticmethod
    async def on_game_changed(sender: object, event: FieldChangeEvent) -> None:
        """``game_id`` 变更（含游戏被删置 ``-``）：设备原值重赋，按新游戏重新归一。"""
        _ = event
        entry = cast(ScriptEntry, sender)
        device = entry.info.game_device_id
        if device == "-":
            return
        entry.info.game_device_id = device
        await entry.commit()

    @staticmethod
    async def on_device_removed(sender: object, uid: UUID) -> None:
        """统一设备删除信号：引用该设备的脚本原值重赋，交给校验器归一为 ``-``。"""
        _ = sender
        for entry in config_manager.get_collection("scripts").values():
            if entry.info.game_device_id != uid:
                continue
            entry.info.game_device_id = uid
            await entry.commit()


device_removed.connect(ScriptEntry.on_device_removed)
