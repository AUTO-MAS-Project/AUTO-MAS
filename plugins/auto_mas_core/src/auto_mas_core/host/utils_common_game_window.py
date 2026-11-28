"""真实宿主模块 app.utils.common.game_window 的 SDK 导出。窗口定位、前置与客户区截图。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils.common.game_window import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.game_window 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        return getattr(import_module("app.utils.common.game_window"), name)
