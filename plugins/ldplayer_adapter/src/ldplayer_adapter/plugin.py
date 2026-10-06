"""雷电模拟器适配。"""

from __future__ import annotations

from auto_mas_core import GameAdapterPlugin, GameTypeDecl

from .handle import LDPlayerControl, search_installed
from .schema import LDPlayerDevice, LDPlayerGame


class Plugin(GameAdapterPlugin):
    """登记雷电游戏配置类。展示名在包内 i18n。"""

    game_type_key = "ldplayer"
    decl = GameTypeDecl(
        game_class=LDPlayerGame,
        device_class=LDPlayerDevice,
        control_class=LDPlayerControl,
        search=search_installed,
    )
