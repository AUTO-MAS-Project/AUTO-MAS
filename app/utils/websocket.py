#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


"""出站 WebSocket 客户端

后端作为客户端连接外部第三方进程（如 Koishi 通知服务）。
与前端主连接（app/core/ws）分层管理，互不混用状态。
心跳使用 WebSocket 协议层 ping/pong，不使用应用层业务消息。
"""

import json
import asyncio
from typing import Optional, Callable, Any, Awaitable, Dict

from websockets.asyncio.client import connect, ClientConnection
from websockets.exceptions import ConnectionClosed

from app.utils.logger import get_logger

# 远程命令执行器签名: (endpoint, params) -> 归一化结果字典
CommandExecutor = Callable[[str, Optional[Dict[str, Any]]], Awaitable[Dict[str, Any]]]


# ============== WebSocket 客户端实例 ==============


class WebSocketClient:
    """出站 WebSocket 客户端，可创建多个实例连接不同服务端。

    心跳由 websockets 库协议层 ping/pong 维护；
    支持指数退避自动重连与可注入的远程命令执行器。
    """

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
        auth_token: Optional[str] = None,
        command_executor: Optional[CommandExecutor] = None,
    ):
        """
        初始化 WebSocket 客户端

        Args:
            url: WebSocket 服务器地址，例如 "ws://localhost:8080/ws"
            ping_interval: 协议层 ping 发送间隔（秒）
            ping_timeout: 协议层 pong 超时时间（秒），超时视为连接断开
            reconnect_interval: 重连间隔时间（秒）
            max_reconnect_attempts: 最大重连次数，-1 表示无限重连
            on_message: 收到消息时的回调函数
            on_connect: 连接成功时的回调函数
            on_disconnect: 断开连接时的回调函数
            name: 客户端名称，用于日志标识，不传则自动生成
            auth_token: 认证令牌，设置后连接成功时会自动发送认证消息
            command_executor: 远程命令执行器，处理 type=="command" 的入站消息
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
        self._reconnect_count = 0
        self._receive_task: Optional[asyncio.Task] = None
        self._auth_token: Optional[str] = auth_token
        self._command_executor = command_executor

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
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
            )
            self._reconnect_count = 0

            self.logger.info(f"WebSocket 连接成功: {self.url}")

            # 自动进行认证（如果设置了 token）
            if self._auth_token:
                await self._authenticate(self._auth_token)

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

        if self._receive_task is not None and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self._receive_task = None

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

    async def close(self, code: int = 1000, reason: str = "正常关闭"):
        """兼容统一的关闭接口。"""
        await self.disconnect()

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

    async def send_json(self, data: Dict[str, Any]) -> bool:
        """兼容 FastAPI WebSocket 的 send_json 接口。"""
        return await self.send(data)

    async def send_auth(
        self,
        token: str,
        auth_type: str = "auth",
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """发送认证消息。"""
        self._auth_token = token
        auth_message = {
            "id": "Client",
            "type": auth_type,
            "data": {"token": token, **(extra_data or {})},
        }
        success = await self.send(auth_message)
        if success:
            self.logger.info("已发送认证消息")
        return success

    async def _handle_message(self, raw_message: str):
        """
        处理接收到的消息

        Args:
            raw_message: 原始消息字符串
        """
        try:
            data = json.loads(raw_message)

            # 处理 command 类型消息（外部进程远程调用后端命令）
            if data.get("type") == "command":
                await self._handle_command(data)
                # 同时也调用消息回调（如果有）
                if self.on_message:
                    result = self.on_message(data)
                    if asyncio.iscoroutine(result):
                        await result
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
        if self._command_executor is None:
            self.logger.warning("未配置命令执行器，忽略 command 消息")
            return

        try:
            msg_id = data.get("id", "Unknown")
            msg_data = data.get("data", {})
            endpoint = msg_data.get("endpoint")
            params = msg_data.get("params")

            if not endpoint:
                self.logger.warning(
                    f"收到来自 [{msg_id}] 的 command 消息，但缺少 endpoint"
                )
                return

            self.logger.info(f"收到来自 [{msg_id}] 的命令: {endpoint}")

            result = await self._command_executor(endpoint, params)

            # 发送响应
            response = {
                "id": "Client",
                "type": "response",
                "data": {"endpoint": endpoint, "request_id": msg_id, **result},
            }
            await self.send(response)
            self.logger.debug(
                f"已响应命令 [{endpoint}]: success={result.get('success')}"
            )

        except Exception as e:
            self.logger.error(f"处理命令时发生异常: {type(e).__name__}: {e}")

    async def _receive_loop(self):
        """消息接收循环"""
        while self._running and self.is_connected:
            try:
                message = await self._connection.recv()
                await self._handle_message(message)

            except ConnectionClosed as e:
                self.logger.warning(
                    f"连接已关闭: {e.rcvd.code if e.rcvd else 'N/A'} - {e.rcvd.reason if e.rcvd else 'N/A'}"
                )
                break

            except asyncio.CancelledError:
                raise

            except Exception as e:
                self.logger.error(f"接收消息时发生异常: {type(e).__name__}: {e}")
                break

    def _get_backoff_delay(self) -> float:
        """
        计算指数退避延迟时间

        Returns:
            float: 延迟时间（秒），最大60秒
        """
        # 指数退避: base_interval * 2^(reconnect_count - 1)
        delay = self.reconnect_interval * (2 ** (self._reconnect_count - 1))
        # 限制最大延迟为60秒
        return min(delay, 60.0)

    async def run(self):
        """
        运行 WebSocket 客户端（包含自动重连，使用指数退避策略）
        """
        self._running = True

        while self._running:
            # 尝试连接
            if not await self.connect():
                self._reconnect_count += 1

                if (
                    self.max_reconnect_attempts != -1
                    and self._reconnect_count > self.max_reconnect_attempts
                ):
                    self.logger.error(
                        f"已达到最大重连次数 ({self.max_reconnect_attempts})，停止重连"
                    )
                    break

                delay = self._get_backoff_delay()
                self.logger.info(
                    f"{delay:.1f}秒后尝试重连... (第 {self._reconnect_count} 次)"
                )
                await asyncio.sleep(delay)
                continue

            # 连接成功，重置重连计数并运行接收循环
            self._reconnect_count = 0
            self._receive_task = asyncio.create_task(self._receive_loop())

            try:
                await self._receive_task
            except asyncio.CancelledError:
                break
            finally:
                self._receive_task = None

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
            if (
                self.max_reconnect_attempts != -1
                and self._reconnect_count > self.max_reconnect_attempts
            ):
                self.logger.error(
                    f"已达到最大重连次数 ({self.max_reconnect_attempts})，停止重连"
                )
                break

            delay = self._get_backoff_delay()
            self.logger.info(
                f"{delay:.1f}秒后尝试重连... (第 {self._reconnect_count} 次)"
            )
            await asyncio.sleep(delay)

        self.logger.info("WebSocket 客户端已停止")

    async def _authenticate(self, token: str) -> bool:
        """
        发送认证消息

        Args:
            token: 认证令牌

        Returns:
            bool: 发送是否成功
        """
        # 保存 token 以便重连时使用
        self._auth_token = token
        auth_message = {"id": "Client", "type": "auth", "data": {"token": token}}
        success = await self.send(auth_message)
        if success:
            self.logger.info("已发送认证消息")
        return success

    def set_auth_token(self, token: Optional[str]):
        """
        设置认证令牌（下次连接/重连时生效）

        Args:
            token: 认证令牌，设为 None 可清除
        """
        self._auth_token = token


# ============== WebSocket 客户端管理器 ==============


class WSClientManager:
    """出站 WebSocket 客户端管理器，用于管理多个客户端实例"""

    # 系统客户端名称常量
    KOISHI_CLIENT_NAME = "Koishi"

    def __init__(self):
        self._clients: Dict[str, WebSocketClient] = {}
        self._system_clients: set[str] = {self.KOISHI_CLIENT_NAME}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._command_executor: Optional[CommandExecutor] = None
        self._logger = get_logger("WS管理器")

    def set_command_executor(self, executor: CommandExecutor) -> None:
        """
        注入远程命令执行器（应用启动时调用一次）。

        Args:
            executor: 命令执行器，签名为 (endpoint, params) -> 结果字典。
        """
        self._command_executor = executor

    def get_client(self, name: str) -> Optional[WebSocketClient]:
        """获取客户端实例"""
        return self._clients.get(name)

    def get_session(self, name: str) -> Optional[WebSocketClient]:
        """兼容旧接口：获取客户端实例。"""
        return self._clients.get(name)

    def has_client(self, name: str) -> bool:
        """检查客户端是否存在"""
        return name in self._clients

    def is_system_client(self, name: str) -> bool:
        """检查是否为系统客户端"""
        return name in self._system_clients

    def list_clients(self) -> Dict[str, Dict[str, Any]]:
        """列出所有客户端及其状态"""
        result = {}
        for name, client in self._clients.items():
            result[name] = {
                "name": name,
                "url": client.url,
                "is_connected": client.is_connected,
                "is_system": name in self._system_clients,
                "ping_interval": client.ping_interval,
                "ping_timeout": client.ping_timeout,
                "reconnect_interval": client.reconnect_interval,
                "max_reconnect_attempts": client.max_reconnect_attempts,
            }
        return result

    async def create_client(
        self,
        name: str,
        url: str,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = -1,
    ) -> WebSocketClient:
        """创建新的 WebSocket 客户端"""

        # 如果已存在同名客户端，先移除
        if name in self._clients:
            await self.remove_client(name)

        async def on_connect():
            self._logger.info(f"客户端 [{name}] 已连接到 {url}")

            # 如果是 Koishi 系统客户端，自动发送认证
            if name == self.KOISHI_CLIENT_NAME and name in self._system_clients:
                await self._auto_auth_koishi()

        async def on_disconnect():
            self._logger.info(f"客户端 [{name}] 已断开连接")

        # 创建客户端
        client = WebSocketClient(
            url=url,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            reconnect_interval=reconnect_interval,
            max_reconnect_attempts=max_reconnect_attempts,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            name=name,
            command_executor=self._command_executor,
        )

        self._clients[name] = client
        self._logger.info(f"已创建 WebSocket 客户端: {name} -> {url}")
        return client

    async def connect_client(self, name: str) -> bool:
        """连接客户端（非阻塞方式启动）"""
        client = self._clients.get(name)
        if not client:
            return False

        if client.is_connected:
            return True

        # 取消之前的任务
        if name in self._tasks:
            task = self._tasks[name]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 启动客户端任务
        self._tasks[name] = asyncio.create_task(
            self._run_client_with_reconnect(name, client)
        )

        # 等待连接建立（最多5秒）
        for _ in range(50):
            if client.is_connected:
                return True
            await asyncio.sleep(0.1)

        return client.is_connected

    async def _run_client_with_reconnect(self, name: str, client: WebSocketClient):
        """运行客户端并处理重连逻辑"""
        try:
            await client.run()
        except asyncio.CancelledError:
            self._logger.info(f"客户端 [{name}] 任务已取消")
        except Exception as e:
            self._logger.error(f"客户端 [{name}] 运行出错: {type(e).__name__}: {e}")

    async def disconnect_client(self, name: str) -> bool:
        """断开客户端连接"""
        client = self._clients.get(name)
        if not client:
            return False

        await client.disconnect()

        # 取消任务
        if name in self._tasks:
            task = self._tasks[name]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._tasks[name]

        return True

    async def remove_client(self, name: str) -> bool:
        """删除客户端（系统客户端不可删除）"""
        if name not in self._clients:
            return False

        # 系统客户端不可删除
        if name in self._system_clients:
            self._logger.warning(f"尝试删除系统客户端 [{name}]，已拒绝")
            return False

        # 先断开连接
        await self.disconnect_client(name)

        # 删除客户端
        if name in self._clients:
            del self._clients[name]

        self._logger.info(f"已删除 WebSocket 客户端: {name}")
        return True

    async def send_message(self, name: str, message: Dict[str, Any]) -> bool:
        """发送消息"""
        client = self._clients.get(name)
        if not client or not client.is_connected:
            return False

        return await client.send(message)

    async def send_auth(
        self,
        name: str,
        token: str,
        auth_type: str = "auth",
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """发送认证消息"""
        client = self._clients.get(name)
        if not client or not client.is_connected:
            return False

        return await client.send_auth(
            token=token, auth_type=auth_type, extra_data=extra_data
        )

    async def _auto_auth_koishi(self):
        """Koishi 系统客户端自动认证（连接/重连时调用）"""
        from app.core import Config

        token = Config.get("Notify", "KoishiToken")
        if token:
            # 稍微延迟以确保连接稳定
            await asyncio.sleep(0.1)
            auth_success = await self.send_auth(
                name=self.KOISHI_CLIENT_NAME, token=token, auth_type="auth"
            )
            if auth_success:
                self._logger.success("Koishi 系统客户端认证消息已发送")
            else:
                self._logger.warning("Koishi 系统客户端认证消息发送失败")
        else:
            self._logger.warning("Koishi Token 为空，跳过认证")

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

    async def init_system_client_koishi(self) -> bool:
        """
        初始化 Koishi 系统客户端

        根据配置自动创建并连接 Koishi WebSocket 客户端

        Returns:
            bool: 是否成功初始化并连接
        """
        from app.core import Config

        # 检查是否启用 Koishi 通知
        if not Config.get("Notify", "IfKoishiSupport"):
            self._logger.info("Koishi 通知未启用，跳过系统客户端初始化")
            return False

        # 获取服务器地址并转换为 WebSocket URL
        http_url = Config.get("Notify", "KoishiServerAddress")
        if not http_url:
            self._logger.warning("Koishi 服务器地址为空，跳过系统客户端初始化")
            return False

        ws_url = self.http_to_ws_url(http_url)

        self._logger.info(f"正在初始化 Koishi 系统客户端: {ws_url}")

        try:
            # 创建客户端
            await self.create_client(
                name=self.KOISHI_CLIENT_NAME,
                url=ws_url,
                ping_interval=15.0,
                ping_timeout=30.0,
                reconnect_interval=5.0,
                max_reconnect_attempts=-1,  # 无限重连
            )

            # 标记为系统客户端
            self._system_clients.add(self.KOISHI_CLIENT_NAME)

            # 连接客户端
            success = await self.connect_client(self.KOISHI_CLIENT_NAME)

            if success:
                self._logger.success(f"Koishi 系统客户端连接成功: {ws_url}")
                # 认证已在 on_connect 回调中自动处理
                return True
            else:
                self._logger.warning(f"Koishi 系统客户端连接失败，将在后台持续重连")
                return False

        except Exception as e:
            self._logger.error(f"初始化 Koishi 系统客户端失败: {type(e).__name__}: {e}")
            return False

    async def update_system_client_koishi(self) -> bool:
        """
        更新 Koishi 系统客户端配置

        当配置变更时调用，会断开旧连接并重新连接

        Returns:
            bool: 是否成功更新
        """
        # 如果客户端存在，先断开
        if self.has_client(self.KOISHI_CLIENT_NAME):
            await self.disconnect_client(self.KOISHI_CLIENT_NAME)
            # 从系统客户端集合中移除以允许删除
            self._system_clients.discard(self.KOISHI_CLIENT_NAME)
            # 删除旧客户端
            if self.KOISHI_CLIENT_NAME in self._clients:
                del self._clients[self.KOISHI_CLIENT_NAME]

        # 重新初始化
        return await self.init_system_client_koishi()


# 全局管理器实例
ws_client_manager = WSClientManager()


# 便捷函数：创建并连接客户端
async def create_ws_client(
    host: str = "localhost",
    port: int = 5140,
    path: str = "/ws",
    use_ssl: bool = False,
    **kwargs,
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
