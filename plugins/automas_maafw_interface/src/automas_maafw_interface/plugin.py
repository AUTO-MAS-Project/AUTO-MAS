from __future__ import annotations

from typing import TYPE_CHECKING

from .service import MaaFWInterfaceService

if TYPE_CHECKING:
    from auto_mas_core import PluginContext


DEFAULT_INSTANCE = {
    "name": "MaaFW Interface",
    "enabled": True,
    "config": {},
}

schema = {
    "__no_plugin_config__": {
        "type": "boolean",
        "default": True,
        "hidden": True,
        "configurable": False,
        "title": "No plugin-level configuration",
    },
}


class Plugin:
    provides = ["maafw.interface.v1"]

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx
        self.service = MaaFWInterfaceService()

    async def on_start(self) -> None:
        self.ctx.set("maafw.interface.v1", self.service)
        self.ctx.logger.info("maafw.interface.v1 ready")

    async def on_stop(self, reason: str) -> None:
        self.ctx.logger.info(f"maafw.interface.v1 stopped, reason={reason}")
