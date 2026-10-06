"""插件 HTTP：装饰器只写相对 ``/api/plugin/<名>`` 的路径；启用挂载、禁用卸下。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable


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

    @property
    def prefix(self) -> str:
        return f"/api/plugin/{self.plugin_name}"


class HttpRegistry:
    """插件声明式 HTTP 挂载表。

    ``seal()`` 后网关拒绝对外分发（进程退出第一阶段）；``unmount`` 仍可用。
    """

    def __init__(self) -> None:
        self._mounts: dict[str, PluginHttpMount] = {}
        self._accepting = True

    @property
    def accepting(self) -> bool:
        return self._accepting

    def seal(self) -> None:
        """停止接受外部 HTTP 请求（退出密封）。"""
        self._accepting = False

    def mount(self, plugin_name: str, routes: list[RouteDecl]) -> PluginHttpMount:
        if not self._accepting:
            raise RuntimeError("插件 HTTP 已密封，不可再挂载")
        mount = PluginHttpMount(plugin_name=plugin_name, routes=list(routes))
        self._mounts[plugin_name] = mount
        return mount

    def unmount(self, plugin_name: str) -> None:
        self._mounts.pop(plugin_name, None)

    def get(self, plugin_name: str) -> PluginHttpMount | None:
        return self._mounts.get(plugin_name)

    def all_mounts(self) -> dict[str, PluginHttpMount]:
        return dict(self._mounts)


def plugin_route(path: str, *, methods: list[str] | tuple[str, ...] | None = None):
    """声明相对插件前缀的路由；可叠多个 method。"""
    method_tuple = tuple(m.upper() for m in (methods or ("GET",)))

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
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
