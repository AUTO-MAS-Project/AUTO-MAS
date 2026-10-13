"""Manager 插件实例挂载纪律：load 无实例；enable 构造；禁止 unload/reload 静默新建。"""

from __future__ import annotations

import asyncio
import types
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.core import plugin_manager as plugin_mod
# plugin_manager 在各函数内 ``from app.core.config import Config``，
# 模块上没有 Config 属性；打桩要打真对象的属性
from app.core.config import Config as _AppConfig
from app.plugin.base.plugin import BasePlugin
from app.plugin.types import LifecycleContext, PluginCodeDrift, PluginState


class _Track(BasePlugin):
    """记录钩子调用与实例身份。"""

    calls: list[tuple[str, int]] = []

    def __init__(self, config=None, record=None) -> None:
        super().__init__(config=config, record=record)
        self.token = id(self)

    async def pre_reload(self) -> None:
        _Track.calls.append(("pre_reload", self.token))

    async def on_reload(self) -> None:
        _Track.calls.append(("on_reload", self.token))

    async def on_enable(self) -> None:
        _Track.calls.append(("on_enable", self.token))

    async def on_disable(self) -> None:
        _Track.calls.append(("on_disable", self.token))

    async def pre_unload(self) -> None:
        _Track.calls.append(("pre_unload", self.token))

    async def on_unload(self) -> None:
        _Track.calls.append(("on_unload", self.token))


def _record(
    *,
    state: PluginState,
    plugin: BasePlugin | None,
    cls: type[BasePlugin] | None = _Track,
) -> Any:
    info = types.SimpleNamespace(
        plugin_name="demo",
        is_core=False,
        is_local=False,
        state=state,
        import_name="demo",
        lifecycle_context=LifecycleContext.IDLE,
        enabled=state == PluginState.ENABLED,
        last_error="",
        code_drift=PluginCodeDrift.NORMAL,
        wants=[],
        requires=[],
        config_uid="",
    )
    class _Record:
        pass

    record = _Record()
    record.uid = uuid4()
    record.info = info
    record._plugin = plugin
    record._plugin_cls = cls
    record._config = None
    record._degraded_wants = []
    record._project_dir = None
    record.commit = AsyncMock()
    return record


def _mgr() -> plugin_mod._PluginManager:
    m = plugin_mod._PluginManager()
    m._downstream = lambda _r: []  # type: ignore[method-assign]
    m._upstream = lambda _r: []  # type: ignore[method-assign]
    return m


@contextmanager
def _stub_loader() -> Iterator[None]:
    orig_refresh = plugin_mod.discover.refresh
    orig_clear = plugin_mod.loader.clear
    orig_load = plugin_mod.loader.load
    plugin_mod.discover.refresh = AsyncMock()  # type: ignore[method-assign]
    plugin_mod.loader.clear = lambda _r: None  # type: ignore[method-assign]
    plugin_mod.loader.load = lambda _r: _Track  # type: ignore[method-assign]
    try:
        yield
    finally:
        plugin_mod.discover.refresh = orig_refresh  # type: ignore[method-assign]
        plugin_mod.loader.clear = orig_clear  # type: ignore[method-assign]
        plugin_mod.loader.load = orig_load  # type: ignore[method-assign]


async def _test_load_does_not_create_instance() -> None:
    # load 只解析类，禁止构造实例 / on_load
    _Track.calls = []
    mgr = _mgr()
    record = _record(state=PluginState.UNLOADED, plugin=None, cls=None)
    with _stub_loader():
        await mgr.load(record, held=True)

    assert record._plugin is None
    assert record._plugin_cls is _Track
    assert record.info.state == PluginState.DISABLED
    assert _Track.calls == []


async def _test_enable_constructs_instance() -> None:
    _Track.calls = []
    mgr = _mgr()
    record = _record(state=PluginState.DISABLED, plugin=None)
    await mgr.enable(record, held=True)

    assert record._plugin is not None
    assert isinstance(record._plugin, _Track)
    assert record.info.state == PluginState.ENABLED
    assert _Track.calls == [("on_enable", record._plugin.token)]


async def _test_reload_skips_hooks_when_plugin_missing() -> None:
    _Track.calls = []
    mgr = _mgr()
    record = _record(state=PluginState.DISABLED, plugin=None)
    with _stub_loader():
        await mgr.reload(record, held=True)

    assert _Track.calls == []
    assert record._plugin is None
    assert record.info.state == PluginState.DISABLED
    assert record.info.lifecycle_context == LifecycleContext.IDLE


async def _test_reload_enabled_calls_disable_and_enable() -> None:
    # 启用中 reload：旧实例 pre/on_reload → on_disable；新实例 on_enable
    _Track.calls = []
    mgr = _mgr()
    hung = _Track()
    record = _record(state=PluginState.ENABLED, plugin=hung)
    with _stub_loader():
        await mgr.reload(record, held=True)

    names = [n for n, _ in _Track.calls]
    assert names.count("pre_reload") == 1
    assert names.count("on_reload") == 1
    assert names.count("on_disable") >= 1
    assert names.count("on_enable") >= 1
    assert ("pre_reload", hung.token) in _Track.calls
    assert ("on_reload", hung.token) in _Track.calls
    assert ("on_disable", hung.token) in _Track.calls
    assert record._plugin is not None
    assert record._plugin.token != hung.token
    assert record.info.state == PluginState.ENABLED


async def _test_unload_skips_hooks_when_plugin_missing() -> None:
    _Track.calls = []
    mgr = _mgr()
    record = _record(state=PluginState.DISABLED, plugin=None)
    registry = MagicMock()
    registry.commit = AsyncMock()
    orig = _AppConfig.plugin_registry
    _AppConfig.plugin_registry = registry
    try:
        with _stub_loader():
            await mgr.unload(record, held=True)
    finally:
        _AppConfig.plugin_registry = orig

    assert _Track.calls == []
    registry.remove.assert_called_once_with(record.uid)
    registry.commit.assert_awaited()


async def _test_unload_hooks_use_hung_instance() -> None:
    _Track.calls = []
    mgr = _mgr()
    hung = _Track()
    record = _record(state=PluginState.DISABLED, plugin=hung)
    registry = MagicMock()
    registry.commit = AsyncMock()
    orig = _AppConfig.plugin_registry
    _AppConfig.plugin_registry = registry
    try:
        with _stub_loader():
            await mgr.unload(record, held=True)
    finally:
        _AppConfig.plugin_registry = orig

    assert _Track.calls == [
        ("pre_unload", hung.token),
        ("on_unload", hung.token),
    ]
    assert record._plugin is None
    registry.remove.assert_called_once_with(record.uid)


async def main() -> None:
    await _test_load_does_not_create_instance()
    await _test_enable_constructs_instance()
    await _test_reload_skips_hooks_when_plugin_missing()
    await _test_reload_enabled_calls_disable_and_enable()
    await _test_unload_skips_hooks_when_plugin_missing()
    await _test_unload_hooks_use_hung_instance()


def test_instance_lifecycle_discipline() -> None:
    asyncio.run(main())
