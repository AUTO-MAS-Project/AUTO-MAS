"""真实宿主模块 app.services 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
    from app.services import script_install as script_install
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.services 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name == "script_install":
            return import_module("app.services.script_install")
        return getattr(import_module("app.services"), name)
