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

import re
from html import escape as html_escape
from typing import Any

from app.models.notification import NotificationCapabilities, RenderedNotification
from app.models.notification.channel import (
    SCOPE_GLOBAL,
    ChannelConfig,
    ChannelTarget,
    KoishiDependencies,
    NotificationDeliveryError,
    NotifyChannel,
    NotifyChannelField,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import Sender

_KOISHI_HTML_DOCUMENT_PATTERN = re.compile(
    r"^\s*(?:<!--.*?-->\s*)*(?:<!doctype\s+html\b|<html\b|<head\b)",
    re.IGNORECASE | re.DOTALL,
)


def _koishi_html_from_text(content: str) -> str:
    """把完整邮件文档的备用纯文本排成 Koishi 可读的 HTML 片段。"""

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    fragments = []
    for index, line in enumerate(lines):
        escaped = html_escape(line)
        if index == 0 or (line.startswith("【") and line.endswith("】")):
            tag = "h2"
        elif line.startswith("•"):
            tag = "h3"
        else:
            tag = "p"
        fragments.append(f"<{tag}>{escaped}</{tag}>")
    return "".join(fragments)


def _koishi_targets(config: ChannelConfig, *, scope: str) -> tuple[ChannelTarget, ...]:
    name = f"{_prefix(scope)} Koishi"
    return (
        ChannelTarget(
            id=name,
            label=name,
            capabilities=NotificationCapabilities(
                # Koishi 接收 HTML 正文片段；完整邮件文档在发送适配器中退回文本表达。
                formats=("html", "text"),
                body_title_policy="always",
            ),
        ),
    )


async def _koishi_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    if rendered.format != "html":
        success = await sender.send_koishi(rendered.content)
    else:
        if _KOISHI_HTML_DOCUMENT_PATTERN.search(rendered.content[:256]):
            content = _koishi_html_from_text(rendered.text_fallback or rendered.title)
        else:
            content = rendered.content
            title = html_escape(rendered.title)
            if title and title not in content:
                content = f"<h2>{title}</h2>{content}"
        success = await sender.send_koishi(content, msgtype="html")
    if success is False:
        raise NotificationDeliveryError(
            "Koishi 连接不可用或消息未提交", kind="unavailable", retryable=True
        )
    return success


def register() -> NotifyChannel:
    return NotifyChannel(
        key="koishi",
        name_key="core.setting.notify.koishiSection",
        desc_key="core.setting.notify.koishiTip",
        icon="chat",
        group="builtin",
        order=60,
        doc_url=None,
        scopes=frozenset({SCOPE_GLOBAL}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfKoishiSupport"),
        summary_key="core.setting.notify.summary.koishi",
        summary_fields=("KoishiServerAddress",),
        fields={
            SCOPE_GLOBAL: (
                NotifyChannelField(
                    group="Notify",
                    name="KoishiServerAddress",
                    label_key="core.setting.notify.koishiWs",
                    control="text",
                    placeholder_key="core.setting.notify.koishiWsPlaceholder",
                    tip_key="core.setting.notify.koishiWsTip",
                ),
                NotifyChannelField(
                    group="Notify",
                    name="KoishiToken",
                    label_key="core.setting.notify.koishiToken",
                    control="password",
                    placeholder_key="core.setting.notify.koishiTokenPlaceholder",
                    tip_key="core.setting.notify.koishiTokenTip",
                ),
            )
        },
        target_builder=_koishi_targets,
        send_adapter=_koishi_send,
        sender_factory=lambda deps: Sender(
            KoishiDependencies(
                config=deps.config,
                websocket_manager_factory=deps.websocket_manager_factory,
                logger=deps.logger,
                command_executor=deps.command_executor,
            )
        ),
        start_adapter=Sender.start,
        stop_adapter=Sender.stop,
        lifecycle_order=10,
    )
