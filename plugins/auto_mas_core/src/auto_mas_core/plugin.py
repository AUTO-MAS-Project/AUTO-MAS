from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_mas_core import PluginContext


DEFAULT_INSTANCE = {
    "id": "auto_mas_core:system",
    "name": "AUTO-MAS Core",
    "enabled": True,
    "config": {},
    "system": True,
    "locked": True,
}


class Plugin:
    ctx: "PluginContext"

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx

    async def on_start(self) -> None:
        self.ctx.logger.debug("[{}] core system plugin loaded".format(self.ctx.plugin_name))

    async def on_stop(self, reason: str) -> None:
        self.ctx.logger.debug(
            "[{}] core system plugin stopped, reason={}".format(
                self.ctx.plugin_name,
                reason,
            )
        )
