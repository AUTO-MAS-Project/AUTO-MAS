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
    SystemNoticeDependencies,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import Sender


def _system_targets(config: ChannelConfig, *, scope: str) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)}系统"
    return (
        ChannelTarget(
            is_local=True,
            id=name,
            label=name,
            timeout_seconds=5,
            summary_policy="preferred",
            use_summary_title=True,
            capabilities=NotificationCapabilities(
                formats=("text",),
                append_signature=False,
            ),
        ),
    )


async def _system_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    lines = rendered.content.splitlines() if rendered.summary_used else []
    timeout = 5 if target.timeout_seconds is None else target.timeout_seconds
    return await sender.push_plyer(
        title=rendered.title,
        message=rendered.content,
        ticker=(lines[0] if lines else "") or rendered.title,
        t=timeout,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="system",
        name_key="core.setting.notify.systemSection",
        desc_key="core.setting.notify.systemTip",
        icon="bell",
        group="builtin",
        order=10,
        doc_url=None,
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfPushPlyer"),
        summary_key="core.setting.notify.summary.system",
        summary_fields=(),
        fields={},
        target_builder=_system_targets,
        send_adapter=_system_send,
        sender_factory=lambda deps: Sender(
            SystemNoticeDependencies(
                config=deps.transport or deps.config,
                system_notify=deps.system_notify,
                system_icon=deps.system_icon,
                logger=deps.logger,
            )
        ),
        transport_fields=("IfPushPlyer",),
    )
