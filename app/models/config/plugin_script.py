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

from collections.abc import Awaitable, Callable
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigGroup,
    Virtual,
    virtual_field,
)
from app.config.shortcuts import collection, ref, select, ui

from .game_binding import GameBindingOwner
from .plan import PlanEntry
from .queue import Webhook
from .tag import TagItem


class UserEntry(GameBindingOwner):
    """用户配置上界：插件子类扩展；删用户时由宿主订阅清本地 data/。"""

    ui_native_session: ClassVar[Literal["view", "config"] | None] = None

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


class ScriptEntry(GameBindingOwner):
    """脚本配置上界：至少脚本名 + 游戏选择；users 由适配器挂具体 user_type。"""

    ui_native_session: ClassVar[Literal["view", "config"] | None] = None

    class Info(ConfigGroup):
        name: str = Field(default="新脚本", description="脚本名称")

    info: Info = Field(default_factory=Info, description="脚本信息")
    users: ConfigCollection[UserEntry] = collection(UserEntry)

    @classmethod
    def bind_runtime_signals(cls) -> None:
        """设备绑定由公共游戏目标模型校验，不再保留 info 下的旧游戏字段。"""

    async def prepare_script_removal(self) -> None:
        """托管移除及通用数据清理前处理专项持有的资源。"""

    def prepare_user_removal(
        self, user_id: UUID
    ) -> Callable[[], Awaitable[None]] | None:
        """删除前捕获账号资源，返回仅在集合提交成功后运行的清理。"""
        return None
