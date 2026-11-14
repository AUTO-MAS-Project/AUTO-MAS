"""真实宿主模块 app.tools.common.community.providers 的 SDK 导出。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.common.community.providers import *  # noqa: F403 - SDK 静态导出与真实宿主定义保持一致。
    from app.tools.common.community.providers import cloud_genshin as cloud_genshin
    from app.tools.common.community.providers import kuro as kuro
    from app.tools.common.community.providers import miyoushe as miyoushe
    from app.tools.common.community.providers import miyoushe_qr as miyoushe_qr
    from app.tools.common.community.providers import skland as skland
    from app.tools.common.community.providers import taygedo as taygedo
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.tools.common.community.providers 取得同名能力，使插件通过 SDK 入口复用宿主实现。"""
        if name in (
            "cloud_genshin",
            "kuro",
            "miyoushe",
            "miyoushe_qr",
            "skland",
            "taygedo",
        ):
            return import_module(f"app.tools.common.community.providers.{name}")
        return getattr(import_module("app.tools.common.community.providers"), name)
