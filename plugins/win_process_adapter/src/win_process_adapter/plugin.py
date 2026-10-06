"""通用进程适配。"""

from __future__ import annotations

from auto_mas_core import GameAdapterPlugin, GameTypeDecl

from .handle import WinProcessControl, search_installed
from .schema import WinProcessDevice, WinProcessGame


class Plugin(GameAdapterPlugin):
    """登记通用进程游戏配置类。展示名在包内 i18n。"""

    game_type_key = "general"
    decl = GameTypeDecl(
        game_class=WinProcessGame,
        device_class=WinProcessDevice,
        control_class=WinProcessControl,
        search=search_installed,
    )
