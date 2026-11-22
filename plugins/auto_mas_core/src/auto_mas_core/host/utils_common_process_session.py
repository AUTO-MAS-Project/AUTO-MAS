"""真实宿主模块 app.utils.common.process.session 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["DesktopProcessTarget", "desktop_process_target"]

if TYPE_CHECKING:
    from app.utils.common.process.session import (
        DesktopProcessTarget as DesktopProcessTarget,
    )
    from app.utils.common.process.session import (
        desktop_process_target as desktop_process_target,
    )
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.process.session 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.utils.common.process.session"), name)
