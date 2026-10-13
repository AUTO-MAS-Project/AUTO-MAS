"""PluginRecord 四 Trigger 的 UI 可用性（按 state / 核心 / 本地）。"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from app.models.config import PluginRecord
from app.plugin.types import PluginState


def _hint_editable(hints: object, field: str) -> bool | None:
    block = cast(dict[str, Any], hints).get("info") or []
    for item in block:
        if isinstance(item, dict) and item.get("field") == field:
            return bool(item.get("editable"))
    return None


async def _check() -> None:
    rec = PluginRecord.build(
        info={
            "plugin_name": "demo",
            "state": PluginState.DISABLED,
            "is_core": False,
            "is_local": False,
        }
    )
    await rec.activate()

    # 禁用态：可 enable/reload/uninstall，不可 disable
    h = rec.ui.hints
    assert _hint_editable(h, "enable") is True
    assert _hint_editable(h, "disable") is False
    assert _hint_editable(h, "reload") is True
    assert _hint_editable(h, "uninstall") is True

    # disable 为 DISABLE：赋值 True 不得开闸
    dispatched: list[str] = []
    orig = PluginRecord.on_disable

    async def _spy_disable(self: PluginRecord) -> None:
        dispatched.append("disable")

    PluginRecord.on_disable = _spy_disable  # type: ignore[method-assign]
    try:
        rec.info.disable = True
    finally:
        PluginRecord.on_disable = orig  # type: ignore[method-assign]
    assert dispatched == []

    rec.info.state = PluginState.ENABLED
    await rec.commit()
    h2 = rec.ui.hints
    assert _hint_editable(h2, "enable") is False
    assert _hint_editable(h2, "disable") is True

    # enable 为 DISABLE：赋值不得开闸
    dispatched.clear()
    orig_en = PluginRecord.on_enable

    async def _spy_enable(self: PluginRecord) -> None:
        dispatched.append("enable")

    PluginRecord.on_enable = _spy_enable  # type: ignore[method-assign]
    try:
        rec.info.enable = True
    finally:
        PluginRecord.on_enable = orig_en  # type: ignore[method-assign]
    assert dispatched == []

    rec.info.is_core = True
    await rec.commit()
    h3 = rec.ui.hints
    assert _hint_editable(h3, "disable") is False
    assert _hint_editable(h3, "reload") is False
    assert _hint_editable(h3, "uninstall") is False

    rec.info.is_core = False
    rec.info.is_local = True
    rec.info.state = PluginState.DISABLED
    await rec.commit()
    h4 = rec.ui.hints
    assert _hint_editable(h4, "uninstall") is False

    rec.info.is_local = False
    rec.info.state = PluginState.FAULT_LOAD
    await rec.commit()
    h5 = rec.ui.hints
    assert _hint_editable(h5, "enable") is False
    assert _hint_editable(h5, "reload") is False
    assert _hint_editable(h5, "uninstall") is True

    rec.info.state = PluginState.ENABLING
    await rec.commit()
    h6 = rec.ui.hints
    assert _hint_editable(h6, "enable") is False
    assert _hint_editable(h6, "disable") is False
    assert _hint_editable(h6, "reload") is False
    assert _hint_editable(h6, "uninstall") is False


def test_plugin_record_trigger_ui_visibility() -> None:
    asyncio.run(_check())
