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
WebSocket 客户端调试 API

提供后端作为 WebSocket 客户端连接外部服务器的功能
支持：创建客户端、连接、断开、发送消息、鉴权等
"""

import time
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.utils.websocket import WebSocketClient
from app.api.ws_command import list_ws_commands
from app.utils.logger import get_logger

logger = get_logger("WS调试")

router = APIRouter(prefix="/api/ws_debug", tags=["WebSocket调试"])


# ============== Pydantic 模型 ==============

class WSClientCreateIn(BaseModel):
    """创建 WebSocket 客户端请求"""
    name: str = Field(..., description="客户端名称，用于标识")
    url: str = Field(..., description="WebSocket 服务器地址，如 ws://localhost:5140/path")
    ping_interval: float = Field(default=15.0, description="心跳发送间隔（秒）")
    ping_timeout: float = Field(default=30.0, description="心跳超时时间（秒）")
    reconnect_interval: float = Field(default=5.0, description="重连间隔（秒）")
    max_reconnect_attempts: int = Field(default=-1, description="最大重连次数，-1为无限")


class WSClientCreateOut(BaseModel):
    """创建客户端响应"""
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="状态")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="返回数据")


class WSClientConnectIn(BaseModel):
    """连接请求"""
    name: str = Field(..., description="客户端名称")


class WSClientDisconnectIn(BaseModel):
    """断开连接请求"""
    name: str = Field(..., description="客户端名称")


class WSClientRemoveIn(BaseModel):
    """删除客户端请求"""
    name: str = Field(..., description="客户端名称")


class WSClientSendIn(BaseModel):
    """发送消息请求"""
    name: str = Field(..., description="客户端名称")
    message: Dict[str, Any] = Field(..., description="要发送的 JSON 消息")


class WSClientSendJsonIn(BaseModel):
    """发送自定义 JSON 消息请求"""
    name: str = Field(..., description="客户端名称")
    msg_id: str = Field(default="Client", description="消息 ID")
    msg_type: str = Field(..., description="消息类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="消息数据")


class WSClientAuthIn(BaseModel):
    """发送认证请求"""
    name: str = Field(..., description="客户端名称")
    token: str = Field(..., description="认证 Token")
    auth_type: str = Field(default="auth", description="认证消息类型")
    extra_data: Optional[Dict[str, Any]] = Field(default=None, description="额外认证数据")


class WSClientStatusIn(BaseModel):
    """获取客户端状态请求"""
    name: str = Field(..., description="客户端名称")


class WSClientStatusOut(BaseModel):
    """客户端状态响应"""
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="状态")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="状态数据")


class WSClientListOut(BaseModel):
    """客户端列表响应"""
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="状态")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="客户端列表")


class WSMessageHistoryOut(BaseModel):
    """消息历史响应"""
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="状态")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="消息历史")


class WSClearHistoryIn(BaseModel):
    """清空消息历史请求"""
    name: Optional[str] = Field(default=None, description="客户端名称，为空则清空所有")


class WSCommandsOut(BaseModel):
    """可用命令列表响应"""
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="状态")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="命令列表")


# ============== 全局状态管理 ==============

class WSClientManager:
    """WebSocket 客户端管理器"""
    
    def __init__(self):
        self._clients: Dict[str, WebSocketClient] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._message_history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history_per_client = 200
        self._debug_connections: List[WebSocket] = []
    
    def get_client(self, name: str) -> Optional[WebSocketClient]:
        """获取客户端实例"""
        return self._clients.get(name)
    
    def has_client(self, name: str) -> bool:
        """检查客户端是否存在"""
        return name in self._clients
    
    def list_clients(self) -> Dict[str, Dict[str, Any]]:
        """列出所有客户端及其状态"""
        result = {}
        for name, client in self._clients.items():
            result[name] = {
                "name": name,
                "url": client.url,
                "is_connected": client.is_connected,
                "ping_interval": client.ping_interval,
                "ping_timeout": client.ping_timeout,
                "reconnect_interval": client.reconnect_interval,
                "max_reconnect_attempts": client.max_reconnect_attempts,
                "message_count": len(self._message_history.get(name, []))
            }
        return result
    
    async def create_client(
        self,
        name: str,
        url: str,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = -1
    ) -> WebSocketClient:
        """创建新的 WebSocket 客户端"""
        
        # 如果已存在同名客户端，先移除
        if name in self._clients:
            await self.remove_client(name)
        
        # 创建消息回调
        async def on_message(data: Dict[str, Any]):
            await self._record_message(name, "received", data)
        
        async def on_connect():
            logger.info(f"客户端 [{name}] 已连接到 {url}")
            await self._broadcast_event({
                "event": "connected",
                "client": name,
                "url": url,
                "timestamp": time.time()
            })
        
        async def on_disconnect():
            logger.info(f"客户端 [{name}] 已断开连接")
            await self._broadcast_event({
                "event": "disconnected",
                "client": name,
                "timestamp": time.time()
            })
        
        # 创建客户端
        client = WebSocketClient(
            url=url,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            reconnect_interval=reconnect_interval,
            max_reconnect_attempts=max_reconnect_attempts,
            on_message=on_message,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            name=name
        )
        
        self._clients[name] = client
        self._message_history[name] = []
        
        logger.info(f"已创建 WebSocket 客户端: {name} -> {url}")
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
        
        # 启动客户端任务（使用 run_once 避免自动重连）
        self._tasks[name] = asyncio.create_task(self._run_client_with_reconnect(name, client))
        
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
            logger.info(f"客户端 [{name}] 任务已取消")
        except Exception as e:
            logger.error(f"客户端 [{name}] 运行出错: {type(e).__name__}: {e}")
    
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
        """删除客户端"""
        if name not in self._clients:
            return False
        
        # 先断开连接
        await self.disconnect_client(name)
        
        # 删除客户端
        del self._clients[name]
        
        # 清理消息历史
        if name in self._message_history:
            del self._message_history[name]
        
        logger.info(f"已删除 WebSocket 客户端: {name}")
        return True
    
    async def send_message(self, name: str, message: Dict[str, Any]) -> bool:
        """发送消息"""
        client = self._clients.get(name)
        if not client or not client.is_connected:
            return False
        
        success = await client.send(message)
        if success:
            await self._record_message(name, "sent", message)
        return success
    
    async def send_auth(
        self,
        name: str,
        token: str,
        auth_type: str = "auth",
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送认证消息"""
        auth_message = {
            "id": "Client",
            "type": auth_type,
            "data": {
                "token": token,
                **(extra_data or {})
            }
        }
        return await self.send_message(name, auth_message)
    
    async def _record_message(
        self,
        name: str,
        direction: str,
        data: Dict[str, Any]
    ):
        """记录消息"""
        if name not in self._message_history:
            self._message_history[name] = []
        
        record = {
            "direction": direction,
            "timestamp": time.time(),
            "data": data
        }
        
        self._message_history[name].append(record)
        
        # 限制历史记录数量
        if len(self._message_history[name]) > self._max_history_per_client:
            self._message_history[name].pop(0)
        
        # 广播给调试前端
        await self._broadcast_message(name, record)
    
    async def _broadcast_message(self, client_name: str, record: Dict[str, Any]):
        """广播消息给调试前端"""
        message = {
            "type": "message",
            "client": client_name,
            **record
        }
        await self._broadcast(message)
    
    async def _broadcast_event(self, event: Dict[str, Any]):
        """广播事件给调试前端"""
        message = {
            "type": "event",
            **event
        }
        await self._broadcast(message)
    
    async def _broadcast(self, data: Dict[str, Any]):
        """广播数据给所有调试前端"""
        disconnected = []
        for ws in self._debug_connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            if ws in self._debug_connections:
                self._debug_connections.remove(ws)
    
    def get_message_history(self, name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """获取消息历史"""
        if name:
            return {name: self._message_history.get(name, [])}
        return self._message_history.copy()
    
    def clear_message_history(self, name: Optional[str] = None):
        """清空消息历史"""
        if name:
            if name in self._message_history:
                self._message_history[name] = []
        else:
            for key in self._message_history:
                self._message_history[key] = []
    
    def add_debug_connection(self, ws: WebSocket):
        """添加调试前端连接"""
        self._debug_connections.append(ws)
    
    def remove_debug_connection(self, ws: WebSocket):
        """移除调试前端连接"""
        if ws in self._debug_connections:
            self._debug_connections.remove(ws)


# 全局管理器实例
_manager = WSClientManager()


# ============== API 路由 ==============

@router.post(
    "/client/create",
    summary="创建 WebSocket 客户端",
    response_model=WSClientCreateOut,
)
async def create_client(request: WSClientCreateIn) -> WSClientCreateOut:
    """
    创建一个新的 WebSocket 客户端实例
    
    - **name**: 客户端唯一名称
    - **url**: WebSocket 服务器地址
    - **ping_interval**: 心跳发送间隔
    - **ping_timeout**: 心跳超时时间
    - **reconnect_interval**: 重连间隔
    - **max_reconnect_attempts**: 最大重连次数
    """
    try:
        client = await _manager.create_client(
            name=request.name,
            url=request.url,
            ping_interval=request.ping_interval,
            ping_timeout=request.ping_timeout,
            reconnect_interval=request.reconnect_interval,
            max_reconnect_attempts=request.max_reconnect_attempts
        )
        
        return WSClientCreateOut(
            code=200,
            status="success",
            message=f"客户端 [{request.name}] 创建成功",
            data={
                "name": request.name,
                "url": request.url,
                "is_connected": client.is_connected
            }
        )
    except Exception as e:
        logger.error(f"创建客户端失败: {type(e).__name__}: {e}")
        return WSClientCreateOut(
            code=500,
            status="error",
            message=f"创建客户端失败: {str(e)}"
        )


@router.post(
    "/client/connect",
    summary="连接 WebSocket 客户端",
    response_model=WSClientStatusOut,
)
async def connect_client(request: WSClientConnectIn) -> WSClientStatusOut:
    """
    启动指定客户端的连接（非阻塞）
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    try:
        success = await _manager.connect_client(request.name)
        client = _manager.get_client(request.name)
        
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message=f"客户端 [{request.name}] 连接成功",
                data={
                    "name": request.name,
                    "url": client.url if client else None,
                    "is_connected": True
                }
            )
        else:
            return WSClientStatusOut(
                code=500,
                status="error",
                message=f"客户端 [{request.name}] 连接失败或超时",
                data={
                    "name": request.name,
                    "is_connected": client.is_connected if client else False
                }
            )
    except Exception as e:
        logger.error(f"连接客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"连接失败: {str(e)}"
        )


@router.post(
    "/client/disconnect",
    summary="断开 WebSocket 客户端",
    response_model=WSClientStatusOut,
)
async def disconnect_client(request: WSClientDisconnectIn) -> WSClientStatusOut:
    """
    断开指定客户端的连接
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    try:
        await _manager.disconnect_client(request.name)
        return WSClientStatusOut(
            code=200,
            status="success",
            message=f"客户端 [{request.name}] 已断开",
            data={
                "name": request.name,
                "is_connected": False
            }
        )
    except Exception as e:
        logger.error(f"断开客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"断开失败: {str(e)}"
        )


@router.post(
    "/client/remove",
    summary="删除 WebSocket 客户端",
    response_model=WSClientStatusOut,
)
async def remove_client(request: WSClientRemoveIn) -> WSClientStatusOut:
    """
    删除指定客户端（会自动断开连接）
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    try:
        await _manager.remove_client(request.name)
        return WSClientStatusOut(
            code=200,
            status="success",
            message=f"客户端 [{request.name}] 已删除"
        )
    except Exception as e:
        logger.error(f"删除客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"删除失败: {str(e)}"
        )


@router.post(
    "/client/status",
    summary="获取客户端状态",
    response_model=WSClientStatusOut,
)
async def get_client_status(request: WSClientStatusIn) -> WSClientStatusOut:
    """
    获取指定客户端的状态信息
    """
    client = _manager.get_client(request.name)
    if not client:
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    return WSClientStatusOut(
        code=200,
        status="success",
        message="获取状态成功",
        data={
            "name": request.name,
            "url": client.url,
            "is_connected": client.is_connected,
            "ping_interval": client.ping_interval,
            "ping_timeout": client.ping_timeout,
            "reconnect_interval": client.reconnect_interval,
            "max_reconnect_attempts": client.max_reconnect_attempts
        }
    )


@router.get(
    "/client/list",
    summary="列出所有客户端",
    response_model=WSClientListOut,
)
async def list_clients() -> WSClientListOut:
    """
    获取所有已创建的 WebSocket 客户端列表及状态
    """
    clients = _manager.list_clients()
    return WSClientListOut(
        code=200,
        status="success",
        message=f"共 {len(clients)} 个客户端",
        data={
            "clients": list(clients.values()),
            "count": len(clients)
        }
    )


@router.post(
    "/message/send",
    summary="发送原始消息",
    response_model=WSClientStatusOut,
)
async def send_message(request: WSClientSendIn) -> WSClientStatusOut:
    """
    发送原始 JSON 消息到指定客户端连接的服务器
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    client = _manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400,
            status="error",
            message=f"客户端 [{request.name}] 未连接"
        )
    
    try:
        success = await _manager.send_message(request.name, request.message)
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message="消息发送成功",
                data={"sent": request.message}
            )
        else:
            return WSClientStatusOut(
                code=500,
                status="error",
                message="消息发送失败"
            )
    except Exception as e:
        logger.error(f"发送消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"发送失败: {str(e)}"
        )


@router.post(
    "/message/send_json",
    summary="发送格式化消息",
    response_model=WSClientStatusOut,
)
async def send_json_message(request: WSClientSendJsonIn) -> WSClientStatusOut:
    """
    发送格式化的 JSON 消息（自动组装 id、type、data 结构）
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    client = _manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400,
            status="error",
            message=f"客户端 [{request.name}] 未连接"
        )
    
    message = {
        "id": request.msg_id,
        "type": request.msg_type,
        "data": request.data
    }
    
    try:
        success = await _manager.send_message(request.name, message)
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message="消息发送成功",
                data={"sent": message}
            )
        else:
            return WSClientStatusOut(
                code=500,
                status="error",
                message="消息发送失败"
            )
    except Exception as e:
        logger.error(f"发送消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"发送失败: {str(e)}"
        )


@router.post(
    "/message/auth",
    summary="发送认证消息",
    response_model=WSClientStatusOut,
)
async def send_auth(request: WSClientAuthIn) -> WSClientStatusOut:
    """
    发送认证消息到服务器
    
    - **name**: 客户端名称
    - **token**: 认证 Token
    - **auth_type**: 认证消息类型，默认 "auth"
    - **extra_data**: 额外的认证数据
    """
    if not _manager.has_client(request.name):
        return WSClientStatusOut(
            code=404,
            status="error",
            message=f"客户端 [{request.name}] 不存在"
        )
    
    client = _manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400,
            status="error",
            message=f"客户端 [{request.name}] 未连接"
        )
    
    try:
        success = await _manager.send_auth(
            name=request.name,
            token=request.token,
            auth_type=request.auth_type,
            extra_data=request.extra_data
        )
        
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message="认证消息发送成功"
            )
        else:
            return WSClientStatusOut(
                code=500,
                status="error",
                message="认证消息发送失败"
            )
    except Exception as e:
        logger.error(f"发送认证消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500,
            status="error",
            message=f"发送失败: {str(e)}"
        )


@router.get(
    "/history",
    summary="获取消息历史",
    response_model=WSMessageHistoryOut,
)
async def get_history(name: Optional[str] = None) -> WSMessageHistoryOut:
    """
    获取消息历史记录
    
    - **name**: 客户端名称，为空则获取所有客户端的历史
    """
    history = _manager.get_message_history(name)
    
    total_count = sum(len(msgs) for msgs in history.values())
    
    return WSMessageHistoryOut(
        code=200,
        status="success",
        message=f"共 {total_count} 条消息",
        data={
            "history": history,
            "total_count": total_count
        }
    )


@router.post(
    "/history/clear",
    summary="清空消息历史",
    response_model=WSClientStatusOut,
)
async def clear_history(request: WSClearHistoryIn) -> WSClientStatusOut:
    """
    清空消息历史记录
    
    - **name**: 客户端名称，为空则清空所有
    """
    _manager.clear_message_history(request.name)
    
    if request.name:
        return WSClientStatusOut(
            code=200,
            status="success",
            message=f"已清空客户端 [{request.name}] 的消息历史"
        )
    else:
        return WSClientStatusOut(
            code=200,
            status="success",
            message="已清空所有消息历史"
        )


@router.get(
    "/commands",
    summary="获取可用 WS 命令",
    response_model=WSCommandsOut,
)
async def get_commands() -> WSCommandsOut:
    """
    获取所有已注册的 WebSocket 命令端点
    """
    commands = list_ws_commands()
    return WSCommandsOut(
        code=200,
        status="success",
        message=f"共 {len(commands)} 个命令",
        data={
            "commands": commands,
            "count": len(commands)
        }
    )


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    实时消息推送 WebSocket 端点
    
    前端连接此端点后，可实时接收所有客户端的消息和事件
    """
    await websocket.accept()
    _manager.add_debug_connection(websocket)
    
    logger.info(f"调试前端已连接: {websocket.client}")
    
    try:
        # 发送当前所有客户端状态
        clients = _manager.list_clients()
        await websocket.send_json({
            "type": "init",
            "clients": list(clients.values())
        })
        
        # 发送历史消息
        history = _manager.get_message_history()
        for client_name, messages in history.items():
            for msg in messages:
                await websocket.send_json({
                    "type": "message",
                    "client": client_name,
                    **msg
                })
        
        # 保持连接，接收心跳
        while True:
            try:
                data = await websocket.receive_text()
                # 处理心跳或其他命令
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket 错误: {e}")
                break
    
    finally:
        _manager.remove_debug_connection(websocket)
        logger.info(f"调试前端已断开: {websocket.client}")
