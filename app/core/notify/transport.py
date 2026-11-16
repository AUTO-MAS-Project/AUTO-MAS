#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.notify.channels.registry import BoundChannels
from app.models.notification import (
    LocalNotice,
    NotifyPayload,
    RenderedNotification,
    WebhookTargetSnapshot,
    resolve_content,
)
from app.models.notification.channel import (
    ChannelTarget,
    DeliveryChannel,
    NotificationTransportSnapshot,
)
from app.utils import get_logger

logger = get_logger("本地通知")


class Notification:
    """持有已装配渠道，并保留系统通知和 Webhook 测试的直接入口。"""

    def __init__(self, channels: BoundChannels) -> None:
        self._channels = channels

    def channel_sender(
        self, key: str, *, transport: NotificationTransportSnapshot | None = None
    ) -> Any:
        return self._channels.sender(key, transport=transport)

    async def start(self) -> None:
        await self._channels.start()

    async def stop(self) -> None:
        await self._channels.stop()

    async def send_channel(
        self,
        channel: DeliveryChannel,
        target: ChannelTarget,
        rendered: RenderedNotification,
    ) -> bool | None:
        return await channel.send(
            sender=self.channel_sender(channel.key, transport=target.transport),
            target=target,
            rendered=rendered,
        )

    async def send_notice(self, notice: LocalNotice) -> None:
        # 本地提示是附加反馈；保留取消，但不能把已完成的业务改判为失败。
        try:
            await self.channel_sender("system").push_plyer(
                title=notice.title,
                message=notice.message,
                ticker=notice.ticker,
                t=notice.duration_seconds,
            )
        except Exception as exc:
            logger.warning(f"本地通知发送失败: {type(exc).__name__}")

    async def test_webhook(
        self, payload: NotifyPayload, webhook: WebhookTargetSnapshot
    ) -> None:
        await self.channel_sender("webhook").WebhookPush(
            title=payload.title,
            content=payload.text,
            webhook=replace(webhook, enabled=True),
            images=resolve_content(payload.images),
        )
