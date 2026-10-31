#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from __future__ import annotations

from typing import Any

from app.models.notification import NotificationCapabilities, RenderedNotification
from app.models.notification.channel import (
    SCOPE_GLOBAL,
    ChannelConfig,
    ChannelTarget,
    NotifyChannel,
    QQSessionDependencies,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import QQTarget, Sender


def _openclaw_qq_targets(
    config: ChannelConfig, *, scope: str
) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)} QQ（官方机器人）"
    app_id = config.get("Notify", "OpenClawQQAppId")
    target_type = config.get("Notify", "OpenClawQQTargetType")
    recipients: list[QQTarget] = []
    if target_type in {"c2c", "all"}:
        recipients.append(
            QQTarget(
                app_id=app_id,
                target_type="c2c",
                openid=config.get("Notify", "OpenClawQQTargetOpenId"),
            )
        )
    if target_type in {"group", "all"}:
        recipients.extend(
            QQTarget(app_id=app_id, target_type="group", openid=openid)
            for openid in dict.fromkeys(config.get("Notify", "OpenClawQQGroupOpenIds"))
            if openid
        )
    return tuple(
        ChannelTarget(
            id=(
                f"{name}:group:{app_id}:{target.openid}"
                if target.target_type == "group"
                else name
            ),
            label=f"{name} 群 …{target.openid[-12:]}"
            if target.target_type == "group" and target.openid
            else name,
            value=target,
            capabilities=NotificationCapabilities(
                formats=("text",),
                image_presentations=frozenset({"rich_media"}),
                body_title_policy="always",
            ),
        )
        for target in recipients
    )


async def _openclaw_qq_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    return await sender.send_openclaw_qq(
        title=rendered.title,
        content=rendered.content,
        images=rendered.images,
        target=target.value,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="openclaw_qq",
        name_key="core.setting.notify.openclawQqSection",
        desc_key="core.setting.notify.openclawQqTip",
        icon="qq",
        group="builtin",
        order=80,
        doc_url="https://bot.q.qq.com/wiki/",
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="custom",
        custom_block="claw:qq",
        enable_field=("Notify", "IfOpenClawQQ"),
        summary_key=None,
        summary_fields=(),
        fields={},
        target_builder=_openclaw_qq_targets,
        send_adapter=_openclaw_qq_send,
        sender_factory=lambda deps: Sender(
            QQSessionDependencies(
                config=deps.config,
                read_proxy=deps.read_proxy,
                http_factory=deps.http_factory,
                websocket_connect=deps.websocket_connect,
                notification_command_executor=deps.notification_command_executor,
            )
        ),
        start_adapter=Sender.start,
        stop_adapter=Sender.stop,
        lifecycle_order=0,
    )
