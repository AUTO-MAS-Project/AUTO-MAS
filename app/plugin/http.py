"""插件 HTTP：装饰器只写相对 ``/api/plugin/<名>`` 的路径；启用挂载、禁用卸下。"""

from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass, field, replace
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from .calls import call_context

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from .calls import CallGate
    from .frontend import MountedFrontend


PLUGIN_GATEWAY_PATH = "/api/plugin/{plugin_name}/{path:path}"
PLUGIN_UI_PATH = "/api/plugin/{plugin_name}/ui/{path:path}"
_RESERVED_UI_PATH = re.compile(r"(?:/api/plugin/[^/]+)?/ui(?:/|$)")


def _async_endpoint(endpoint):
    """保持同步端点签名，在工作线程执行业务，取消时仍等实际调用退出才释放在途计数。"""
    from starlette.concurrency import run_in_threadpool

    @wraps(endpoint)
    async def invoke(*args, **kwargs):
        """由事件循环持有端点执行；请求取消不会让仍在工作线程使用的插件提前卸载。"""

        def run():
            """在线程入口绑定调用归属，返回事件循环执行生命周期时仍可识别原发起者。"""
            with call_context():
                return endpoint(*args, **kwargs)

        worker = asyncio.create_task(run_in_threadpool(run))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()
            raise

    return invoke


@dataclass
class RouteDecl:
    path: str
    methods: tuple[str, ...]
    handler: Callable[..., Any]
    name: str | None = None


@dataclass
class PluginHttpMount:
    plugin_name: str
    routes: list[RouteDecl] = field(default_factory=list)
    router: APIRouter | None = None
    frontend: MountedFrontend | None = None

    @property
    def prefix(self) -> str:
        """生成当前插件在宿主 HTTP 网关中的独立路由前缀。"""
        return f"/api/plugin/{self.plugin_name}"


class HttpRegistry:
    """插件声明式 HTTP 挂载表。

    ``seal()`` 后网关拒绝对外分发（进程退出第一阶段）；``unmount`` 仍可用。
    """

    def __init__(self) -> None:
        """初始化插件路由挂载表，并允许宿主后续接收路由注册。"""
        self._mounts: dict[str, PluginHttpMount] = {}
        self._accepting = True
        self._app: FastAPI | None = None
        self._typed_routes: dict[str, list[Any]] = {}

    def bind_app(self, app: FastAPI) -> None:
        """绑定宿主路由表，让插件自己提供的类型化端点随启停装卸并参与 OpenAPI。"""
        if self._app is not None:
            raise RuntimeError("插件 HTTP 已绑定应用")
        self._app = app

    @property
    def accepting(self) -> bool:
        """返回 HTTP 注册表是否仍允许挂载插件路由。"""
        return self._accepting

    def seal(self) -> None:
        """停止接受外部 HTTP 请求（退出密封）。"""
        self._accepting = False

    def invalidate_schema(self) -> None:
        """插件声明变化后清除宿主契约缓存，使下一次查询反映当前可用能力。"""
        if self._app is not None:
            self._app.openapi_schema = None

    def mount(
        self,
        plugin_name: str,
        routes: list[RouteDecl],
        *,
        router: APIRouter | None = None,
        gate: CallGate | None = None,
        frontend: MountedFrontend | None = None,
    ) -> PluginHttpMount:
        """为指定插件登记路由声明副本并返回挂载记录，注册表关闭时拒绝新增。"""
        if not self._accepting:
            raise RuntimeError("插件 HTTP 已密封，不可再挂载")
        if any(
            _RESERVED_UI_PATH.match("/" + route.path.lstrip("/")) for route in routes
        ) or (
            router is not None
            and any(
                _RESERVED_UI_PATH.match(getattr(route, "path", ""))
                for route in router.routes
            )
        ):
            raise ValueError(f"插件 {plugin_name} 的 /ui 路径保留给界面资源")
        mount = PluginHttpMount(
            plugin_name=plugin_name,
            routes=list(routes),
            router=router,
            frontend=frontend,
        )
        if router is not None and self._app is not None:
            from copy import copy

            from fastapi import APIRouter
            from fastapi.routing import APIRoute

            assert gate is not None
            guarded = APIRouter()
            for route in router.routes:
                if not isinstance(route, APIRoute):
                    raise TypeError("插件类型化路由只接受 HTTP API 端点")
                clone = copy(route)
                endpoint = route.endpoint
                if not inspect.iscoroutinefunction(endpoint):
                    endpoint = _async_endpoint(endpoint)
                clone.endpoint = gate.wrap(endpoint)
                guarded.routes.append(clone)
            previous = {id(route) for route in self._app.routes}
            self._app.include_router(guarded)
            self._typed_routes[plugin_name] = [
                route for route in self._app.routes if id(route) not in previous
            ]
            # 同命名空间的具体路由必须先于通用网关；旧的绝对路径路由保留原有优先级。
            gateway_index = next(
                (
                    i
                    for i, route in enumerate(self._app.router.routes)
                    if getattr(route, "path", None) == PLUGIN_GATEWAY_PATH
                ),
                len(self._app.router.routes),
            )
            namespaced = [
                route
                for route in self._typed_routes[plugin_name]
                if route.path == mount.prefix
                or route.path.startswith(mount.prefix + "/")
            ]
            for route in namespaced:
                self._app.router.routes.remove(route)
            self._app.router.routes[gateway_index:gateway_index] = namespaced
            self._app.openapi_schema = None
        self._mounts[plugin_name] = mount
        return mount

    def unmount(self, plugin_name: str) -> None:
        """移除指定插件的全部 HTTP 路由挂载，插件未挂载时保持无操作。"""
        self._mounts.pop(plugin_name, None)
        self.invalidate_schema()
        owned = self._typed_routes.pop(plugin_name, [])
        if owned and self._app is not None:
            identities = {id(route) for route in owned}
            self._app.router.routes = [
                route for route in self._app.routes if id(route) not in identities
            ]
            self._app.openapi_schema = None

    def get(self, plugin_name: str) -> PluginHttpMount | None:
        """按插件名称查询其 HTTP 路由挂载记录。"""
        return self._mounts.get(plugin_name)

    def all_mounts(self) -> dict[str, PluginHttpMount]:
        """返回插件挂载表的副本，供宿主遍历而不直接修改注册表。"""
        return dict(self._mounts)


def plugin_route(path: str, *, methods: list[str] | tuple[str, ...] | None = None):
    """声明相对插件前缀的路由；可叠多个 method。"""
    method_tuple = ("GET",) if methods is None else tuple(m.upper() for m in methods)
    if not method_tuple:
        raise ValueError("插件 HTTP 路由至少需要一个请求方法")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        """把请求路径和方法附加到处理函数的路由声明列表，供插件加载时收集。"""
        decls: list[RouteDecl] = getattr(fn, "__plugin_routes__", [])
        decls.append(RouteDecl(path=path, methods=method_tuple, handler=fn))
        setattr(fn, "__plugin_routes__", decls)
        return fn

    return decorator


def collect_route_decls(obj: Any) -> list[RouteDecl]:
    """从插件实例公开属性收集 ``@plugin_route``。"""
    out: list[RouteDecl] = []
    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(obj, attr_name)
        except Exception:
            continue
        decls = getattr(attr, "__plugin_routes__", None)
        if decls:
            # 装饰时登记的是类上的裸函数，换成实例绑定方法
            out.extend(replace(d, handler=attr) for d in decls)
    return out
