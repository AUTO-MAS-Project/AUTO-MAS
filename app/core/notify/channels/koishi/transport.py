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

import asyncio
from typing import Any, Dict

from app.models.notification.channel import KoishiDependencies


class Sender:
    def __init__(self, dependencies: KoishiDependencies) -> None:
        self.dependencies = dependencies
        self._manager = dependencies.websocket_manager_factory()
        self._auth_token: str | None = None

    async def start(self) -> None:
        """沿用原启动条件和连接参数，恢复 Koishi 通知及远程命令连接。"""
        config = self.dependencies.config
        if not config.get("IfKoishiSupport"):
            self.dependencies.logger.info("Koishi 通知未启用，跳过系统客户端初始化")
            return
        address = config.get("KoishiServerAddress")
        if not address:
            self.dependencies.logger.warning(
                "Koishi 服务器地址为空，跳过系统客户端初始化"
            )
            return
        url = self.http_to_ws_url(address)
        self.dependencies.logger.info(f"正在初始化 Koishi 系统客户端: {url}")
        try:
            self._auth_token = None
            await self._manager.create_client(
                name="Koishi",
                url=url,
                ping_interval=15.0,
                ping_timeout=30.0,
                reconnect_interval=5.0,
                max_reconnect_attempts=-1,
                on_connect=self._on_connect,
                on_message=self._on_message,
            )
            success = await self._manager.connect_client("Koishi")
            if success:
                self.dependencies.logger.success(f"Koishi 系统客户端连接成功: {url}")
            else:
                self.dependencies.logger.warning(
                    "Koishi 系统客户端连接失败，将在后台持续重连"
                )
        except Exception as exc:
            self.dependencies.logger.error(
                f"初始化 Koishi 系统客户端失败: {type(exc).__name__}: {exc}"
            )

    async def stop(self) -> None:
        await self._manager.disconnect_client("Koishi")

    async def _send_auth(self, token: str) -> bool:
        client = self._manager.get_client("Koishi")
        if client is None or not client.is_connected:
            return False
        self._auth_token = token
        success = await client.send(
            {"id": "Client", "type": "auth", "data": {"token": token}}
        )
        if success:
            self.dependencies.logger.info("已发送认证消息")
        return success

    async def _on_connect(self) -> None:
        # 沿用原重连顺序：恢复缓存认证，再读取当前 Token 认证。
        if self._auth_token:
            await self._send_auth(self._auth_token)
        token = self.dependencies.config.get("KoishiToken")
        if token:
            await asyncio.sleep(0.1)
            if await self._send_auth(token):
                self.dependencies.logger.success("Koishi 系统客户端认证消息已发送")
            else:
                self.dependencies.logger.warning("Koishi 系统客户端认证消息发送失败")
        else:
            self.dependencies.logger.warning("Koishi Token 为空，跳过认证")

    async def _on_message(self, data: Dict[str, Any]) -> None:
        if data.get("type") == "command":
            await self._handle_command(data)

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
        client = self._manager.get_client(client_name)
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

    async def _handle_command(self, data: Dict[str, Any]):
        """
        处理 command 类型消息

        Args:
            data: 消息数据，格式为:
                {
                    "id": "Koishi",
                    "type": "command",
                    "data": {
                        "endpoint": "queue.info",
                        "params": {...}  # 可选
                    }
                }
        """
        if self.dependencies.command_executor is None:
            self.dependencies.logger.warning("未配置命令执行器，忽略 command 消息")
            return

        try:
            msg_id = data.get("id", "Unknown")
            msg_data = data.get("data", {})
            endpoint = msg_data.get("endpoint")
            params = msg_data.get("params")

            if not endpoint:
                self.dependencies.logger.warning(
                    f"收到来自 [{msg_id}] 的 command 消息，但缺少 endpoint"
                )
                return

            self.dependencies.logger.info(f"收到来自 [{msg_id}] 的命令: {endpoint}")

            result = await self.dependencies.command_executor(endpoint, params)

            # 发送响应
            response = {
                "id": "Client",
                "type": "response",
                "data": {"endpoint": endpoint, "request_id": msg_id, **result},
            }
            await self._manager.get_client("Koishi").send(response)
            self.dependencies.logger.debug(
                f"已响应命令 [{endpoint}]: success={result.get('success')}"
            )

        except Exception as e:
            self.dependencies.logger.error(
                f"处理命令时发生异常: {type(e).__name__}: {e}"
            )

    @staticmethod
    def http_to_ws_url(http_url: str) -> str:
        """将 HTTP URL 转换为 WebSocket URL"""
        if http_url.startswith("https://"):
            return "wss://" + http_url[8:]
        elif http_url.startswith("http://"):
            return "ws://" + http_url[7:]
        elif http_url.startswith("wss://") or http_url.startswith("ws://"):
            return http_url
        else:
            # 默认添加 ws://
            return "ws://" + http_url
