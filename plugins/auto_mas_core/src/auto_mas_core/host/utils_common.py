"""真实宿主模块 app.utils.common 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils.common import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
    from app.utils.common import game_window as game_window
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name == "game_window":
            return import_module("app.utils.common.game_window")
        return getattr(import_module("app.utils.common"), name)
