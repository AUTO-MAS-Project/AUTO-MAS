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

    async def send_koishi(
        self,
        message: str,
        msgtype: str = "text",
        client_name: str = "Koishi",
    ) -> bool:
        """
        通过 WebSocket 推送消息到 Koishi AUTO-MAS 插件

        Args:
            message (str): 消息内容。
            msgtype (str): 消息类型，可选 "text"、"html"、"picture"，默认 "text"。
            client_name (str): WebSocket 客户端名称，默认 "Koishi"。

        Returns:
            bool: 发送是否成功。
        """
        # 获取 WebSocket 客户端
        client = self.dependencies.get_client(client_name)
        if not client:
            self.dependencies.logger.error(
                f"Koishi 通知推送失败: 未找到名为 [{client_name}] 的 WebSocket 客户端"
            )
            return False

        if not client.is_connected:
            self.dependencies.logger.error(
                f"Koishi 通知推送失败: WebSocket 客户端 [{client_name}] 未连接"
            )
            return False

        # 构造通知消息
        notify_message = {
            "id": "Client",
            "type": "notify",
            "data": {
                "msgtype": msgtype,
                "message": message,
            },
        }

        # 发送消息
        success = await client.send(notify_message)
        if success:
            self.dependencies.logger.success(f"Koishi 通知推送成功: {message[:50]}")
        else:
            self.dependencies.logger.error("Koishi 通知推送失败: 发送消息失败")

        return success
