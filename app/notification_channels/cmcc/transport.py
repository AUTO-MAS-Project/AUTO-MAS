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

from app.models.notification_channel import ChannelDependencies


class Sender:
    def __init__(self, dependencies: ChannelDependencies) -> None:
        self.dependencies = dependencies

    async def send_cmcc_newmsg(self, title: str, content: str, api_key: str) -> None:
        """通过中国移动新消息（5G 消息）提交通知。"""

        proxy = self.dependencies.read_proxy()

        await self.dependencies.send_cmcc(
            api_key=api_key,
            content=content,
            proxy=proxy,
        )
        self.dependencies.logger.success(f"中国移动5G短信通知已提交: {title}")
