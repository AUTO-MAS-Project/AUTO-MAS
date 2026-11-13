"""真实宿主模块 app.task.proxy_helpers 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.task.proxy_helpers import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
    from app.task.proxy_helpers import (
        CONFIG_BASE_INDEPENDENT as CONFIG_BASE_INDEPENDENT,
    )
    from app.task.proxy_helpers import CONFIG_BASE_NATIVE as CONFIG_BASE_NATIVE
    from app.task.proxy_helpers import CONFIG_BASE_SHARED as CONFIG_BASE_SHARED
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.task.proxy_helpers 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        return getattr(import_module("app.task.proxy_helpers"), name)
