"""宿主业务服务；与跨插件服务总线的导入路径区分。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core import BackgroundTaskManager, Notify
    from app.core.downloads import Downloads
    from app.core.plugin.operations import Operations

__all__ = ["BackgroundTaskManager", "Downloads", "Notify", "Operations"]


if not TYPE_CHECKING:

    def __getattr__(name: str) -> Any:
        """按 SDK 公开服务名称惰性取得宿主单例，未公开服务拒绝访问。"""
        if name not in __all__:
            raise AttributeError(name)
        if name == "Operations":
            from app.core.plugin.operations import Operations

            return Operations
        import app.core as host_core

        return getattr(host_core, name)


def __dir__() -> list[str]:
    """返回 SDK 允许访问的服务名称，供交互补全和运行时属性检查使用。"""
    return list(__all__)
