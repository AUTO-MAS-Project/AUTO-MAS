from __future__ import annotations

from app.plugins import ScriptAdapterDefinition, ScriptAdapterPlugin

from .adapter import OkwwAdapterHooks
from .schema import OkwwConfig, OkwwUserConfig


DEFAULT_INSTANCE = {
    "name": "OK-WW 专项适配",
    "enabled": True,
    "config": {},
}

SCRIPT_ADAPTER_TYPE_KEYS = ("Okww",)


class Plugin(ScriptAdapterPlugin):
    """OK-WW script adapter plugin."""

    def build_script_adapters(self) -> list[ScriptAdapterDefinition]:
        return [
            ScriptAdapterDefinition(
                type_key="Okww",
                display_name="ok-ww脚本",
                script_model=OkwwConfig,
                user_model=OkwwUserConfig,
                hooks_factory=OkwwAdapterHooks,
                supported_modes=("AutoProxy", "ScriptConfig"),
                icon="Okww",
                editor_kind="plugin:okww_adapter",
                metadata={
                    "framework": "ok-script",
                    "source": "okww_adapter",
                },
            )
        ]
