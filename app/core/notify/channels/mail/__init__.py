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

from typing import Any, Mapping

from app.models.notification import NotificationCapabilities, RenderedNotification
from app.models.notification.channel import (
    SCOPE_GLOBAL,
    SCOPE_USER,
    ChannelConfig,
    ChannelTarget,
    MailDependencies,
    NotifyChannel,
    NotifyChannelField,
)
from app.models.notification.channel import target_prefix as _prefix

from .transport import Sender

_MAIL_FIELD_TO = NotifyChannelField(
    group="Notify",
    name="ToAddress",
    label_key="core.setting.notify.to",
    control="text",
    placeholder_key="core.setting.notify.toPlaceholder",
    tip_key="core.setting.notify.toTip",
)

_MAIL_FIELDS: Mapping[str, tuple[NotifyChannelField, ...]] = {
    SCOPE_GLOBAL: (
        NotifyChannelField(
            group="Notify",
            name="SMTPServerAddress",
            label_key="core.setting.notify.smtp",
            control="text",
            placeholder_key="core.setting.notify.smtpPlaceholder",
            tip_key="core.setting.notify.smtpTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="FromAddress",
            label_key="core.setting.notify.from",
            control="text",
            placeholder_key="core.setting.notify.fromPlaceholder",
            tip_key="core.setting.notify.fromTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="AuthorizationCode",
            label_key="core.setting.notify.authCode",
            control="password",
            placeholder_key="core.setting.notify.authCodePlaceholder",
            tip_key="core.setting.notify.authCodeTip",
        ),
        _MAIL_FIELD_TO,
    ),
    SCOPE_USER: (_MAIL_FIELD_TO,),
}


def _mail_targets(config: ChannelConfig, *, scope: str) -> tuple[ChannelTarget, ...]:
    value = config.get("Notify", "ToAddress")
    if value is None:
        return ()
    name = f"{_prefix(scope)}邮件"
    return (
        ChannelTarget(
            id=name,
            label=name,
            value=value,
            empty_recipient=value,
            empty_hint=f"{_prefix(scope)}邮箱地址",
            capabilities=NotificationCapabilities(
                formats=("html", "text"),
                image_presentations=frozenset({"html"}),
                append_signature=False,
            ),
        ),
    )


async def _mail_send(
    sender: Any, target: ChannelTarget, rendered: RenderedNotification
) -> bool | None:
    return await sender.send_mail(
        mode="网页" if rendered.format == "html" else "文本",
        title=rendered.title,
        content=rendered.content,
        to_address=target.value,
        images=rendered.images,
    )


def register() -> NotifyChannel:
    return NotifyChannel(
        key="mail",
        name_key="core.setting.notify.mailSection",
        desc_key="core.setting.notify.mailEnableTip",
        icon="mail",
        group="builtin",
        order=20,
        doc_url="https://doc.auto-mas.top/docs/advanced-features/notification.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93",
        scopes=frozenset({SCOPE_GLOBAL, SCOPE_USER}),
        kind="fields",
        custom_block=None,
        enable_field=("Notify", "IfSendMail"),
        summary_key="core.setting.notify.summary.mail",
        summary_fields=("SMTPServerAddress", "ToAddress"),
        fields=_MAIL_FIELDS,
        target_builder=_mail_targets,
        send_adapter=_mail_send,
        sender_factory=lambda deps: Sender(
            MailDependencies(
                config=deps.transport or deps.config,
                smtp_factory=deps.smtp_factory,
                logger=deps.logger,
            )
        ),
        transport_fields=("SMTPServerAddress", "FromAddress", "AuthorizationCode"),
    )
