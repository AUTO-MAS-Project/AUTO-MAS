"""真实宿主模块 app.core.notify.formats.maafw 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["build_statistics_payload"]

if TYPE_CHECKING:
    from app.core.notify.formats.maafw import (
        build_statistics_payload as build_statistics_payload,
    )
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.core.notify.formats.maafw 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.core.notify.formats.maafw"), name)
