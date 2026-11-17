"""宿主公共通知内容排版工具的 SDK 导出，不包含专项报告逻辑。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.notify.templates import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
else:

    def __getattr__(name: str) -> Any:
        """使用通用排版函数时再加载宿主模块，避免发现插件时提前初始化通知组件。"""
        return getattr(import_module("app.core.notify.templates"), name)
