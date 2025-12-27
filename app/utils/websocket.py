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


import time
import asyncio
import json
from typing import Optional, Callable, Any, Dict

from websockets.asyncio.client import connect, ClientConnection
from websockets.exceptions import ConnectionClosed

from app.utils.logger import get_logger


class WebSocketClient:
    """WebSocket 客户端，支持应用层 Ping/Pong 心跳维护，可创建多个实例连接不同服务端"""

    _instance_counter = 0  # 实例计数器，用于生成唯一标识

    def __init__(
            self,
            url: str,
            ping_interval: float = 15.0,
            ping_timeout: float = 30.0,
            reconnect_interval: float = 5.0,
            max_reconnect_attempts: int = -1,
            on_message: Optional[Callable[[Dict[str, Any]], Any]] = None,
            on_connect: Optional[Callable[[], Any]] = None,
            on_disconnect: Optional[Callable[[], Any]] = None,
            name: Optional[str] = None,
    ):
        """
        初始化 WebSocket 客户端

        Args:
            url: WebSocket 服务器地址，例如 "ws://localhost:8080/ws"
            ping_interval: 发送 Ping 的时间间隔（秒）
            ping_timeout: Ping 超时时间（秒），超过此时间未收到 Pong 则断开连接
            reconnect_interval: 重连间隔时间（秒）
            max_reconnect_attempts: 最大重连次数，-1 表示无限重连
            on_message: 收到消息时的回调函数
            on_connect: 连接成功时的回调函数
            on_disconnect: 断开连接时的回调函数
            name: 客户端名称，用于日志标识，不传则自动生成
        """
        WebSocketClient._instance_counter += 1
        self.name = name or f"WSClient-{WebSocketClient._instance_counter}"
        self.logger = get_logger(f"WS客户端:{self.name}")

        self.url = url
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self._connection: Optional[ClientConnection] = None
        self._running = False
        self._last_ping = 0.0
        self._last_pong = 0.0
        self._reconnect_count = 0
        self._tasks: list[asyncio.Task] = []

    @property
    def is_connected(self) -> bool:
        """检查连接是否有效"""
        return self._connection is not None and self._connection.state.name == "OPEN"

    async def connect(self) -> bool:
        """
        建立 WebSocket 连接

        Returns:
            bool: 连接是否成功
        """
        try:
            self._connection = await connect(
                self.url,
                ping_interval=None,  # 禁用协议层心跳，使用应用层心跳
                ping_timeout=None,
            )
            self._last_ping = time.monotonic()
            self._last_pong = time.monotonic()
            self._reconnect_count = 0

            self.logger.info(f"WebSocket 连接成功: {self.url}")

            if self.on_connect:
                result = self.on_connect()
                if asyncio.iscoroutine(result):
                    await result

            return True

        except Exception as e:
            self.logger.error(f"WebSocket 连接失败: {type(e).__name__}: {e}")
            return False

    async def disconnect(self):
        """断开 WebSocket 连接"""
        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                self.logger.warning(f"关闭连接时发生异常: {type(e).__name__}: {e}")
            finally:
                self._connection = None

        self.logger.info("WebSocket 连接已断开")

        if self.on_disconnect:
            result = self.on_disconnect()
            if asyncio.iscoroutine(result):
                await result

    async def send(self, message: Dict[str, Any]) -> bool:
        """
        发送 JSON 消息

        Args:
            message: 要发送的消息字典

        Returns:
            bool: 发送是否成功
        """
        if not self.is_connected:
            self.logger.warning("WebSocket 未连接，无法发送消息")
            return False

        try:
            await self._connection.send(json.dumps(message))
            return True
        except Exception as e:
            self.logger.error(f"发送消息失败: {type(e).__name__}: {e}")
            return False

    async def _send_ping(self):
        """发送应用层 Ping"""
        message = {
            "id": "Client",
            "type": "Signal",
            "data": {"Ping": "heartbeat"}
        }
        if await self.send(message):
            self._last_ping = time.monotonic()
            self.logger.debug("已发送 Ping")

    async def _send_pong(self):
        """发送应用层 Pong"""
        message = {
            "id": "Client",
            "type": "Signal",
            "data": {"Pong": "heartbeat"}
        }
        await self.send(message)
        self.logger.debug("已发送 Pong")

    async def _handle_message(self, raw_message: str):
        """
        处理接收到的消息

        Args:
            raw_message: 原始消息字符串
        """
        try:
            data = json.loads(raw_message)

            # 处理 Ping/Pong 信号
            if data.get("type") == "Signal":
                signal_data = data.get("data", {})
                if "Pong" in signal_data:
                    self._last_pong = time.monotonic()
                    self.logger.debug("收到 Pong")
                    return
                elif "Ping" in signal_data:
                    self.logger.debug("收到 Ping")
                    await self._send_pong()
                    return

            # 调用消息回调
            if self.on_message:
                result = self.on_message(data)
                if asyncio.iscoroutine(result):
                    await result

        except json.JSONDecodeError as e:
            self.logger.warning(f"消息解析失败: {e}")
        except Exception as e:
            self.logger.error(f"处理消息时发生异常: {type(e).__name__}: {e}")

    async def _receive_loop(self):
        """消息接收循环"""
        while self._running and self.is_connected:
            try:
                message = await asyncio.wait_for(
                    self._connection.recv(),
                    timeout=self.ping_interval
                )
                await self._handle_message(message)

            except asyncio.TimeoutError:
                # 接收超时，检查心跳状态
                continue

            except ConnectionClosed as e:
                self.logger.warning(
                    f"连接已关闭: {e.rcvd.code if e.rcvd else 'N/A'} - {e.rcvd.reason if e.rcvd else 'N/A'}")
                break

            except Exception as e:
                self.logger.error(f"接收消息时发生异常: {type(e).__name__}: {e}")
                break

    async def _heartbeat_loop(self):
        """心跳维护循环"""
        while self._running and self.is_connected:
            try:
                current_time = time.monotonic()

                # 检查 Pong 超时
                if self._last_pong < self._last_ping:
                    time_since_ping = current_time - self._last_ping
                    if time_since_ping > self.ping_timeout:
                        self.logger.warning(f"Pong 超时 ({time_since_ping:.1f}s)，断开连接")
                        break

                # 发送 Ping
                time_since_last_ping = current_time - self._last_ping
                if time_since_last_ping >= self.ping_interval:
                    await self._send_ping()

                await asyncio.sleep(1.0)

            except Exception as e:
                self.logger.error(f"心跳循环异常: {type(e).__name__}: {e}")
                break

    async def run(self):
        """
        运行 WebSocket 客户端（包含自动重连）
        """
        self._running = True

        while self._running:
            # 尝试连接
            if not await self.connect():
                self._reconnect_count += 1

                if self.max_reconnect_attempts != -1 and self._reconnect_count > self.max_reconnect_attempts:
                    self.logger.error(f"已达到最大重连次数 ({self.max_reconnect_attempts})，停止重连")
                    break

                self.logger.info(f"{self.reconnect_interval}秒后尝试重连... (第 {self._reconnect_count} 次)")
                await asyncio.sleep(self.reconnect_interval)
                continue

            # 启动接收和心跳任务
            receive_task = asyncio.create_task(self._receive_loop())
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._tasks = [receive_task, heartbeat_task]

            # 等待任一任务结束
            done, pending = await asyncio.wait(
                self._tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            self._tasks.clear()

            # 清理连接
            if self._connection:
                try:
                    await self._connection.close()
                except Exception:
                    pass
                self._connection = None

            if self.on_disconnect:
                result = self.on_disconnect()
                if asyncio.iscoroutine(result):
                    await result

            # 检查是否需要重连
            if not self._running:
                break

            self._reconnect_count += 1
            if self.max_reconnect_attempts != -1 and self._reconnect_count > self.max_reconnect_attempts:
                self.logger.error(f"已达到最大重连次数 ({self.max_reconnect_attempts})，停止重连")
                break

            self.logger.info(f"{self.reconnect_interval}秒后尝试重连... (第 {self._reconnect_count} 次)")
            await asyncio.sleep(self.reconnect_interval)

        self.logger.info("WebSocket 客户端已停止")

    async def run_once(self):
        """
        运行 WebSocket 客户端（不自动重连，连接断开后直接退出）
        """
        self._running = True

        if not await self.connect():
            return

        # 启动接收和心跳任务
        receive_task = asyncio.create_task(self._receive_loop())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._tasks = [receive_task, heartbeat_task]

        # 等待任一任务结束
        done, pending = await asyncio.wait(
            self._tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        # 取消未完成的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()
        await self.disconnect()

    async def _authenticate(self, token: str) -> bool:
        """
        发送认证消息

        Args:
            token: 认证令牌

        Returns:
            bool: 发送是否成功
        """
        auth_message = {
            "id": "Client",
            "type": "auth",
            "data": {
                "token": token
            }
        }
        return await self.send(auth_message)


# 便捷函数：创建并连接客户端
async def create_ws_client(
        host: str = "localhost",
        port: int = 8080,
        path: str = "/ws",
        use_ssl: bool = False,
        **kwargs
) -> WebSocketClient:
    """
    创建 WebSocket 客户端实例

    Args:
        host: 服务器主机地址
        port: 服务器端口
        path: WebSocket 路径
        use_ssl: 是否使用 SSL
        **kwargs: 传递给 WebSocketClient 的其他参数

    Returns:
        WebSocketClient: 客户端实例
    """
    protocol = "wss" if use_ssl else "ws"
    url = f"{protocol}://{host}:{port}{path}"
    return WebSocketClient(url=url, **kwargs)


# 使用示例
async def _example():
    """示例用法：同时连接多个服务端并发送消息"""

    async def on_message(client_name: str):
        async def handler(data: Dict[str, Any]):
            print(f"[{client_name}] 收到消息: {data}")

        return handler

    # 创建多个客户端实例，连接不同服务端
    client1 = await create_ws_client(
        host="localhost",
        port=5140,
        path="/AUTO_MAS",
        name="Server1",  # 指定名称便于日志区分
        ping_interval=15.0,
        ping_timeout=30.0,
        on_message=await on_message("Server1"),
    )

    # 创建一个任务用于定期向客户端发送消息
    async def send_messages():
        # 等待客户端连接成功
        while not client1.is_connected:
            await asyncio.sleep(0.1)
        await client1._authenticate(token="123456")

        # 发送测试消息
        for i in range(5):
            message = {
                "id": "TestClient",
                "type": "TestMessage",
                "data": {
                    "count": i,
                    "message": f"这是第 {i + 1} 条测试消息"
                }
            }
            # 向 client1 发送消息
            success = await client1.send(message)
            if success:
                print(f"[发送成功] -> Server1: {message}")
            else:
                print(f"[发送失败] -> Server1")

            await asyncio.sleep(3)  # 每3秒发送一次

    # 并发运行客户端和发送消息任务
    await asyncio.gather(
        client1.run(),
        send_messages(),
    )


if __name__ == "__main__":
    asyncio.run(_example())
