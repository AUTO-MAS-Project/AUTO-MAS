"""插件系统入口：跨插件总线与 HTTP 挂载（与宿主 ``auto_mas_core.services`` 用路径区分）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.plugin.http import HttpRegistry
    from app.plugin.services import ServiceRegistry

    services: ServiceRegistry
    http: HttpRegistry

__all__ = ["services", "http"]


if not TYPE_CHECKING:

    def __getattr__(name: str) -> Any:
        # 与 Manager 同一实例；禁止在此 new 第二份注册表
        """返回宿主插件管理器实际持有的服务或 HTTP 注册表，确保 SDK 不创建第二份注册状态。"""
        if name == "services":
            from app.core.plugin import Plugin

            return Plugin.services
        if name == "http":
            from app.core.plugin import Plugin

            return Plugin.http
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
