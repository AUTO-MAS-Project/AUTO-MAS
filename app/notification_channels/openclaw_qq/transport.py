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

from app.models.notification import NotificationImage
from app.models.notification_channel import ChannelDependencies


class Sender:
    def __init__(self, dependencies: ChannelDependencies) -> None:
        self.dependencies = dependencies

    async def send_openclaw_qq(
        self,
        title: str,
        content: str,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        """通过 QQ 官方机器人通道推送通知。

        登录凭据由扫码登录管理器维护，通知层不读取或暴露协议细节；长文本
        拆分、业务错误和访问令牌刷新也由管理器统一处理。

        Args:
            title: 通知标题。
            content: 已渲染的通知正文。
            images: 随通知发送的图片资源。

        Raises:
            ValueError: 尚未绑定 QQ 官方机器人时抛出。
            RuntimeError: 官方接口返回 HTTP 或业务错误时抛出。
        """
        await self.dependencies.send_qq(title=title, content=content, images=images)
