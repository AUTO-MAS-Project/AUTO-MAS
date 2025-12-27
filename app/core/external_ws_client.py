#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""
外部 WebSocket 客户端管理器

连接到外部 WebSocket 服务器（如 Koishi），处理收到的 command 消息
"""

import asyncio
from typing import Dict, Any, Optional

from app.utils.websocket import WebSocketClient
from app.api.ws_command import execute_ws_command, list_ws_commands
from app.utils.logger import get_logger

logger = get_logger("WS外部客户端")


class ExternalWSClient:
    """外部 WebSocket 客户端管理器（连接到 Koishi 等外部服务器）"""
    
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        auto_auth: bool = True,
        **kwargs
    ):
        """
        初始化外部 WebSocket 客户端
        
        Args:
            url: WebSocket 服务器地址，例如 "ws://localhost:5140/AUTO_MAS"
            token: 验证令牌（可选）
            auto_auth: 是否在连接成功后自动发送认证消息
            **kwargs: 传递给 WebSocketClient 的其他参数
        """
        self.url = url
        self.token = token
        self.auto_auth = auto_auth
        self._client: Optional[WebSocketClient] = None
        self._running = False
        
        # 创建 WebSocket 客户端
        self._client = WebSocketClient(
            url=url,
            on_message=self._handle_message,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            name="External",
            **kwargs
        )
    
    async def _on_connect(self):
        """连接成功回调"""
        logger.info(f"已连接到外部服务器: {self.url}")
        
        # 自动发送认证消息
        if self.auto_auth and self.token:
            await self.send_auth()
    
    async def _on_disconnect(self):
        """断开连接回调"""
        logger.info("与外部服务器的连接已断开")
    
    async def send_auth(self):
        """发送认证消息"""
        if not self.token:
            logger.warning("未设置 token，跳过认证")
            return
        
        message = {
            "id": "Client",
            "type": "auth",
            "data": {
                "token": self.token
            }
        }
        
        success = await self._client.send(message)
        if success:
            logger.info("已发送认证消息")
        else:
            logger.error("发送认证消息失败")
    
    async def _handle_message(self, data: Dict[str, Any]):
        """
        处理接收到的消息
        
        Args:
            data: 消息数据
        """
        msg_type = data.get("type")
        
        # 处理 command 消息
        if msg_type == "command":
            await self._handle_command(data)
        
        # 处理认证响应
        elif msg_type == "auth_result":
            auth_data = data.get("data", {})
            if auth_data.get("success"):
                logger.info("认证成功")
            else:
                logger.error(f"认证失败: {auth_data.get('message')}")
        
        else:
            logger.debug(f"收到消息: type={msg_type}, data={data.get('data')}")
    
    async def _handle_command(self, message: Dict[str, Any]):
        """
        处理 command 类型消息
        
        消息格式:
        {
            "id": "koishi",
            "type": "command",
            "data": {
                "endpoint": "queue.add",
                "params": {...}
            }
        }
        
        Args:
            message: 完整的消息数据
        """
        command_data = message.get("data", {})
        endpoint = command_data.get("endpoint")
        params = command_data.get("params")
        
        if not endpoint:
            logger.warning("收到的 command 消息缺少 endpoint 字段")
            await self.send_result(message.get("id"), {
                "success": False,
                "message": "缺少 endpoint 字段"
            })
            return
        
        logger.info(f"执行命令: {endpoint}")
        
        # 执行命令
        try:
            result = await execute_ws_command(endpoint, params)
            
            # 返回结果给服务器
            await self.send_result(message.get("id"), result)
            
            if result.get("success"):
                logger.info(f"命令执行成功: {endpoint}")
            else:
                logger.error(f"命令执行失败: {endpoint}, 错误: {result.get('message')}")
        
        except Exception as e:
            logger.error(f"执行命令时发生异常: {type(e).__name__}: {e}")
            await self.send_result(message.get("id"), {
                "success": False,
                "message": f"命令执行异常: {str(e)}"
            })
    
    async def send_result(self, message_id: Optional[str], result: Dict[str, Any]):
        """
        发送命令执行结果
        
        Args:
            message_id: 原消息 ID
            result: 执行结果
        """
        response = {
            "id": "Client",
            "type": "command_result",
            "data": result
        }
        
        if message_id:
            response["reply_to"] = message_id
        
        await self._client.send(response)
    
    async def send_message(self, msg_type: str, data: Dict[str, Any]) -> bool:
        """
        发送自定义消息
        
        Args:
            msg_type: 消息类型
            data: 消息数据
        
        Returns:
            bool: 发送是否成功
        """
        message = {
            "id": "Client",
            "type": msg_type,
            "data": data
        }
        
        return await self._client.send(message)
    
    async def list_commands(self) -> list[str]:
        """
        获取所有可用命令列表
        
        Returns:
            list[str]: 命令端点列表
        """
        return list_ws_commands()
    
    async def start(self):
        """启动客户端（自动重连）"""
        logger.info(f"启动外部 WebSocket 客户端: {self.url}")
        self._running = True
        await self._client.run()
    
    async def start_once(self):
        """启动客户端（不自动重连）"""
        logger.info(f"启动外部 WebSocket 客户端: {self.url}")
        self._running = True
        await self._client.run_once()
    
    async def stop(self):
        """停止客户端"""
        logger.info("停止外部 WebSocket 客户端")
        self._running = False
        if self._client:
            await self._client.disconnect()
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._client.is_connected if self._client else False


# 使用示例
async def _example():
    """示例用法"""
    
    # 创建客户端
    client = ExternalWSClient(
        url="ws://localhost:5140/AUTO_MAS",
        token="123456",
        auto_auth=True,
        ping_interval=15.0,
        ping_timeout=30.0,
        reconnect_interval=5.0,
        max_reconnect_attempts=-1,  # 无限重连
    )
    
    # 启动客户端
    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止客户端")
        await client.stop()


if __name__ == "__main__":
    asyncio.run(_example())
