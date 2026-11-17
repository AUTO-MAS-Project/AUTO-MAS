"""真实宿主模块 app.utils.common.config 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.utils.common.config import *  # noqa: F403 - SDK 静态导出与真实宿主定义保持一致。
    from app.utils.common.config import archive as archive
    from app.utils.common.config import document as document
    from app.utils.common.config import restore as restore
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.config 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name in ("archive", "document", "restore"):
            return import_module(f"app.utils.common.config.{name}")
        return getattr(import_module("app.utils.common.config"), name)
