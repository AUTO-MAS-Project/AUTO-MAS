from __future__ import annotations

import inspect
import uuid
from typing import Any

from app.core import Config
from app.core.script_types import script_type_registry
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import (
    PluginHttpRequest,
    PluginHttpResponse,
    ScriptAdapterDefinition,
    ScriptAdapterPlugin,
)
from app.plugins.realtime import schedule_plugin_snapshot
from app.plugins.script_config_store import ScriptConfigStore

from .adapter import HSRAdapterHooks
from .registry import HSRRegistryService
from .schema import HSRConfig, HSRUserConfig


DEFAULT_INSTANCE = {
    "name": "HSR 统一脚本入口",
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

class Plugin(ScriptAdapterPlugin):
    """注册 HSR 脚本类型、聚合服务和插件 HTTP 接口。"""

    provides = ["hsr.registry.v1"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.registry = HSRRegistryService(on_change=self._on_registry_change)
        self.provider: Any = None

    def build_script_adapters(self) -> list[ScriptAdapterDefinition]:
        return [
            ScriptAdapterDefinition(
                type_key="HSR",
                display_name="HSR脚本",
                hooks_factory=HSRAdapterHooks,
                script_model=HSRConfig,
                user_model=HSRUserConfig,
                script_class_name="HSRPluginConfig",
                user_class_name="HSRPluginUserConfig",
                module="automas_script_hsr.schema",
                supported_modes=("AutoProxy", "ManualReview"),
                icon="HSR",
                editor_kind="plugin:automas_script_hsr",
                is_builtin=False,
                record_capability_resolver=self.registry.resolve_record_capability,
                metadata={
                    "available": False,
                    "unavailable_reason": "请启用 SRA 或 M7A HSR 适配器",
                    "framework": "hsr",
                    "source": "automas_script_hsr",
                    "theme_color": "purple",
                },
            )
        ]

    async def on_start(self) -> None:
        definition = self.build_script_adapters()[0]
        provider = definition.build_provider(
            owner=self.ctx.instance_id,
            plugin_context=self.ctx,
        )
        from .runtime.manager import HSRManager

        provider.manager_factory = lambda script_item: HSRManager(
            script_item,
            provider=provider,
            registry=self.registry,
        )
        if provider.bind_related_config is not None:
            provider.bind_related_config(Config)
        script_type_registry.register(provider, owner=self.ctx.instance_id)
        self.provider = provider
        self.registry.set_provider(provider)
        self.ctx.set("hsr.registry.v1", self.registry)

        self.ctx.server.http(
            "/hsr/v1/capabilities",
            self._capabilities,
            methods=("GET",),
        )
        self.ctx.server.http(
            "/hsr/v1/stage-options",
            self._stage_options,
            methods=("GET",),
        )
        self.ctx.logger.info("hsr.registry.v1 ready")

    async def on_stop(self, reason: str) -> None:
        cleanup_errors = await self.registry.close_all_sessions()
        if cleanup_errors:
            self.ctx.logger.error(
                f"HSR 活动会话清理失败: {'；'.join(cleanup_errors)}"
            )
        self.ctx.set("hsr.registry.v1", None)
        removed = script_type_registry.unregister_by_owner(self.ctx.instance_id)
        self.provider = None
        self.ctx.logger.info(f"HSR 统一脚本入口已停止: {removed}, reason={reason}")

    async def on_unload(self) -> None:
        cleanup_errors = await self.registry.close_all_sessions()
        if cleanup_errors:
            self.ctx.logger.error(
                f"HSR 活动会话清理失败: {'；'.join(cleanup_errors)}"
            )
        self.ctx.set("hsr.registry.v1", None)
        removed = script_type_registry.unregister_by_owner(self.ctx.instance_id)
        self.provider = None
        self.ctx.logger.info(f"HSR 统一脚本入口已卸载: {removed}")

    async def _capabilities(self, request: PluginHttpRequest) -> PluginHttpResponse:
        script_id = str(request.query.get("scriptId") or "").strip()
        if not script_id:
            return self._success(self.registry.snapshot().asdict())

        try:
            store, script_model = await self._load_script(script_id)
            _ = store
            snapshot = self.registry.snapshot(
                script_config=script_model,
            )
            return self._success(snapshot.asdict())
        except (KeyError, ValueError, LookupError) as exc:
            return self._error(422, str(exc))

    async def _stage_options(self, request: PluginHttpRequest) -> PluginHttpResponse:
        script_id = str(request.query.get("scriptId") or "").strip()
        user_id = str(request.query.get("userId") or "").strip()
        engine = str(request.query.get("engine") or "").strip().upper()
        slot = str(request.query.get("slot") or "main").strip()
        if not script_id or not engine:
            return self._error(400, "缺少 scriptId 或 engine")

        try:
            store, script_model = await self._load_script(script_id)
            snapshot = self.registry.snapshot(script_config=script_model)
            if engine not in snapshot.effective_engines:
                return self._error(409, f"{engine} 未在当前 HSR 脚本中生效")
            user_model = await store.load_user_model(user_id) if user_id else None
            result = self.registry.get_group(engine).task_catalog.list_stage_options(
                script_config=script_model,
                user_config=user_model,
                slot=slot,
            )
            if inspect.isawaitable(result):
                result = await result
            return self._success(
                {
                    "engine": engine,
                    "categories": [category.asdict() for category in result],
                }
            )
        except (KeyError, ValueError, LookupError) as exc:
            return self._error(422, str(exc))

    async def _load_script(self, script_id: str) -> tuple[ScriptConfigStore, Any]:
        script_uid = uuid.UUID(script_id)
        storage = Config.ScriptConfig[script_uid]
        if not isinstance(storage, PluginScriptConfig):
            raise ValueError("脚本不是 HSR 插件配置")
        if str(storage.get("Meta", "PluginTypeKey") or "").strip() != "HSR":
            raise ValueError("脚本不是 HSR 插件配置")
        if self.provider is None:
            raise LookupError("HSR provider 当前未注册")
        store = ScriptConfigStore(
            provider=self.provider,
            storage_script_config=storage,
        )
        return store, await store.load_script_model()

    def _on_registry_change(self) -> None:
        schedule_plugin_snapshot(reason="hsr.registry.changed")

    @staticmethod
    def _success(data: Any) -> PluginHttpResponse:
        return PluginHttpResponse(
            status_code=200,
            body={
                "code": 200,
                "status": "success",
                "message": "success",
                "data": data,
            },
        )

    @staticmethod
    def _error(status_code: int, message: str) -> PluginHttpResponse:
        return PluginHttpResponse(
            status_code=status_code,
            body={
                "code": status_code,
                "status": "error",
                "message": message,
                "data": None,
            },
        )
