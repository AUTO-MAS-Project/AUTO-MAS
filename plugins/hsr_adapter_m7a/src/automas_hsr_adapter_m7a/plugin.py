from __future__ import annotations

from .catalog import M7ATaskCatalog
from .controller import M7AController


DEFAULT_INSTANCE = {
    "name": "HSR M7A 适配器",
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
    provides = ["hsr.task_catalog.m7a.v1", "hsr.controller.m7a.v1"]
    needs = ["hsr.registry.v1"]

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.catalog = M7ATaskCatalog()
        self.controller = M7AController()

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
            self.ctx.set("hsr.task_catalog.m7a.v1", self.catalog)
            self.ctx.set("hsr.controller.m7a.v1", self.controller)
        except Exception:
            if registered:
                registry.unregister_owner(self.ctx.instance_id)
            self.ctx.set("hsr.task_catalog.m7a.v1", None)
            self.ctx.set("hsr.controller.m7a.v1", None)
            raise
        self.ctx.logger.info("M7A HSR adapter ready")

    async def on_stop(self, reason: str) -> None:
        registry = self.ctx.get("hsr.registry.v1")
        if registry is not None:
            cleanup_errors = await registry.close_owner_sessions(self.ctx.instance_id)
            if cleanup_errors:
                self.ctx.logger.error(
                    f"M7A HSR 活动会话清理失败: {'；'.join(cleanup_errors)}"
                )
            registry.unregister_owner(self.ctx.instance_id)
        self.ctx.set("hsr.task_catalog.m7a.v1", None)
        self.ctx.set("hsr.controller.m7a.v1", None)
        self.ctx.logger.info(f"M7A HSR adapter stopped, reason={reason}")

    async def on_unload(self) -> None:
        await self.on_stop("unload")
