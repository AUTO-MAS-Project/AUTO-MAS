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


"""
WebSocket 客户端调试 API

提供后端作为 WebSocket 客户端连接外部服务器的功能
支持：创建客户端、连接、断开、发送消息、鉴权等
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.utils.websocket import ws_client_manager
from app.api.ws_command import list_ws_commands
from app.core.plugins import PluginManager
from app.core.plugins.market import (
    fetch_market_snapshot,
    collect_installed_distribution_names,
)
from app.utils.logger import get_logger
from app.models.schema import (
    WSClientCreateIn,
    WSClientCreateOut,
    WSClientConnectIn,
    WSClientDisconnectIn,
    WSClientRemoveIn,
    WSClientSendIn,
    WSClientSendJsonIn,
    WSClientAuthIn,
    WSClientStatusIn,
    WSClientStatusOut,
    WSClientListOut,
    WSMessageHistoryOut,
    WSClearHistoryIn,
    WSCommandsOut,
)

logger = get_logger("WS端点")

router = APIRouter(prefix="/api/ws", tags=["Websocket端点"])
WSDEV_CHANNEL_NAME = "wsdev"
PLUGIN_CHANNEL_NAME = "plugin"
PLUGIN_CHANNEL_CLIENT_ID = "PluginMarket"
_plugin_operation_lock = asyncio.Lock()


def _normalize_distribution_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


async def _send_plugin_message(
    event: str,
    *,
    request_id: str | None = None,
    status: str = "success",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    session = ws_client_manager.get_session(PLUGIN_CHANNEL_NAME)
    if session is None:
        return

    await session.send_json(
        {
            "id": PLUGIN_CHANNEL_CLIENT_ID,
            "type": "Message",
            "data": {
                "event": event,
                "request_id": request_id,
                "status": status,
                "message": message,
                "payload": payload or {},
            },
        }
    )


async def _push_installed_sync(
    package_name: str,
    *,
    request_id: str | None = None,
) -> None:
    plugins_dir = Path.cwd() / "plugins"
    installed_names = collect_installed_distribution_names(plugins_dir=plugins_dir)
    normalized = _normalize_distribution_name(package_name)
    await _send_plugin_message(
        "plugin.installed.sync",
        request_id=request_id,
        payload={
            "package": package_name,
            "installed": normalized in installed_names,
        },
    )


async def _handle_plugin_channel_message(data: Dict[str, Any]) -> None:
    action = str(data.get("action") or "").strip()
    request_id = str(data.get("request_id") or "").strip() or None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    if not action:
        await _send_plugin_message(
            "plugin.error",
            request_id=request_id,
            status="error",
            message="缺少 action 字段",
        )
        return

    if action == "market.snapshot.request":
        try:
            limit = int(payload.get("per_prefix_limit") or 60)
            snapshot = await fetch_market_snapshot(
                plugins_dir=Path.cwd() / "plugins",
                per_prefix_limit=max(1, min(limit, 200)),
            )
            await _send_plugin_message(
                "market.snapshot.response",
                request_id=request_id,
                payload=snapshot,
            )
        except Exception as error:
            logger.error(f"构建插件市场快照失败: {type(error).__name__}: {error}")
            await _send_plugin_message(
                "plugin.error",
                request_id=request_id,
                status="error",
                message=f"构建插件市场快照失败: {type(error).__name__}: {error}",
            )
        return

    if action == "plugin.install.request":
        package_name = str(payload.get("package") or "").strip()
        if not package_name:
            await _send_plugin_message(
                "plugin.error",
                request_id=request_id,
                status="error",
                message="安装请求缺少 package",
            )
            return

        await _send_plugin_message(
            "plugin.install.progress",
            request_id=request_id,
            payload={"package": package_name, "progress": 5, "stage": "queued"},
        )

        async with _plugin_operation_lock:
            await _send_plugin_message(
                "plugin.install.progress",
                request_id=request_id,
                payload={"package": package_name, "progress": 30, "stage": "installing"},
            )
            try:
                await PluginManager.install_plugin_package(package_name)
                await _send_plugin_message(
                    "plugin.install.progress",
                    request_id=request_id,
                    payload={"package": package_name, "progress": 100, "stage": "completed"},
                )
                await _send_plugin_message(
                    "plugin.install.result",
                    request_id=request_id,
                    payload={"package": package_name, "success": True},
                    message=f"安装成功: {package_name}",
                )
            except Exception as error:
                await _send_plugin_message(
                    "plugin.install.result",
                    request_id=request_id,
                    status="error",
                    payload={"package": package_name, "success": False},
                    message=f"安装失败: {type(error).__name__}: {error}",
                )
            finally:
                await _push_installed_sync(package_name, request_id=request_id)
        return

    if action == "plugin.uninstall.request":
        package_name = str(payload.get("package") or "").strip()
        if not package_name:
            await _send_plugin_message(
                "plugin.error",
                request_id=request_id,
                status="error",
                message="卸载请求缺少 package",
            )
            return

        async with _plugin_operation_lock:
            try:
                await PluginManager.uninstall_plugin_package(package_name)
                await _send_plugin_message(
                    "plugin.uninstall.result",
                    request_id=request_id,
                    payload={"package": package_name, "success": True},
                    message=f"卸载成功: {package_name}",
                )
            except Exception as error:
                await _send_plugin_message(
                    "plugin.uninstall.result",
                    request_id=request_id,
                    status="error",
                    payload={"package": package_name, "success": False},
                    message=f"卸载失败: {type(error).__name__}: {error}",
                )
            finally:
                await _push_installed_sync(package_name, request_id=request_id)
        return

    if action == "plugin.installed.request":
        package_name = str(payload.get("package") or "").strip()
        if not package_name:
            await _send_plugin_message(
                "plugin.error",
                request_id=request_id,
                status="error",
                message="installed 查询缺少 package",
            )
            return
        await _push_installed_sync(package_name, request_id=request_id)
        return

    await _send_plugin_message(
        "plugin.error",
        request_id=request_id,
        status="error",
        message=f"未知 action: {action}",
    )


async def _on_plugin_channel_connect() -> None:
    await _send_plugin_message(
        "plugin.channel.ready",
        payload={"channel": PLUGIN_CHANNEL_NAME},
        message="plugin 通道已连接",
    )


async def _send_wsdev_snapshot(websocket: WebSocket):
    """
    发送 wsdev 初始化快照。

    Args:
        websocket: 当前调试前端的 WebSocket 连接。

    Raises:
        Exception: 发送初始化数据失败时抛出底层异常。
    """
    # 发送当前所有客户端状态
    clients = ws_client_manager.list_clients()
    await websocket.send_json({"type": "init", "clients": list(clients.values())})

    # 发送历史消息
    history = ws_client_manager.get_message_history()
    for client_name, messages in history.items():
        for msg in messages:
            await websocket.send_json({"type": "message", "client": client_name, **msg})


async def _invoke_declared_callback(callback: Optional[Callable], *args):
    """
    调用声明式回调并自动兼容同步/异步函数。

    Args:
        callback: 声明式回调函数。
        *args: 传递给回调的参数。

    Raises:
        Exception: 回调执行过程中抛出的原始异常会向上抛出。
    """
    if callback is None:
        return

    result = callback(*args)
    if hasattr(result, "__await__"):
        await result


def _build_channel_handlers(
    channel_name: str,
    websocket: WebSocket,
    channel_config: Dict[str, Any],
):
    """
    构建声明式通道的消息与生命周期回调。

    Args:
        channel_name: 通道名称。
        websocket: 当前 WebSocket 连接。
        channel_config: 通道声明配置。

    Returns:
        tuple: `(on_message, on_connect, on_disconnect)` 三个回调。
    """
    declared_on_message = channel_config.get("on_message")
    declared_on_connect = channel_config.get("on_connect")
    declared_on_disconnect = channel_config.get("on_disconnect")

    if channel_name == WSDEV_CHANNEL_NAME:

        async def on_message(data: Dict[str, Any]):
            action = data.get("action") if isinstance(data, dict) else None
            if action == "ping":
                await websocket.send_text("pong")
            elif action == "request_snapshot":
                await _send_wsdev_snapshot(websocket)
            await _invoke_declared_callback(declared_on_message, data)

        async def on_connect():
            ws_client_manager.add_debug_connection(websocket)
            logger.info(f"调试前端已连接 (/api/ws/{channel_name}): {websocket.client}")
            await _send_wsdev_snapshot(websocket)
            await _invoke_declared_callback(declared_on_connect)

        async def on_disconnect():
            ws_client_manager.remove_debug_connection(websocket)
            logger.info(f"调试前端已断开 (/api/ws/{channel_name}): {websocket.client}")
            await _invoke_declared_callback(declared_on_disconnect)

        return on_message, on_connect, on_disconnect

    async def on_message(data: Dict[str, Any]):
        await _invoke_declared_callback(declared_on_message, data)

    async def on_connect():
        logger.info(f"声明通道已连接 (/api/ws/{channel_name}): {websocket.client}")
        await _invoke_declared_callback(declared_on_connect)

    async def on_disconnect():
        logger.info(f"声明通道已断开 (/api/ws/{channel_name}): {websocket.client}")
        await _invoke_declared_callback(declared_on_disconnect)

    return on_message, on_connect, on_disconnect


def _register_builtin_reverse_channels():
    """
    注册内置声明式反向通道。

    Raises:
        ValueError: 当内置通道名称非法或与保留名称冲突时抛出。
    """
    ws_client_manager.register_reverse_channel(
        name=WSDEV_CHANNEL_NAME,
        ping_interval=15.0,
        ping_timeout=30.0,
        overwrite=True,
    )
    ws_client_manager.register_reverse_channel(
        name=PLUGIN_CHANNEL_NAME,
        ping_interval=15.0,
        ping_timeout=30.0,
        on_message=_handle_plugin_channel_message,
        on_connect=_on_plugin_channel_connect,
        overwrite=True,
    )


_register_builtin_reverse_channels()

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
        client = await ws_client_manager.create_client(
            name=request.name,
            url=request.url,
            ping_interval=request.ping_interval,
            ping_timeout=request.ping_timeout,
            reconnect_interval=request.reconnect_interval,
            max_reconnect_attempts=request.max_reconnect_attempts,
        )

        return WSClientCreateOut(
            code=200,
            status="success",
            message=f"客户端 [{request.name}] 创建成功",
            data={
                "name": request.name,
                "url": request.url,
                "is_connected": client.is_connected,
            },
        )
    except Exception as e:
        logger.error(f"创建客户端失败: {type(e).__name__}: {e}")
        return WSClientCreateOut(
            code=500, status="error", message=f"创建客户端失败: {str(e)}"
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
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    try:
        success = await ws_client_manager.connect_client(request.name)
        client = ws_client_manager.get_client(request.name)

        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message=f"客户端 [{request.name}] 连接成功",
                data={
                    "name": request.name,
                    "url": client.url if client else None,
                    "is_connected": True,
                },
            )
        else:
            return WSClientStatusOut(
                code=500,
                status="error",
                message=f"客户端 [{request.name}] 连接失败或超时",
                data={
                    "name": request.name,
                    "is_connected": client.is_connected if client else False,
                },
            )
    except Exception as e:
        logger.error(f"连接客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"连接失败: {str(e)}"
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
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    try:
        await ws_client_manager.disconnect_client(request.name)
        return WSClientStatusOut(
            code=200,
            status="success",
            message=f"客户端 [{request.name}] 已断开",
            data={"name": request.name, "is_connected": False},
        )
    except Exception as e:
        logger.error(f"断开客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"断开失败: {str(e)}"
        )


@router.post(
    "/client/remove",
    summary="删除 WebSocket 客户端",
    response_model=WSClientStatusOut,
)
async def remove_client(request: WSClientRemoveIn) -> WSClientStatusOut:
    """
    删除指定客户端（会自动断开连接）

    注意：系统客户端（如 Koishi）不可删除
    """
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    # 检查是否为系统客户端
    if ws_client_manager.is_system_client(request.name):
        return WSClientStatusOut(
            code=403,
            status="error",
            message=f"客户端 [{request.name}] 是系统客户端，不可删除",
        )

    try:
        await ws_client_manager.remove_client(request.name)
        return WSClientStatusOut(
            code=200, status="success", message=f"客户端 [{request.name}] 已删除"
        )
    except Exception as e:
        logger.error(f"删除客户端失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"删除失败: {str(e)}"
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
    client = ws_client_manager.get_client(request.name)
    if not client:
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
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
            "max_reconnect_attempts": client.max_reconnect_attempts,
        },
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
    clients = ws_client_manager.list_clients()
    return WSClientListOut(
        code=200,
        status="success",
        message=f"共 {len(clients)} 个客户端",
        data={"clients": list(clients.values()), "count": len(clients)},
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
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    client = ws_client_manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400, status="error", message=f"客户端 [{request.name}] 未连接"
        )

    try:
        success = await ws_client_manager.send_message(request.name, request.message)
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message="消息发送成功",
                data={"sent": request.message},
            )
        else:
            return WSClientStatusOut(code=500, status="error", message="消息发送失败")
    except Exception as e:
        logger.error(f"发送消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"发送失败: {str(e)}"
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
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    client = ws_client_manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400, status="error", message=f"客户端 [{request.name}] 未连接"
        )

    message = {"id": request.msg_id, "type": request.msg_type, "data": request.data}

    try:
        success = await ws_client_manager.send_message(request.name, message)
        if success:
            return WSClientStatusOut(
                code=200,
                status="success",
                message="消息发送成功",
                data={"sent": message},
            )
        else:
            return WSClientStatusOut(code=500, status="error", message="消息发送失败")
    except Exception as e:
        logger.error(f"发送消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"发送失败: {str(e)}"
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
    if not ws_client_manager.has_client(request.name):
        return WSClientStatusOut(
            code=404, status="error", message=f"客户端 [{request.name}] 不存在"
        )

    client = ws_client_manager.get_client(request.name)
    if not client or not client.is_connected:
        return WSClientStatusOut(
            code=400, status="error", message=f"客户端 [{request.name}] 未连接"
        )

    try:
        success = await ws_client_manager.send_auth(
            name=request.name,
            token=request.token,
            auth_type=request.auth_type,
            extra_data=request.extra_data,
        )

        if success:
            return WSClientStatusOut(
                code=200, status="success", message="认证消息发送成功"
            )
        else:
            return WSClientStatusOut(
                code=500, status="error", message="认证消息发送失败"
            )
    except Exception as e:
        logger.error(f"发送认证消息失败: {type(e).__name__}: {e}")
        return WSClientStatusOut(
            code=500, status="error", message=f"发送失败: {str(e)}"
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
    history = ws_client_manager.get_message_history(name)

    total_count = sum(len(msgs) for msgs in history.values())

    return WSMessageHistoryOut(
        code=200,
        status="success",
        message=f"共 {total_count} 条消息",
        data={"history": history, "total_count": total_count},
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
    ws_client_manager.clear_message_history(request.name)

    if request.name:
        return WSClientStatusOut(
            code=200,
            status="success",
            message=f"已清空客户端 [{request.name}] 的消息历史",
        )
    else:
        return WSClientStatusOut(
            code=200, status="success", message="已清空所有消息历史"
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
        data={"commands": commands, "count": len(commands)},
    )


@router.websocket("/{channel_name}")
async def websocket_dynamic_channel(websocket: WebSocket, channel_name: str):
    """
    声明式动态 WebSocket 端点。

    路由会根据 `channel_name` 查找管理器中的声明配置，
    并统一通过 `openwsr` 接管当前连接。

    Raises:
        Exception: 会话创建或运行失败时抛出底层异常。
    """
    channel_config = ws_client_manager.get_reverse_channel_config(channel_name)
    if channel_config is None:
        logger.warning(f"未声明的反向通道连接被拒绝: /api/ws/{channel_name}")
        await websocket.close(code=1008, reason=f"未声明通道: {channel_name}")
        return

    await websocket.accept()

    on_message, on_connect, on_disconnect = _build_channel_handlers(
        channel_name=channel_name,
        websocket=websocket,
        channel_config=channel_config,
    )

    session = await ws_client_manager.openwsr(
        name=channel_name,
        websocket=websocket,
        ping_interval=float(channel_config.get("ping_interval", 15.0)),
        ping_timeout=float(channel_config.get("ping_timeout", 30.0)),
        auth_token=channel_config.get("auth_token"),
        on_message=on_message,
        on_connect=on_connect,
        on_disconnect=on_disconnect,
    )
    await session.wait_closed()
