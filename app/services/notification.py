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

from collections.abc import Sequence
from typing import Any

from app.models.config import Webhook
from app.models.notification import (
    NotificationImage,
    RenderedNotification,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import ChannelTarget, NotifyChannel
from app.notification_channels.registry import BoundChannels


class Notification:
    """持有已装配渠道，并保留系统通知和 Webhook 测试的直接入口。"""

    def __init__(self) -> None:
        self._channels: BoundChannels | None = None

    @property
    def initialized(self) -> bool:
        return self._channels is not None

    def bind(self, channels: BoundChannels) -> None:
        if self._channels is not None and self._channels is not channels:
            raise RuntimeError("通知渠道已装配")
        self._channels = channels

    def channel_sender(self, key: str) -> Any:
        if self._channels is None:
            raise RuntimeError("通知渠道尚未装配")
        return self._channels.sender(key)

    async def start(self) -> None:
        if self._channels is None:
            raise RuntimeError("通知渠道尚未装配")
        await self._channels.start()

    async def stop(self) -> None:
        if self._channels is not None:
            await self._channels.stop()

    async def send_channel(
        self,
        channel: NotifyChannel,
        target: ChannelTarget,
        rendered: RenderedNotification,
    ) -> bool | None:
        return await channel.send(self.channel_sender(channel.key), target, rendered)

    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> None:
        return await self.channel_sender("system").push_plyer(
            title=title, message=message, ticker=ticker, t=t
        )

    async def WebhookPush(
        self,
        title: str,
        content: str,
        webhook: Webhook | WebhookTargetSnapshot,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        return await self.channel_sender("webhook").WebhookPush(
            title=title, content=content, webhook=webhook, images=images
        )


Notify = Notification()
