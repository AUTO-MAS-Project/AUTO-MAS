"""真实宿主模块 app.core.ws 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.ws import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
    from app.core.ws import protocol as protocol
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.core.ws 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name == "protocol":
            return import_module("app.core.ws.protocol")
        return getattr(import_module("app.core.ws"), name)
