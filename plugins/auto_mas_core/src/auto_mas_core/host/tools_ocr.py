"""启动器与游戏画面的 OCR 能力。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.common.ocr import *  # noqa: F403 - SDK 整包静态再导出，复用宿主自身的公开符号声明。
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.tools.common.ocr 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        return getattr(import_module("app.tools.common.ocr"), name)
