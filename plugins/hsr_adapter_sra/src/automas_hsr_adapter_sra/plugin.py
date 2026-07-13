from __future__ import annotations

from .catalog import SRATaskCatalog
from .controller import SRAController


DEFAULT_INSTANCE = {
    "name": "HSR SRA 适配器",
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
    provides = ["hsr.task_catalog.sra.v1", "hsr.controller.sra.v1"]
    needs = ["hsr.registry.v1"]

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.catalog = SRATaskCatalog()
        self.controller = SRAController()

    async def on_start(self) -> None:
        registry = self.ctx.get("hsr.registry.v1")
        if registry is None:
            raise RuntimeError("hsr.registry.v1 不可用")
        registered = False
        try:
            registry.register_group(
                owner=self.ctx.instance_id,
                task_catalog=self.catalog,
                controller=self.controller,
            )
            registered = True
            self.ctx.set("hsr.task_catalog.sra.v1", self.catalog)
            self.ctx.set("hsr.controller.sra.v1", self.controller)
        except Exception:
            if registered:
                registry.unregister_owner(self.ctx.instance_id)
            self.ctx.set("hsr.task_catalog.sra.v1", None)
            self.ctx.set("hsr.controller.sra.v1", None)
            raise
        self.ctx.logger.info("SRA HSR adapter ready")

    async def on_stop(self, reason: str) -> None:
        registry = self.ctx.get("hsr.registry.v1")
        if registry is not None:
            cleanup_errors = await registry.close_owner_sessions(self.ctx.instance_id)
            if cleanup_errors:
                self.ctx.logger.error(
                    f"SRA HSR 活动会话清理失败: {'；'.join(cleanup_errors)}"
                )
            registry.unregister_owner(self.ctx.instance_id)
        self.ctx.set("hsr.task_catalog.sra.v1", None)
        self.ctx.set("hsr.controller.sra.v1", None)
        self.ctx.logger.info(f"SRA HSR adapter stopped, reason={reason}")

    async def on_unload(self) -> None:
        await self.on_stop("unload")
