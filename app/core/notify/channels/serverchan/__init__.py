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
    SCOPE_USER,
    ChannelConfig,
    ChannelTarget,
    HttpDependencies,
    NotifyChannel,
    NotifyChannelField,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import Sender

_SERVERCHAN_FIELD = NotifyChannelField(
    group="Notify",
    name="ServerChanKey",
    label_key="core.setting.notify.serverChanKey",
    control="password",
    placeholder_key="core.setting.notify.serverChanPlaceholder",
    tip_key="core.setting.notify.serverChanKeyTip",
)


def _serverchan_targets(
    config: ChannelConfig, *, scope: str
) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "ServerChanKey")
    if value is None:
        return ()
    name = f"{_prefix(scope)} ServerChan"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}ServerChan 密钥",
            summary_policy="if_over_limit",
            capabilities=NotificationCapabilities(
                formats=("markdown", "text"),
                image_presentations=frozenset({"markdown"}),
                max_content_utf8_bytes=30 * 1024,
                double_text_newlines=True,
            ),
        ),
    )


async def _serverchan_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    return await sender.ServerChanPush(
        title=rendered.title,
        content=rendered.content,
        send_key=target.value,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="serverchan",
        name_key="core.setting.notify.serverChanSection",
        desc_key="core.setting.notify.serverChanTip",
        icon="plane",
        group="builtin",
        order=30,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfServerChan"),
        summary_key="core.setting.notify.summary.serverchan",
        summary_fields=("ServerChanKey",),
        fields={SCOPE_GLOBAL: (_SERVERCHAN_FIELD,), SCOPE_USER: (_SERVERCHAN_FIELD,)},
        target_builder=_serverchan_targets,
        send_adapter=_serverchan_send,
        sender_factory=lambda deps: Sender(
            HttpDependencies(
                read_proxy=deps.read_proxy,
                http_factory=deps.http_factory,
                logger=deps.logger,
            )
        ),
        transport_fields=(),
    )
