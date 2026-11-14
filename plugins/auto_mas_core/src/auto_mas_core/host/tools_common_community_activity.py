"""真实宿主模块 app.tools.common.community.activity 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.common.community.activity import *  # noqa: F403 - SDK 静态导出与真实宿主定义保持一致。
    from app.tools.common.community.activity import parser as parser
    from app.tools.common.community.activity import provider as provider
    from app.tools.common.community.activity import roles as roles
    from app.tools.common.community.activity import transport as transport
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.tools.common.community.activity 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name in ("parser", "provider", "roles", "transport"):
            return import_module(f"app.tools.common.community.activity.{name}")
        return getattr(import_module("app.tools.common.community.activity"), name)
