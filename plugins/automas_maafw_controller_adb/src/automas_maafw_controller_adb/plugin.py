from __future__ import annotations

from typing import TYPE_CHECKING

from .service import MaaFWAdbControllerService

if TYPE_CHECKING:
    from auto_mas_core import PluginContext


DEFAULT_INSTANCE = {
    "name": "MaaFW ADB Controller",
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
    provides = ["maafw.controller.adb"]
    wants = ["maafw.registry.v1"]

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx
        self.service = MaaFWAdbControllerService()

    async def on_start(self) -> None:
        self.ctx.set("maafw.controller.adb", self.service)
        registry = self.ctx.get("maafw.registry.v1")
        if registry is not None and hasattr(registry, "register_controller_provider"):
            registry.register_controller_provider(self.service.get_provider_definition())
        self.ctx.logger.info("maafw.controller.adb ready")

    async def on_stop(self, reason: str) -> None:
        registry = self.ctx.get("maafw.registry.v1")
        if registry is not None and hasattr(registry, "unregister_controller_provider"):
            registry.unregister_controller_provider("adb")
        self.ctx.logger.info(f"maafw.controller.adb stopped, reason={reason}")
