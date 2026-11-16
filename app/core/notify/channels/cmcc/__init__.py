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
    NotifyChannelField,
    WebSocketDependencies,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import Sender


def _cmcc_targets(config: ChannelConfig, *, scope: str) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "CMCCNewMsgApiKey")
    if value is None:
        return ()
    name = f"{_prefix(scope)} 中国移动5G短信"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}中国移动5G短信 API Key",
            capabilities=NotificationCapabilities(
                formats=("text",),
                body_title_policy="always",
            ),
        ),
    )


async def _cmcc_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    return await sender.send_cmcc_newmsg(
        title=rendered.title,
        content=rendered.content,
        api_key=target.value,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="cmcc",
        name_key="core.setting.notify.cmccNewMsgName",
        desc_key="core.setting.notify.cmccNewMsgTip",
        icon="signal",
        group="builtin",
        order=40,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html",
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfCMCCNewMsg"),
        summary_key="core.setting.notify.summary.cmcc",
        summary_fields=("CMCCNewMsgApiKey",),
        fields={
            SCOPE_GLOBAL: (
                NotifyChannelField(
                    group="Notify",
                    name="CMCCNewMsgApiKey",
                    label_key="core.setting.notify.cmccNewMsgApiKey",
                    control="password",
                    placeholder_key="core.setting.notify.cmccNewMsgApiKeyPlaceholder",
                    tip_key="core.setting.notify.cmccNewMsgApiKeyTip",
                ),
            )
        },
        target_builder=_cmcc_targets,
        send_adapter=_cmcc_send,
        sender_factory=lambda deps: Sender(
            WebSocketDependencies(
                read_proxy=deps.read_proxy,
                websocket_connect=deps.websocket_connect,
                logger=deps.logger,
            )
        ),
        transport_fields=(),
    )
