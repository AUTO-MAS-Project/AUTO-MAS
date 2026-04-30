from __future__ import annotations

import asyncio
import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional

from fastapi import WebSocket
from pydantic import BaseModel

from app.utils.websocket import ws_client_manager


def _normalize_path(path: str) -> str:
    """归一化插件声明路径，确保对外路径不携带实例名前缀。"""
    text = str(path or "").strip()
    if not text:
        raise ValueError("插件服务路径不能为空")
    if "://" in text:
        raise ValueError("插件服务路径必须是相对路径")
    text = "/" + text.lstrip("/")
    text = re.sub(r"/+", "/", text)
    if text != "/" and text.endswith("/"):
        text = text[:-1]
    return text


def _normalize_methods(methods: Iterable[str] | None) -> set[str]:
    """归一化 HTTP 方法列表。"""
    raw_methods = list(methods or ["POST"])
    result: set[str] = set()
    for item in raw_methods:
        method = str(item or "").strip().upper()
        if method:
            result.add(method)
    if not result:
        result.add("POST")
    return result


async def _maybe_await(value: Any) -> Any:
    """兼容同步与异步插件回调。"""
    if inspect.isawaitable(value):
        return await value
    return value


def _call_with_optional_arg(func: Callable[..., Any], arg: Any) -> Any:
    """根据回调签名决定是否注入一个上下文参数。"""
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(arg)

    params = list(signature.parameters.values())
    if not params:
        return func()
    return func(arg)


@dataclass
class PluginHttpRequest:
    """传递给插件 HTTP 处理器的结构化请求。"""

    method: str
    path: str
    query: Dict[str, Any]
    headers: Dict[str, str]
    body: bytes
    json: Any
    instance_id: str


@dataclass
class PluginHttpResponse:
    """插件 HTTP 处理器可显式返回的响应对象。"""

    body: Any = None
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    media_type: str | None = None


@dataclass
class PluginHttpRoute:
    """插件 HTTP 路由声明。"""

    path: str
    methods: set[str]
    instance_id: str
    plugin_name: str
    handler: Callable[..., Any]


@dataclass
class PluginAction:
    """插件前端动作按钮声明。"""

    id: str
    label: str
    path: str
    method: str
    instance_id: str
    plugin_name: str
    payload: Any = None
    refresh: bool = False


@dataclass
class PluginWebSocketRoute:
    """插件反向 WebSocket 路由声明。"""

    path: str
    instance_id: str
    plugin_name: str
    on_message: Callable[..., Any]
    on_connect: Callable[..., Any] | None = None
    on_disconnect: Callable[..., Any] | None = None
    ping_interval: float = 15.0
    ping_timeout: float = 30.0


class PluginWebSocketSession:
    """暴露给插件的 WebSocket 会话门面。"""

    def __init__(self, websocket: WebSocket, *, path: str, instance_id: str) -> None:
        self.websocket = websocket
        self.path = path
        self.instance_id = instance_id

    async def send_json(self, data: Any) -> None:
        """发送 JSON 消息。"""
        await self.websocket.send_json(data)

    async def send_text(self, data: str) -> None:
        """发送文本消息。"""
        await self.websocket.send_text(data)

    async def close(self, code: int = 1000, reason: str = "正常关闭") -> None:
        """关闭当前 WebSocket 连接。"""
        await self.websocket.close(code=code, reason=reason)


class PluginServerRegistry:
    """管理插件声明式 HTTP、WebSocket 与前端动作。"""

    def __init__(self) -> None:
        self._http_routes: Dict[str, PluginHttpRoute] = {}
        self._ws_routes: Dict[str, PluginWebSocketRoute] = {}
        self._actions: Dict[str, Dict[str, PluginAction]] = {}
        self._outbound_names: Dict[str, set[str]] = {}

    def register_http(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        path: str,
        handler: Callable[..., Any],
        methods: Iterable[str] | None = None,
    ) -> PluginHttpRoute:
        """注册插件 HTTP 路由。"""
        route_path = _normalize_path(path)
        owner = self._route_owner(route_path)
        if owner and owner != instance_id:
            raise ValueError(
                f"插件服务路径冲突: path={route_path}, owner={instance_id}, existing={owner}"
            )
        route = PluginHttpRoute(
            path=route_path,
            methods=_normalize_methods(methods),
            instance_id=instance_id,
            plugin_name=plugin_name,
            handler=handler,
        )
        self._http_routes[route_path] = route
        return route

    def register_action(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        action_id: str,
        label: str,
        path: str,
        method: str = "POST",
        payload: Any = None,
        refresh: bool = False,
    ) -> PluginAction:
        """注册插件前端动作按钮。"""
        normalized_id = str(action_id or "").strip()
        normalized_label = str(label or "").strip()
        if not normalized_id:
            raise ValueError("插件动作 ID 不能为空")
        if not normalized_label:
            raise ValueError("插件动作标题不能为空")

        action = PluginAction(
            id=normalized_id,
            label=normalized_label,
            path=_normalize_path(path),
            method=str(method or "POST").strip().upper() or "POST",
            payload=payload,
            refresh=bool(refresh),
            instance_id=instance_id,
            plugin_name=plugin_name,
        )
        actions = self._actions.setdefault(instance_id, {})
        if normalized_id in actions:
            raise ValueError(f"插件动作 ID 重复: instance={instance_id}, action={normalized_id}")
        actions[normalized_id] = action
        return action

    def register_websocket(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        path: str,
        on_message: Callable[..., Any],
        on_connect: Callable[..., Any] | None = None,
        on_disconnect: Callable[..., Any] | None = None,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> PluginWebSocketRoute:
        """注册插件反向 WebSocket 路由。"""
        route_path = _normalize_path(path)
        owner = self._route_owner(route_path)
        if owner and owner != instance_id:
            raise ValueError(
                f"插件服务路径冲突: path={route_path}, owner={instance_id}, existing={owner}"
            )
        route = PluginWebSocketRoute(
            path=route_path,
            instance_id=instance_id,
            plugin_name=plugin_name,
            on_message=on_message,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
        )
        self._ws_routes[route_path] = route
        return route

    async def open_outbound_ws(
        self,
        *,
        instance_id: str,
        name: str,
        url: str,
        on_message: Callable[..., Any] | None = None,
        on_connect: Callable[..., Any] | None = None,
        on_disconnect: Callable[..., Any] | None = None,
        reconnect: bool = True,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> Any:
        """为插件打开一个正向 WebSocket 连接。"""
        safe_name = str(name or "").strip()
        if not safe_name:
            raise ValueError("正向 WebSocket 名称不能为空")
        client_name = f"plugin:{instance_id}:{safe_name}"

        async def wrapped_message(data: Dict[str, Any]) -> None:
            if on_message is not None:
                await _maybe_await(_call_with_optional_arg(on_message, data))

        async def wrapped_connect() -> None:
            if on_connect is not None:
                await _maybe_await(_call_with_optional_arg(on_connect, client_name))

        async def wrapped_disconnect() -> None:
            if on_disconnect is not None:
                await _maybe_await(_call_with_optional_arg(on_disconnect, client_name))

        client = await ws_client_manager.create_client(
            name=client_name,
            url=url,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            reconnect_interval=5.0,
            max_reconnect_attempts=-1 if reconnect else 0,
            on_message=wrapped_message,
            on_connect=wrapped_connect,
            on_disconnect=wrapped_disconnect,
        )
        self._outbound_names.setdefault(instance_id, set()).add(client_name)
        await ws_client_manager.connect_client(client_name)
        return client

    def resolve_http(self, path: str, method: str) -> PluginHttpRoute | None:
        """查找匹配当前 HTTP 请求的插件路由。"""
        route = self._http_routes.get(_normalize_path(path))
        if route is None:
            return None
        if method.upper() not in route.methods:
            return None
        return route

    def resolve_websocket(self, path: str) -> PluginWebSocketRoute | None:
        """查找匹配当前 WebSocket 请求的插件路由。"""
        return self._ws_routes.get(_normalize_path(path))

    async def dispatch_http(self, request: PluginHttpRequest) -> Any:
        """调用插件 HTTP 处理器。"""
        route = self.resolve_http(request.path, request.method)
        if route is None:
            return None
        return await _maybe_await(_call_with_optional_arg(route.handler, request))

    async def unregister_owner(self, instance_id: str) -> None:
        """清理指定插件实例声明的全部服务。"""
        owner = str(instance_id or "").strip()
        if not owner:
            return
        self._http_routes = {
            path: route for path, route in self._http_routes.items() if route.instance_id != owner
        }
        self._ws_routes = {
            path: route for path, route in self._ws_routes.items() if route.instance_id != owner
        }
        self._actions.pop(owner, None)

        for client_name in list(self._outbound_names.pop(owner, set())):
            try:
                await ws_client_manager.remove_client(client_name)
            except Exception:
                continue

    def snapshot(self) -> Dict[str, Any]:
        """构建插件服务声明快照，供前端和调试界面使用。"""
        routes: Dict[str, list[Dict[str, Any]]] = {}
        for route in self._http_routes.values():
            routes.setdefault(route.instance_id, []).append(
                {
                    "kind": "http",
                    "path": route.path,
                    "methods": sorted(route.methods),
                    "plugin": route.plugin_name,
                }
            )
        for route in self._ws_routes.values():
            routes.setdefault(route.instance_id, []).append(
                {
                    "kind": "websocket",
                    "path": route.path,
                    "methods": ["WEBSOCKET"],
                    "plugin": route.plugin_name,
                }
            )

        actions: Dict[str, list[Dict[str, Any]]] = {}
        for instance_id, action_map in self._actions.items():
            actions[instance_id] = [
                {
                    "id": action.id,
                    "label": action.label,
                    "path": action.path,
                    "method": action.method,
                    "payload": action.payload,
                    "plugin": action.plugin_name,
                    "refresh": action.refresh,
                }
                for action in action_map.values()
            ]

        return {"plugin_routes": routes, "plugin_actions": actions}

    def _route_owner(self, path: str) -> str | None:
        """返回指定路径当前归属的插件实例。"""
        route = self._http_routes.get(path)
        if route is not None:
            return route.instance_id
        ws_route = self._ws_routes.get(path)
        if ws_route is not None:
            return ws_route.instance_id
        return None


class PluginServerFacade:
    """插件上下文中的 server 门面。"""

    def __init__(self, *, registry: PluginServerRegistry, plugin_name: str, instance_id: str) -> None:
        self._registry = registry
        self._plugin_name = plugin_name
        self._instance_id = instance_id

    def http(
        self,
        path: str,
        handler: Callable[..., Any],
        *,
        methods: Iterable[str] | None = None,
        action: str | Dict[str, Any] | None = None,
    ) -> PluginHttpRoute:
        """声明一个插件 HTTP 端点。"""
        route = self._registry.register_http(
            instance_id=self._instance_id,
            plugin_name=self._plugin_name,
            path=path,
            handler=handler,
            methods=methods,
        )
        if action is not None:
            if isinstance(action, dict):
                action_id = str(action.get("id") or route.path.strip("/").replace("/", ".") or "default")
                label = str(action.get("label") or action_id)
                payload = action.get("payload")
                refresh = bool(action.get("refresh", False))
            else:
                action_id = route.path.strip("/").replace("/", ".") or "default"
                label = str(action)
                payload = None
                refresh = False
            self.action(
                id=action_id,
                label=label,
                path=route.path,
                method=sorted(route.methods)[0],
                payload=payload,
                refresh=refresh,
            )
        return route

    def action(
        self,
        id: str,
        label: str,
        path: str,
        *,
        method: str = "POST",
        payload: Any = None,
        refresh: bool = False,
    ) -> PluginAction:
        """声明一个插件管理页按钮动作。"""
        return self._registry.register_action(
            instance_id=self._instance_id,
            plugin_name=self._plugin_name,
            action_id=id,
            label=label,
            path=path,
            method=method,
            payload=payload,
            refresh=refresh,
        )

    def websocket(
        self,
        path: str,
        on_message: Callable[..., Any],
        *,
        on_connect: Callable[..., Any] | None = None,
        on_disconnect: Callable[..., Any] | None = None,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> PluginWebSocketRoute:
        """声明一个插件反向 WebSocket 端点。"""
        return self._registry.register_websocket(
            instance_id=self._instance_id,
            plugin_name=self._plugin_name,
            path=path,
            on_message=on_message,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
        )

    async def open_ws(
        self,
        name: str,
        url: str,
        *,
        on_message: Callable[..., Any] | None = None,
        on_connect: Callable[..., Any] | None = None,
        on_disconnect: Callable[..., Any] | None = None,
        reconnect: bool = True,
        ping_interval: float = 15.0,
        ping_timeout: float = 30.0,
    ) -> Any:
        """打开一个由插件拥有的正向 WebSocket 连接。"""
        return await self._registry.open_outbound_ws(
            instance_id=self._instance_id,
            name=name,
            url=url,
            on_message=on_message,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            reconnect=reconnect,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
        )


def serialize_plugin_result(result: Any) -> Any:
    """将插件返回值转换为 FastAPI 可响应对象。"""
    if isinstance(result, BaseModel):
        return result.model_dump()
    if isinstance(result, PluginHttpResponse):
        return result
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    try:
        json.dumps(result)
        return result
    except TypeError:
        return str(result)


plugin_server = PluginServerRegistry()
