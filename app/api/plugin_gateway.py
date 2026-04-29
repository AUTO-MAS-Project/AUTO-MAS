from __future__ import annotations

import inspect
import json
from typing import Any

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.core.plugins.server import (
    PluginHttpRequest,
    PluginHttpResponse,
    PluginWebSocketSession,
    plugin_server,
    serialize_plugin_result,
)
from app.utils import get_logger


router = APIRouter(prefix="/plugin", tags=["插件声明式服务"])
logger = get_logger("插件服务网关")


async def _maybe_await(value: Any) -> Any:
    """兼容同步与异步插件回调。"""
    if inspect.isawaitable(value):
        return await value
    return value


def _call_ws_handler(handler: Any, message: Any, session: PluginWebSocketSession) -> Any:
    """根据插件 WS 回调签名注入消息与会话对象。"""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(message, session)

    params = list(signature.parameters.values())
    if not params:
        return handler()

    has_var_keyword = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params)
    if has_var_keyword or "session" in signature.parameters:
        return handler(message, session=session)

    positional = [
        item
        for item in params
        if item.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return handler(message, session)
    return handler(message)


def _call_ws_lifecycle(handler: Any, session: PluginWebSocketSession) -> Any:
    """根据插件 WS 生命周期回调签名注入会话对象。"""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(session)

    if not signature.parameters:
        return handler()
    return handler(session)


def _to_response(result: Any) -> Response:
    """把插件 HTTP 返回值转换为标准响应。"""
    data = serialize_plugin_result(result)
    if isinstance(data, PluginHttpResponse):
        body = serialize_plugin_result(data.body)
        if isinstance(body, (dict, list)) or body is None:
            return JSONResponse(
                content=body,
                status_code=data.status_code,
                headers=data.headers,
                media_type=data.media_type,
            )
        return Response(
            content=str(body),
            status_code=data.status_code,
            headers=data.headers,
            media_type=data.media_type,
        )
    if isinstance(data, (dict, list)) or data is None:
        return JSONResponse(content=data)
    return PlainTextResponse(content=str(data))


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def dispatch_plugin_http(path: str, request: Request) -> Response:
    """分发插件声明式 HTTP 请求。"""
    route_path = f"/{path}".rstrip("/") or "/"
    route = plugin_server.resolve_http(route_path, request.method)
    if route is None:
        return JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "status": "error",
                "message": f"未找到插件服务端点: {request.method} {route_path}",
            },
        )

    body = await request.body()
    json_body: Any = None
    if body:
        try:
            json_body = await request.json()
        except Exception:
            json_body = None

    plugin_request = PluginHttpRequest(
        method=request.method,
        path=route_path,
        query=dict(request.query_params),
        headers={key: value for key, value in request.headers.items()},
        body=body,
        json=json_body,
        instance_id=route.instance_id,
    )
    try:
        result = await plugin_server.dispatch_http(plugin_request)
        return _to_response(result)
    except Exception as exc:
        logger.error(
            f"插件 HTTP 服务执行失败: path={route_path}, instance={route.instance_id}, "
            f"error={type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "status": "error",
                "message": f"插件服务执行失败: {type(exc).__name__}: {exc}",
            },
        )


@router.websocket("/{path:path}")
async def dispatch_plugin_websocket(path: str, websocket: WebSocket) -> None:
    """分发插件声明式 WebSocket 请求。"""
    route_path = f"/{path}".rstrip("/") or "/"
    route = plugin_server.resolve_websocket(route_path)
    if route is None:
        await websocket.close(code=1008, reason=f"未找到插件 WS 端点: {route_path}")
        return

    await websocket.accept()
    session = PluginWebSocketSession(
        websocket,
        path=route_path,
        instance_id=route.instance_id,
    )

    try:
        if route.on_connect is not None:
            await _maybe_await(_call_ws_lifecycle(route.on_connect, session))

        while True:
            incoming = await websocket.receive()
            if incoming.get("type") == "websocket.disconnect":
                break
            if "json" in incoming:
                message = incoming["json"]
            elif "text" in incoming:
                text = incoming["text"]
                try:
                    message = json.loads(text)
                except json.JSONDecodeError:
                    message = text
            elif "bytes" in incoming:
                message = incoming["bytes"]
            else:
                message = incoming
            await _maybe_await(_call_ws_handler(route.on_message, message, session))
    except Exception as exc:
        logger.error(
            f"插件 WS 服务执行失败: path={route_path}, instance={route.instance_id}, "
            f"error={type(exc).__name__}: {exc}",
            exc_info=True,
        )
        try:
            await websocket.close(code=1011, reason=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        if route.on_disconnect is not None:
            try:
                await _maybe_await(_call_ws_lifecycle(route.on_disconnect, session))
            except Exception as exc:
                logger.warning(
                    f"插件 WS 断开回调失败: path={route_path}, instance={route.instance_id}, "
                    f"error={type(exc).__name__}: {exc}"
                )
