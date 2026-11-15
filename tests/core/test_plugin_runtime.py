"""插件引导、配置所有权及公开调用收敛的隔离集成。"""

import asyncio

import pytest
from pydantic import Field

from app.config import ConfigCollection, ConfigGroup, config_manager
from app.core.plugin.manager import _PluginManager
from app.models.config import (
    PluginConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from app.plugin.base import BasePlugin
from app.plugin.base.game import GameAdapterPlugin
from app.plugin.base.script import ScriptAdapterPlugin
from app.plugin.calls import CallGate
from app.plugin.errors import PluginBusyError
from app.plugin.types import PluginState


def test_disable_confirmation_includes_only_enabled_cascading_adapters(monkeypatch):
    """停用服务提供者时也须警告下游适配配置删除，已停用下游不重复计入。"""

    class Provider(BasePlugin):
        provides_services = {"test.service": "service"}

    provider = PluginRecord.build(info={"plugin_name": "provider", "state": "enabled"})
    script = PluginRecord.build(
        info={"plugin_name": "script", "state": "enabled", "requires": ["test.service"]}
    )
    game = PluginRecord.build(
        info={"plugin_name": "game", "state": "disabled", "requires": ["test.service"]}
    )
    provider._plugin_cls = Provider
    script._plugin_cls = ScriptAdapterPlugin
    game._plugin_cls = GameAdapterPlugin
    manager = _PluginManager()
    monkeypatch.setattr(manager, "list_plugins", lambda: [provider, script, game])
    assert manager.disable_impact(provider) == ["scripts"]
    game.info.state = PluginState.ENABLED
    assert manager.disable_impact(provider) == ["games", "scripts"]


@pytest.mark.asyncio
async def test_bootstrap_core_with_separate_source_and_user_directories(
    isolated_app_paths, monkeypatch
):
    """验证源码与用户工作目录分离时仍能发现 core SDK，并将用户配置保存在工作目录。"""
    config = isolated_app_paths
    registry = PluginRegistryCollection.build(
        [PluginRecord], file=config.config_path / "plugins-test.yaml"
    )
    catalog = ConfigCollection[PluginMeta].build([PluginMeta])
    await registry.activate()
    await catalog.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    monkeypatch.setattr(config, "plugin_catalog", catalog)
    monkeypatch.syspath_prepend(
        str(config.source_path / "plugins" / "auto_mas_core" / "src")
    )
    # 本例验证 core 的独立源码发现；MAA 的完整启停由专项集成验证，避免重载其他用例持有的类。
    from app.plugin.runtime import discover

    parse_source = discover._parse_source_package

    async def core_source(path):
        return await parse_source(path) if path.name == "auto_mas_core" else None

    monkeypatch.setattr(discover, "_parse_source_package", core_source)
    manager = _PluginManager()
    try:
        await manager.initialize()
        core = registry.by_name("auto_mas_core")
        assert core is not None
        assert core.info.is_core
        assert core.info.enabled
        assert core.info.state == PluginState.ENABLED
        await manager.shutdown()
        assert core.info.enabled
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_constructor_failure_releases_unactivated_root(isolated_app_paths):
    """验证插件构造失败后释放未激活配置根，不遗留失效注册。"""

    class Settings(PluginConfig):
        class Data(ConfigGroup):
            value: str = "original"

        data: Data = Field(default_factory=Data)

    class Broken(BasePlugin):
        config_class = Settings

        def __init__(self, config=None, record=None):
            """模拟插件实例构造失败，驱动未激活配置根的回收路径。"""
            raise ValueError("constructor failed")

    record = PluginRecord.build(info={"plugin_name": "broken", "state": "disabled"})
    await record.activate()
    record._plugin_cls = Broken
    before = tuple(config_manager.iter_persist_roots())
    with pytest.raises(ValueError, match="constructor failed"):
        await _PluginManager().enable(record)
    assert tuple(config_manager.iter_persist_roots()) == before
    assert record._config is None


@pytest.mark.asyncio
async def test_retained_service_method_stops_admission_and_waits_inflight():
    """验证外部持有的服务方法在插件停止时拒绝新调用，同时等待已进入调用结束。"""
    gate = CallGate()
    started, release = asyncio.Event(), asyncio.Event()

    async def service():
        """提供可由测试事件延迟完成的真实异步调用，供验证生命周期等待。"""
        started.set()
        await release.wait()
        return 42

    retained = gate.wrap(service)
    active = asyncio.create_task(retained())
    await started.wait()
    gate.accepting = False
    with pytest.raises(PluginBusyError):
        await retained()
    drain = asyncio.create_task(gate.drain())
    await asyncio.sleep(0)
    assert not drain.done()
    release.set()
    assert await active == 42
    await drain


@pytest.mark.asyncio
async def test_config_save_failure_keeps_owned_root_registered(tmp_path, monkeypatch):
    """验证插件配置保存失败时保留配置根归属，避免卸载后丢失尚未保存的数据。"""

    class Settings(PluginConfig):
        class Data(ConfigGroup):
            value: str = "original"

        data: Data = Field(default_factory=Data)

    record = PluginRecord.build(info={"plugin_name": "example"})
    root = Settings.build(file=tmp_path / "example.yaml")
    await root.activate()
    record._config = root

    def fail(*args, **kwargs):
        """模拟磁盘空间不足导致配置写入失败。"""
        raise OSError("disk full")

    monkeypatch.setattr("app.utils.common.io.write_file", fail)
    with pytest.raises(OSError, match="disk full"):
        await _PluginManager()._release_config(record)
    assert record._config is root
    assert config_manager.get_file(root) == tmp_path / "example.yaml"


@pytest.mark.asyncio
async def test_i18n_sources_keep_disabled_resources_and_remove_full_namespace(tmp_path):
    """验证插件停用仍保留语言资源，完整移除时删除该插件命名空间的全部消息。"""
    import json

    from app.core.i18n import LOCALE_FILES, I18nManager

    core = tmp_path / "core"
    plugin = tmp_path / "plugin"
    core.mkdir()
    plugin.mkdir()
    for filename in LOCALE_FILES.values():
        (core / filename).write_text(
            json.dumps({"core.label": "Host"}), encoding="utf-8"
        )
    path = plugin / "en.json"
    path.write_text(json.dumps({"plugins.example.title": "Plugin"}), encoding="utf-8")
    manager = I18nManager(core)
    manager.set_plugin_sources({"example": plugin})
    first, revision = await manager.get_messages("en-US")
    assert first["plugins"]["example"]["title"] == "Plugin"
    # 禁用不移除可读来源；卸载或代码来源移除才改变 source 集合。
    assert (await manager.get_messages("en-US"))[1] == revision
    manager.set_plugin_sources({})
    removed, second_revision = await manager.get_messages("en-US")
    assert second_revision != revision
    assert "plugins" not in removed
    assert removed["core"]["label"] == "Host"


@pytest.mark.asyncio
async def test_game_reload_preserves_device_identity_and_rebinds_signals(monkeypatch):
    """验证游戏插件重载保留配置及设备身份，同时重新绑定生命周期信号。"""
    from types import SimpleNamespace

    from app.config import collection
    from app.core import Config
    from app.core.game_manager import GameManager
    from app.core.plugin.adapters import GameAdapterRuntime
    from app.models.config import GameDeviceEntry, GameEntry, ScriptEntry
    from app.models.config.game import device_removed
    from app.plugin.base.game import GameControl, GameTypeDecl
    from app.plugin.types import LifecycleContext

    class Device(GameDeviceEntry):
        pass

    class Game(GameEntry):
        devices: ConfigCollection[Device] = collection(Device)

    class Control(GameControl):
        async def refresh(self):
            """记录控制器已执行刷新，供验证重载后控制器接线。"""
            self.refreshed = True

        async def open(self, *args, **kwargs):
            """提供测试控制器的空启动实现，本用例只验证注册与重载。"""
            pass

        async def close(self, *args, **kwargs):
            """提供测试控制器的空关闭实现，避免引入真实设备操作。"""
            pass

        async def show(self, *args, **kwargs):
            """提供测试控制器的空显示实现，满足游戏控制协议。"""
            pass

        async def hide(self, *args, **kwargs):
            """提供测试控制器的空隐藏实现，满足游戏控制协议。"""
            pass

        async def minimize(self, *args, **kwargs):
            """提供测试控制器的空最小化实现，满足窗口控制协议。"""
            pass

        async def maximize(self, *args, **kwargs):
            """提供测试控制器的空最大化实现，满足窗口控制协议。"""
            pass

    games = ConfigCollection[GameEntry].build([Game])
    await games.activate()
    uid = games.add(Game, payload={"info": {"name": "retained"}})
    await games.commit()
    old = games[uid]
    device_uid = old.devices.add(Device)
    await old.devices.commit()
    old_control = GameManager.create_control(config=old, control_class=Control)
    old.bind_runtime_signals()
    new_device = type("Device", (GameDeviceEntry,), {})
    new_game = type(
        "Game",
        (GameEntry,),
        {
            "__annotations__": {"devices": ConfigCollection[new_device]},
            "devices": collection(new_device),
        },
    )
    record = PluginRecord.build(
        info={"plugin_name": "example", "lifecycle_context": LifecycleContext.RELOAD}
    )
    await record.activate()

    async def search():
        """返回空发现列表，使重载测试不访问真实设备。"""
        return []

    decl = GameTypeDecl(new_game, new_device, Control, search)
    plugin = SimpleNamespace(
        record=record,
        plugin_name="example",
        decl=decl,
        game_class=new_game,
        device_class=new_device,
        control_class=Control,
    )
    monkeypatch.setattr(Config, "GameConfig", games)
    received = []

    async def removed(sender, uid):
        """记录配置移除信号的设备标识，供检查重载后的信号绑定次数。"""
        received.append(uid)

    empty_scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
    await empty_scripts.activate()
    monkeypatch.setitem(config_manager._collections, "ScriptConfig", empty_scripts)
    device_removed.connect(removed)
    try:
        await GameAdapterRuntime(plugin).system_enable()
        current = games[uid]
        assert isinstance(current, new_game) and current is not old
        assert current.info.name == "retained"
        assert list(current.devices.keys()) == [device_uid]
        assert isinstance(current.devices[device_uid], new_device)
        assert current._game_control is not old_control
        assert current._game_control.refreshed
        current.devices.remove(device_uid)
        await current.devices.commit()
        assert received == [device_uid]
    finally:
        device_removed.disconnect(removed)
        from app.core.plugin import Plugin

        Plugin.game_types.pop(record.uid, None)


@pytest.mark.asyncio
async def test_disabled_instance_never_reopens_retained_service(monkeypatch):
    """验证已停用插件实例不会因恢复准入上下文而重新开放被外部持有的服务方法。"""
    from app.core import Config

    record = PluginRecord.build(
        info={"plugin_name": "example", "state": PluginState.ENABLED, "enabled": True}
    )
    await record.activate()
    record._plugin = BasePlugin(record=record)
    monkeypatch.setattr(Config, "plugin_registry", {record.uid: record})
    manager = _PluginManager()
    gate = CallGate()
    manager._calls[record.uid] = gate

    async def method():
        """提供可被保留的简单异步服务，供检查停用后的调用准入。"""
        return 1

    retained = gate.wrap(method)
    assert await retained() == 1
    async with manager._pause_owners([record.uid]):
        record._plugin = None
        record.info.state = PluginState.DISABLED
        await record.commit()
    with pytest.raises(PluginBusyError):
        await retained()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_state", ["missing", "broken", "loaded"])
async def test_uninstall_retains_failed_package_for_retry(
    isolated_app_paths, monkeypatch, source_state
):
    """已安装插件即使缺失或导入失败也能卸载，包删除失败时保留配置和登记供再次操作。"""
    from types import SimpleNamespace

    from app.core import plugin
    from app.plugin.errors import PluginError, PluginPrecheckError
    from app.plugin.types import PluginCodeDrift
    from app.plugin.uv import ops

    config = isolated_app_paths
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    manager = _PluginManager()
    monkeypatch.setattr(plugin, "Plugin", manager)
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "uninstall_example",
                "package_name": "uninstall-example",
                "import_name": "uninstall_example",
                "source": "installed",
                "state": "disabled",
            }
        },
    )
    await registry.commit()
    record = registry[uid]
    settings = config.config_path / "plugins" / "uninstall_example.yaml"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("saved: value\n", encoding="utf-8")
    if source_state == "missing":
        record.info.code_drift = PluginCodeDrift.PACKAGE_REMOVED
        await record.commit()
    else:
        source = config.plugins_path / "uninstall_example"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text(
            "\x00"
            if source_state == "broken"
            else ("from app.plugin.base import BasePlugin\nPLUGIN = BasePlugin\n"),
            encoding="utf-8",
        )
        record._project_dir = config.plugins_path
        if source_state == "broken":
            with pytest.raises(PluginPrecheckError):
                await manager.load(record)
        else:
            await manager.load(record)

    attempts = []

    async def execute(*args, **kwargs):
        """仅替换包管理进程边界，先模拟文件占用失败，再允许同一发行包卸载成功。"""
        attempts.append(args)
        return SimpleNamespace(
            returncode=1 if len(attempts) == 1 else 0,
            stderr="file in use" if len(attempts) == 1 else "",
            stdout="",
        )

    monkeypatch.setattr(ops, "ensure", lambda: "uv")
    monkeypatch.setattr(ops.ProcessRunner, "run_process", execute)
    with pytest.raises(PluginError, match="uv"):
        await record.on_uninstall()
    assert registry[uid] is record
    assert record.info.state == PluginState.FAULT_LOAD
    assert record.info.last_error
    assert settings.read_text(encoding="utf-8") == "saved: value\n"
    await record.on_uninstall()
    assert uid not in registry
    assert not settings.exists()
    assert len(attempts) == 2
    assert all("uninstall-example" in args for args in attempts)
