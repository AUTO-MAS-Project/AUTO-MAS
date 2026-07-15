from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .contracts import HSRController, HSRTaskCatalogProvider


class HSRAdapterPlugin:
    """Shared atomic lifecycle for one HSR task-catalog/controller pair."""

    needs = ["hsr.registry.v1"]
    task_catalog_factory: Callable[[], HSRTaskCatalogProvider]
    controller_factory: Callable[[], HSRController]
    task_catalog_service: str
    controller_service: str
    display_name: str

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.catalog = self.task_catalog_factory()
        self.controller = self.controller_factory()

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
            self.ctx.set(self.task_catalog_service, self.catalog)
            self.ctx.set(self.controller_service, self.controller)
        except Exception:
            if registered:
                registry.unregister_owner(self.ctx.instance_id)
            self._clear_services()
            raise
        self.ctx.logger.info(f"{self.display_name} ready")

    async def on_stop(self, reason: str) -> None:
        await self._stop(reason=reason, final=False)

    async def on_unload(self) -> None:
        await self._stop(reason="unload", final=True)

    async def _stop(self, *, reason: str, final: bool) -> None:
        registry = self.ctx.get("hsr.registry.v1")
        if registry is not None:
            cleanup_errors = await registry.close_owner_sessions(self.ctx.instance_id)
            if cleanup_errors:
                self.ctx.logger.error(
                    f"{self.display_name} 活动会话清理失败: {'；'.join(cleanup_errors)}"
                )
                if not final:
                    return
            registry.unregister_owner(self.ctx.instance_id)

        self._clear_services()
        self.ctx.logger.info(f"{self.display_name} stopped, reason={reason}")

    def _clear_services(self) -> None:
        self.ctx.set(self.task_catalog_service, None)
        self.ctx.set(self.controller_service, None)
