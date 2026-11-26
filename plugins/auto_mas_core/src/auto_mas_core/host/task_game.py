"""真实宿主模块 app.task.game 的 SDK 导出：只开放 ``__all__`` 列出的名字。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "current_game_session",
    "game_device_id",
    "game_is_emulator",
    "game_target_id",
]

if TYPE_CHECKING:
    from app.task.game import current_game_session as current_game_session
    from app.task.game import game_device_id as game_device_id
    from app.task.game import game_is_emulator as game_is_emulator
    from app.task.game import game_target_id as game_target_id
else:

    def __getattr__(name: str) -> Any:
        """按需从宿主 app.task.game 取得已开放的同名能力；其余名字不对插件承诺。"""
        if name not in __all__:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return getattr(import_module("app.task.game"), name)
