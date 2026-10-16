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
from typing import Any, Literal

from app.models.config import Webhook
from app.models.notification import (
    NotificationImage,
    RenderedNotification,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import ChannelTarget, NotifyChannel
from app.notification_channels.registry import BoundChannels

# 保留现有辅助函数的导入路径；实现只属于对应渠道。
from app.notification_channels.system.transport import (
    clip_notify_text as clip_notify_text,
)
from app.notification_channels.webhook.transport import (
    webhook_body_failure as webhook_body_failure,
)


class Notification:
    """兼容现有单渠道入口，不触发广播、额外重试或外部连接。"""

    def __init__(self) -> None:
        self._channels: BoundChannels | None = None

    @property
    def initialized(self) -> bool:
        return self._channels is not None

    def bind(self, channels: BoundChannels) -> None:
        if self._channels is not None and self._channels is not channels:
            raise RuntimeError("通知渠道已装配")
        self._channels = channels

    def _sender(self, key: str) -> Any:
        if self._channels is None:
            raise RuntimeError("通知渠道尚未装配")
        return self._channels.sender(key)

    async def send_channel(
        self,
        channel: NotifyChannel,
        target: ChannelTarget,
        rendered: RenderedNotification,
    ) -> bool | None:
        return await channel.send(self._sender(channel.key), target, rendered)

    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> None:
        return await self._sender("system").push_plyer(
            title=title, message=message, ticker=ticker, t=t
        )

    async def send_mail(
        self,
        mode: Literal["文本", "网页"],
        title: str,
        content: str,
        to_address: str,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        return await self._sender("mail").send_mail(
            mode=mode,
            title=title,
            content=content,
            to_address=to_address,
            images=images,
        )

    async def ServerChanPush(self, title: str, content: str, send_key: str) -> None:
        return await self._sender("serverchan").ServerChanPush(
            title=title, content=content, send_key=send_key
        )

    async def send_cmcc_newmsg(self, title: str, content: str, api_key: str) -> None:
        return await self._sender("cmcc").send_cmcc_newmsg(
            title=title, content=content, api_key=api_key
        )

    async def send_openclaw_qq(
        self, title: str, content: str, *, images: Sequence[NotificationImage] = ()
    ) -> None:
        return await self._sender("openclaw_qq").send_openclaw_qq(
            title=title, content=content, images=images
        )

    async def WebhookPush(
        self,
        title: str,
        content: str,
        webhook: Webhook | WebhookTargetSnapshot,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        return await self._sender("webhook").WebhookPush(
            title=title, content=content, webhook=webhook, images=images
        )

    async def send_koishi(
        self, message: str, msgtype: str = "text", client_name: str = "Koishi"
    ) -> bool:
        return await self._sender("koishi").send_koishi(
            message=message, msgtype=msgtype, client_name=client_name
        )


Notify = Notification()
