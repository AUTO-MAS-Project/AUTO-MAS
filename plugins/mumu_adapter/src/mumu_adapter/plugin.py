"""MuMu 模拟器适配。"""

from __future__ import annotations

from auto_mas_core import Config, GameAdapterPlugin, GameTypeDecl
from auto_mas_core.utils import get_logger

from .config import MuMuDevice, MuMuGame
from .control import MuMuControl
from .search import search

logger = get_logger("MuMu模拟器")


class Plugin(GameAdapterPlugin):
    """登记 MuMu 游戏配置类。展示名在包内 i18n。"""

    game_type_key = "mumu"
    decl = GameTypeDecl(
        game_class=MuMuGame,
        device_class=MuMuDevice,
        control_class=MuMuControl,
        search=search,
    )

    async def on_enable(self) -> None:
        """补做上次进程没走完的配置还原。

        退订实例时会整份写回并清空备份；进程被强杀则备份留在盘上，
        只有这里补一刀，落盘的备份才不是白存。
        """
        for entry in Config.GameConfig.values():
            if not isinstance(entry, MuMuGame):
                continue
            try:
                await entry._control.sweep_backups()
            except Exception as e:
                logger.warning(f"清扫 {entry.info.name} 残留配置备份失败: {e}")
