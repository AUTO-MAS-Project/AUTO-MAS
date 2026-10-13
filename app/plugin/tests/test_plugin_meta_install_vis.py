"""PluginMeta.install：注册表已有对应条目时 UI 不可用。"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, cast

import pytest

import app.core.config as core_config
from app.config import ConfigCollection
from app.models.config import PluginMeta, PluginRecord


class Registry(ConfigCollection[PluginRecord]):
    _default_entry_types: ClassVar[tuple[type, ...]] = ()

    def by_name(self, name: str) -> PluginRecord | None:
        for record in self.values():
            if record.info.plugin_name == name:
                return record
        return None


def _hint_editable(hints: object, field: str) -> bool | None:
    block = cast(dict[str, Any], hints).get("info") or []
    for item in block:
        if isinstance(item, dict) and item.get("field") == field:
            return bool(item.get("editable"))
    return None


def test_install_disabled_when_registry_has_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        registry = Registry()
        await registry.activate()
        registry.add_type(PluginRecord)
        await registry.commit()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        meta = PluginMeta.build(
            info={
                "package_name": "automas-plugin-demo",
                "plugin_name": "demo",
                "version": "1.0.0",
            }
        )
        await meta.activate()
        assert _hint_editable(meta.ui.hints, "install") is True

        # 同插件名已在注册表 → install 不可用
        registry.add(
            PluginRecord,
            payload={
                "info": {
                    "package_name": "automas-plugin-demo",
                    "plugin_name": "demo",
                }
            },
        )
        await registry.commit()
        assert _hint_editable(meta.ui.hints, "install") is False

        # 仅包名匹配（插件名不同）也应不可用
        for uid in list(registry.keys()):
            registry.remove(uid)
        registry.add(
            PluginRecord,
            payload={
                "info": {
                    "package_name": "automas_plugin_demo",
                    "plugin_name": "other",
                }
            },
        )
        await registry.commit()
        assert _hint_editable(meta.ui.hints, "install") is False

    asyncio.run(run())
