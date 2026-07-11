from __future__ import annotations

from typing import TYPE_CHECKING

from app.plugins import ScriptAdapterDefinition, ScriptAdapterPlugin
from automas_script_maafw.adapter import MaaFWAdapterHooks

from .migration import migrate_legacy_m9a_config
from .schema import M9A_SCRIPT_GROUPS, M9A_USER_GROUPS
from .service import M9APackService

if TYPE_CHECKING:
    from auto_mas_core import PluginContext


DEFAULT_INSTANCE = {
    "name": "M9A MaaFW Pack",
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

SCRIPT_TYPE_BINDINGS = [
    {
        "type_key": "M9A",
        "display_name": "M9A",
        "script_config_class_name": "M9AConfig",
    }
]


class Plugin(ScriptAdapterPlugin):
    provides = ["maafw.pack.m9a.v1"]
    wants = [
        "maafw.registry.v1",
        "maafw.interface.v1",
        "maafw.project_update.v1",
        "maafw.runner.v1",
    ]

    def __init__(self, ctx: "PluginContext") -> None:
        super().__init__(ctx)
        self.ctx = ctx
        self.service = M9APackService()

    def build_script_adapters(self):
        return [
            ScriptAdapterDefinition(
                type_key="M9A",
                display_name="M9A",
                hooks_factory=MaaFWAdapterHooks,
                script_groups=M9A_SCRIPT_GROUPS,
                user_groups=M9A_USER_GROUPS,
                script_class_name="M9APluginConfig",
                user_class_name="M9APluginUserConfig",
                module="automas_script_maafw.schema",
                related_bindings={"EmulatorConfig": "EmulatorConfig"},
                supported_modes=("AutoProxy",),
                icon="M9A",
                icon_path="automas_script_maafw_pack_m9a:assets/m9a.png",
                editor_kind="plugin:automas_script_maafw_pack_m9a",
                legacy_config_class_name="M9AConfig",
                legacy_user_config_class_name="M9AUserConfig",
                is_builtin=False,
                metadata={
                    "framework": "maafw",
                    "source": "automas_script_maafw_pack_m9a",
                    "project_pack": "m9a",
                    "m9a_standalone": True,
                    "theme_color": "cyan",
                    "legacy_config_migrator": migrate_legacy_m9a_config,
                    "script_edit_hint": {
                        "text": "遇到配置问题时，可以查看",
                        "link_text": "M9A 配置指南",
                        "url": "https://doc.auto-mas.top/docs/script-guide/m9a.html",
                        "suffix": "，其中整理了项目目录、运行环境和任务配置步骤。",
                    },
                },
            )
        ]

    async def on_start(self) -> None:
        self.ctx.set("maafw.pack.m9a.v1", self.service)
        registry = self.ctx.get("maafw.registry.v1")
        if registry is not None and hasattr(registry, "register_project_pack"):
            registry.register_project_pack(self.service.get_definition())
        await super().on_start()
        self.ctx.logger.info("maafw.pack.m9a.v1 ready")

    async def on_stop(self, reason: str) -> None:
        registry = self.ctx.get("maafw.registry.v1")
        if registry is not None and hasattr(registry, "unregister_project_pack"):
            registry.unregister_project_pack("m9a")
        self.ctx.set("maafw.pack.m9a.v1", None)
        await super().on_stop(reason)
        self.ctx.logger.info(f"maafw.pack.m9a.v1 stopped, reason={reason}")
