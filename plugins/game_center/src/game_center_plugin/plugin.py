"""游戏中心系统插件

将游戏中心以插件形式接入主程序: 注册内置 provider、发布 "game_center"
服务、声明前端页面。核心域逻辑位于主程序 app/core/game_center。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .service import GameCenterService

if TYPE_CHECKING:
    from auto_mas_core import PluginContext


class Plugin:
    """游戏中心插件入口"""

    provides = ["game_center"]

    ctx: "PluginContext"

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx

    async def on_start(self) -> None:
        from app.core.game_center import game_center_manager

        game_center_manager.init()
        self.ctx.service.set(
            "game_center", GameCenterService(game_center_manager)
        )
        self.ctx.page.register(
            id="game-center",
            path="/game-center",
            title="游戏中心",
            menu_label="游戏中心",
            icon="game",
            component="GameCenter",
            section="main",
            order=75,
        )
        self.ctx.logger.info("[{}] 游戏中心插件已启动".format(self.ctx.plugin_name))

    async def on_stop(self, reason: str) -> None:
        from app.core.game_center import game_center_manager

        await game_center_manager.cleanup()
        self.ctx.logger.info(
            "[{}] 游戏中心插件已停止, reason={}".format(self.ctx.plugin_name, reason)
        )
