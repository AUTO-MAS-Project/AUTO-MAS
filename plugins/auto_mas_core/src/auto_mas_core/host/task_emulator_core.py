"""真实宿主模块 app.task.emulator_core 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.task.emulator_core import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.task.emulator_core 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        return getattr(import_module("app.task.emulator_core"), name)
