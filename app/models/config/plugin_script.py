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

from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import Field, ValidationInfo, field_validator

from app.config import (
    ConfigCollection,
    ConfigGroup,
    NodeState,
    Virtual,
    config_manager,
    virtual_field,
)
from app.config.fields import RefDeleteAction
from app.config.shortcuts import collection, ref, select, ui
from app.config.signals import FieldChangeEvent
from app.plugin.config import PluginCommandEntry

from .game import device_removed
from .plan import PlanEntry
from .queue import Webhook
from .tag import TagItem


class UserEntry(PluginCommandEntry):
    """用户配置上界：插件子类扩展；删用户时由宿主订阅清本地 data/。"""

    class Info(ConfigGroup):
        name: str = Field(default="新用户", description="用户名")
        enabled: bool = Field(default=True, description="是否启用")
        config_path: str = Field(default="", description="配置文件来源路径")
        mode: Annotated[Literal["脚本", "用户", "直控"], select()] = Field(
            default="脚本", description="配置来源"
        )
        if_quick_config: bool = Field(default=True, description="覆写常规配置")
        # 代理情况（专项可扩展字段；基类仅保留日代理摘要）
        proxy_status: str = Field(default="", description="代理情况摘要")
        last_result: str = Field(default="", description="上次任务结果记录")
        # 计划表选择：存 PlanEntry.uid；选项走 /api/plugin/options/plans（禁 ref name=）
        plan_id: Annotated[
            UUID | str,
            select(endpoint="/api/plugin/options/plans"),
            ref("PlanConfig", default="-", entry_types=(PlanEntry,)),
        ] = Field(default="-", description="关联计划表 uid；- 表示未选")
        tags: Virtual[list[TagItem]] = None

    class Notify(ConfigGroup):
        """用户独立通知策略；专项继承后可补充自身报告选项。"""

        enabled: bool = Field(default=False, description="是否启用用户通知")
        if_send_statistic: bool = Field(default=False, description="是否发送统计信息")
        if_send_six_star: bool = Field(default=False, description="是否发送六星通知")
        if_send_mail: bool = Field(default=False, description="是否发送邮件通知")
        to_address: str = Field(default="", description="邮件接收地址")
        if_server_chan: bool = Field(default=False, description="是否启用 Server 酱")
        server_chan_key: Annotated[str, ui(secret=True)] = Field(
            default="", description="Server 酱推送密钥"
        )

    info: Info = Field(default_factory=Info, description="用户信息")
    notify: Notify = Field(default_factory=Notify, description="用户通知")
    custom_webhooks: ConfigCollection[Webhook] = collection(Webhook)

    @virtual_field("info.tags")
    def compute_tags(self) -> list[TagItem]:
        """代理摘要标签；专项可扩展自己的结果展示。"""
        tags: list[TagItem] = []
        proxy = (self.info.proxy_status or "").strip()
        if proxy:
            tags.append(TagItem(text=f"代理：{proxy}", color="blue"))
        else:
            tags.append(TagItem(text="代理：未记录", color="orange"))
        return tags


class ScriptEntry(PluginCommandEntry):
    """脚本配置上界：至少脚本名 + 游戏选择；users 由适配器挂具体 user_type。"""

    class Info(ConfigGroup):
        name: str = Field(default="新脚本", description="脚本名称")
        # 游戏：games 池外键；游戏被删 → 置 "-"
        game_id: Annotated[
            UUID | str,
            select(endpoint="/api/plugin/options/games"),
            ref("games", default="-", on_delete=RefDeleteAction.SET_DEFAULT),
        ] = Field(default="-", description="关联游戏配置 uid；- 表示未选")
        # 设备：不走外键，由下方校验器按所选游戏的 devices 归一；须声明在 game_id 之后
        game_device_id: Annotated[
            UUID | str,
            select(endpoint="/api/plugin/options/devices"),
            ui(deps=["info.game_id"]),
        ] = Field(default="-", description="关联游戏设备 uid；- 表示只订游戏不订实例")

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

    def get_emulator_binding(self) -> tuple[str | UUID, str] | None:
        """[兼容旧模拟器] 提供设备反查所需的只读绑定；游戏设备迁移完成后删除。"""
        return None

    @classmethod
    def bind_runtime_signals(cls) -> None:
        """在插件类型登记时订阅本类实例的游戏引用联动，避免在成员激活期间修改生命周期。"""
        cls.disconnect(
            ScriptEntry.on_game_changed, phase="runtime", group="info", field="game_id"
        )
        cls.connect(
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
        for entry in config_manager.get_collection("ScriptConfig").values():
            if not isinstance(entry, ScriptEntry):
                continue
            if entry.info.game_device_id != uid:
                continue
            entry.info.game_device_id = uid
            await entry.commit()


device_removed.connect(ScriptEntry.on_device_removed)
