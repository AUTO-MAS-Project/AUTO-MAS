"""跨插件服务注册表；其它模块经 ``Plugin.services.get`` 取用。"""

from __future__ import annotations

from typing import Any, Protocol

from .errors import PluginBusyError, PluginError
from .signals import service_changed


class ServiceResolver(Protocol):
    """插件消费服务的查询契约；登记与注销由宿主负责。"""

    def get(self, name: str, default: Any = None) -> Any:
        """按服务名称查询可选能力，未提供时返回指定默认值。"""
        ...

    def require(self, name: str) -> Any:
        """取得调用方必须依赖的服务，缺失或暂不可用时报告错误。"""
        ...


class ServiceRegistry:
    """``seal()`` 后 ``get`` / ``require`` / ``register`` 拒绝；``unregister`` 仍可用。"""

    def __init__(self) -> None:
        """初始化插件服务实例及提供者登记表，默认允许服务注册和查询。"""
        self._services: dict[str, Any] = {}
        self._owners: dict[str, str] = {}
        self._accepting = True

    @property
    def accepting(self) -> bool:
        """返回服务注册表是否仍处于可注册和查询状态。"""
        return self._accepting

    def seal(self) -> None:
        """停止对外提供服务取用（退出密封）。"""
        self._accepting = False

    def register(self, name: str, value: Any, *, owner: str) -> None:
        """以插件为所有者登记服务，拒绝跨插件同名覆盖，并发布服务变更信号。"""
        if not self._accepting:
            raise PluginBusyError("插件服务已密封，不可再注册")
        if name in self._services and self._owners.get(name) != owner:
            raise PluginError(
                f"服务 `{name}` 已被插件 `{self._owners[name]}` 注册",
                payload={"service": name, "owner": self._owners[name]},
            )
        self._services[name] = value
        self._owners[name] = owner
        service_changed.send(self, name=name, action="register", owner=owner)

    def unregister(self, name: str, *, owner: str | None = None) -> None:
        """在所有者匹配时移除指定服务并发布变更信号，服务不存在时保持无操作。"""
        if name not in self._services:
            return
        if owner is not None and self._owners.get(name) != owner:
            return
        del self._services[name]
        self._owners.pop(name, None)
        service_changed.send(self, name=name, action="unregister", owner=owner)

    def unregister_owner(self, owner: str) -> None:
        """注销指定插件发布的全部服务，供停用或卸载时清理。"""
        for name in [n for n, o in self._owners.items() if o == owner]:
            self.unregister(name, owner=owner)

    def get(self, name: str, default: Any = None) -> Any:
        """查询可选服务，服务缺失或注册表停止服务时返回默认值。"""
        if not self._accepting:
            return default
        return self._services.get(name, default)

    def require(self, name: str) -> Any:
        """查询必需服务，注册表已关闭或名称未登记时明确报告不可用。"""
        if not self._accepting:
            raise PluginBusyError("插件服务已密封，不可取用")
        if name not in self._services:
            raise PluginError(f"服务未注册: {name}", payload={"service": name})
        return self._services[name]

    def list_services(self) -> dict[str, str]:
        """返回服务名称到提供者的映射副本，供宿主检查服务归属。"""
        return dict(self._owners)
