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

import json
from typing import Any
from urllib.parse import urlsplit

from app.models.notification import (
    DEFAULT_WEBHOOK_TEMPLATE,
    WECOM_ROBOT_HOST,
    WECOM_ROBOT_PATH,
    NotificationCapabilities,
    RenderedNotification,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import (
    SCOPE_GLOBAL,
    SCOPE_USER,
    ChannelConfig,
    ChannelTarget,
    NotifyChannel,
)
from app.models.notification_channel import target_prefix as _prefix

from .transport import Sender


def _webhook_name(uid: str, webhook: Any) -> str:
    """返回便于定位失败配置的 Webhook 名称。"""

    try:
        return str(webhook.get("Info", "Name") or uid)
    except (AttributeError, KeyError):
        return uid


def _webhook_capabilities(
    webhook: WebhookTargetSnapshot,
) -> NotificationCapabilities:
    """解析该配置实际使用的正文表达与图片槽位。"""

    template_text = webhook.template or DEFAULT_WEBHOOK_TEMPLATE
    try:
        template = json.loads(template_text)
    except (ValueError, TypeError):
        template = None
    parsed_url = urlsplit(webhook.url)
    host = (parsed_url.hostname or "").lower()
    markdown = (
        isinstance(template, dict)
        and (
            template.get("msgtype") == "markdown"
            or template.get("template") == "markdown"
            or "desp" in template
        )
    ) or host in {
        "discord.com",
        "discordapp.com",
        "canary.discord.com",
        "ptb.discord.com",
    }
    wecom_image = host == WECOM_ROBOT_HOST and parsed_url.path == WECOM_ROBOT_PATH
    image_slot = "{image_base64}" in template_text or wecom_image
    return NotificationCapabilities(
        formats=("markdown", "text") if markdown else ("text",),
        image_presentations=frozenset({"base64"}) if image_slot else frozenset(),
        body_title_policy="when_title_missing",
        title_in_template="{title}" in template_text,
    )


def _webhook_targets(config: ChannelConfig, *, scope: str) -> tuple[ChannelTarget, ...]:
    prefix = _prefix(scope)
    targets = []
    # 顺序按 MultipleConfig.order（items() 的产出顺序），不按 uid。
    for uid, webhook in config.Notify_CustomWebhooks.items():
        snapshot = WebhookTargetSnapshot(
            name=_webhook_name(uid, webhook),
            enabled=bool(webhook.get("Info", "Enabled")),
            url=str(webhook.get("Data", "Url") or ""),
            template=str(webhook.get("Data", "Template") or ""),
            headers=str(webhook.get("Data", "Headers") or "{ }"),
            method=webhook.get("Data", "Method"),
        )
        if not snapshot.enabled:
            continue
        targets.append(
            ChannelTarget(
                id=f"{prefix} Webhook {uid}",
                label=f"{prefix} Webhook {_webhook_name(uid, snapshot)}",
                value=snapshot,
                capabilities=_webhook_capabilities(snapshot),
            )
        )
    return tuple(targets)


async def _webhook_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    return await sender.WebhookPush(
        title=rendered.title,
        content=rendered.content,
        images=rendered.images,
        webhook=target.value,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="webhook",
        name_key="setting.notify.webhookName",
        desc_key="setting.notify.webhookDesc",
        icon="webhook",
        group="custom",
        order=50,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="custom",
        custom_block="webhook_list",
        enable_field=None,
        summary_key="setting.notify.summary.webhook",
        summary_fields=(),
        fields={},
        target_builder=_webhook_targets,
        send_adapter=_webhook_send,
        sender_factory=Sender,
    )
