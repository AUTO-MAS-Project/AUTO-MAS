"""真实宿主模块 app.utils.common.game_resolution 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["UnityGameResolutionOverride", "parse_resolution_option"]

if TYPE_CHECKING:
    from app.utils.common.game_resolution import (
        UnityGameResolutionOverride as UnityGameResolutionOverride,
    )
    from app.utils.common.game_resolution import (
        parse_resolution_option as parse_resolution_option,
    )
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.utils.common.game_resolution 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.utils.common.game_resolution"), name)
