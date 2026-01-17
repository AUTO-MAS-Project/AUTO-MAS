#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.utils.websocket import ws_client_manager
from app.api.ws_command import list_ws_commands
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

logger = get_logger("WS调试")

router = APIRouter(prefix="/api/ws_debug", tags=["WebSocket调试"])


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


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    实时消息推送 WebSocket 端点

    前端连接此端点后，可实时接收所有客户端的消息和事件
    """
    await websocket.accept()
    ws_client_manager.add_debug_connection(websocket)

    logger.info(f"调试前端已连接: {websocket.client}")

    try:
        # 发送当前所有客户端状态
        clients = ws_client_manager.list_clients()
        await websocket.send_json({"type": "init", "clients": list(clients.values())})

        # 发送历史消息
        history = ws_client_manager.get_message_history()
        for client_name, messages in history.items():
            for msg in messages:
                await websocket.send_json(
                    {"type": "message", "client": client_name, **msg}
                )

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
        ws_client_manager.remove_debug_connection(websocket)
        logger.info(f"调试前端已断开: {websocket.client}")
