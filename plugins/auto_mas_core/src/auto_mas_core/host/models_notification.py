"""真实宿主模块 app.models.notification 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.notification import *  # noqa: F403 - SDK 静态导出与真实宿主定义保持一致。
    from app.models.notification import channel as channel
    from app.models.notification import community as community
    from app.models.notification import report as report
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.models.notification 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name in ("channel", "community", "report"):
            return import_module(f"app.models.notification.{name}")
        return getattr(import_module("app.models.notification"), name)
