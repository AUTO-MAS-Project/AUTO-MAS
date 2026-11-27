"""真实宿主模块 app.tools.common.game_calendar 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["stella"]

if TYPE_CHECKING:
    from app.tools.common.game_calendar import stella as stella
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.tools.common.game_calendar 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        if name in ("stella",):
            return import_module(f"app.tools.common.game_calendar.{name}")
        return getattr(import_module("app.tools.common.game_calendar"), name)
