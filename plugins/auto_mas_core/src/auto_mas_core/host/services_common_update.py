"""真实宿主模块 app.services.common.update 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.common.update import *  # noqa: F403 - SDK 静态导出与真实宿主定义保持一致。
    from app.services.common.update import fluxdown as fluxdown
    from app.services.common.update import fluxdown_install as fluxdown_install
    from app.services.common.update import prefetch as prefetch
    from app.services.common.update import transport as transport
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.services.common.update 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name in ("fluxdown", "fluxdown_install", "prefetch", "transport"):
            return import_module(f"app.services.common.update.{name}")
        return getattr(import_module("app.services.common.update"), name)
