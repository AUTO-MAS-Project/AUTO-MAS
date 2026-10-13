"""跨插件服务注册表；其它模块经 ``Plugin.services.get`` 取用。"""

from __future__ import annotations

from typing import Any

from .errors import PluginBusyError, PluginError
from .signals import service_changed


class ServiceRegistry:
    """``seal()`` 后 ``get`` / ``require`` / ``register`` 拒绝；``unregister`` 仍可用。"""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._owners: dict[str, str] = {}
        self._accepting = True

    @property
    def accepting(self) -> bool:
        return self._accepting

    def seal(self) -> None:
        """停止对外提供服务取用（退出密封）。"""
        self._accepting = False

    def register(self, name: str, value: Any, *, owner: str) -> None:
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
        if name not in self._services:
            return
        if owner is not None and self._owners.get(name) != owner:
            return
        del self._services[name]
        self._owners.pop(name, None)
        service_changed.send(self, name=name, action="unregister", owner=owner)

    def unregister_owner(self, owner: str) -> None:
        for name in [n for n, o in self._owners.items() if o == owner]:
            self.unregister(name, owner=owner)

    def get(self, name: str, default: Any = None) -> Any:
        if not self._accepting:
            return default
        return self._services.get(name, default)

    def require(self, name: str) -> Any:
        if not self._accepting:
            raise PluginBusyError("插件服务已密封，不可取用")
        if name not in self._services:
            raise PluginError(f"服务未注册: {name}", payload={"service": name})
        return self._services[name]

    def list_services(self) -> dict[str, str]:
        return dict(self._owners)
