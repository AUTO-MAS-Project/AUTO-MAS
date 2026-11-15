"""插件重载根据本次禁用返回的级联树恢复运行状态。"""

import pytest
import pytest_asyncio

from app.core.plugin.manager import _PluginManager
from app.models.config import GlobalConfig, PluginRecord, PluginRegistryCollection
from app.plugin.runtime import loader
from app.plugin.types import PluginState


@pytest_asyncio.fixture
async def cascade_plugins(isolated_app_paths, monkeypatch, tmp_path):
    """从临时插件包加载真实生命周期，隔离配置和插件背景任务的归属。"""
    registry = PluginRegistryCollection.build([PluginRecord])
    setting = GlobalConfig.build()
    await registry.activate()
    await setting.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    manager = _PluginManager()
    records = {}

    async def load(dependencies):
        """按给定服务依赖建立普通插件包，每个包记录自己的业务启停次数。"""
        for name, requires in dependencies.items():
            package = tmp_path / name
            package.mkdir()
            (package / "__init__.py").write_text(
                "from app.plugin.base import BasePlugin\n"
                "class Adapter(BasePlugin):\n"
                f"    requires = {tuple(requires)!r}\n"
                f"    provides_services = {{{name!r}: 'value'}}\n"
                "    events = []\n"
                "    fail_enable = False\n"
                "    async def value(self):\n"
                '        """返回当前实例，供调用者确认服务已经重新挂载。"""\n'
                "        return self\n"
                "    async def on_enable(self):\n"
                '        """记录启用并按插件故障开关注入业务失败。"""\n'
                "        self.events.append('enable')\n"
                "        if self.fail_enable: raise RuntimeError('plugin enable failed')\n"
                "    async def on_disable(self):\n"
                '        """记录资源禁用，供核对共享依赖不会重复启停。"""\n'
                "        self.events.append('disable')\n"
                "PLUGIN = Adapter\n",
                encoding="utf-8",
            )
            uid = registry.add(
                PluginRecord,
                payload={
                    "info": {
                        "plugin_name": name,
                        "import_name": name,
                        "source": "local",
                        "enabled": False,
                    }
                },
            )
            await registry.commit()
            record = registry[uid]
            record._project_dir = tmp_path
            records[name] = record
            await manager.load(record)
        return manager, records

    try:
        yield load
    finally:
        await manager.shutdown()
        for record in records.values():
            loader.clear(record)


@pytest.mark.asyncio
async def test_reload_restores_complete_tree_without_enabling_inactive_descendants(
    cascade_plugins,
):
    """A→B→C 重载恢复全部服务，原本禁用的 B 下游不会被混入恢复树。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_c": ("cascade_b",),
            "cascade_inactive": ("cascade_b",),
        }
    )
    await manager.enable(records["cascade_c"])
    previous = records["cascade_c"]._plugin
    result = await manager.reload(records["cascade_a"])
    expected = {"cascade_b": {"cascade_c": {}}}
    assert result["tear"] == expected
    assert result["restore"] == expected
    for name in ("cascade_a", "cascade_b", "cascade_c"):
        assert records[name].info.state == PluginState.ENABLED
        assert records[name].info.enabled
        assert await manager.services.require(name)() is records[name]._plugin
    assert records["cascade_c"]._plugin is not previous
    assert records["cascade_inactive"].info.state == PluginState.DISABLED
    assert not records["cascade_inactive"].info.enabled
    assert records["cascade_inactive"]._plugin_cls.events == []


@pytest.mark.asyncio
async def test_reload_shared_descendant_is_disabled_and_restored_once(cascade_plugins):
    """菱形依赖只记录实际拆卸路径，正常启用仍能先恢复尚未轮到的上游。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_d": ("cascade_a",),
            "cascade_c": ("cascade_b", "cascade_d"),
        }
    )
    await manager.enable(records["cascade_c"])
    result = await manager.reload(records["cascade_a"])
    expected = {"cascade_b": {"cascade_c": {}}, "cascade_d": {}}
    assert result["tear"] == expected
    assert result["restore"] == expected
    for name in ("cascade_b", "cascade_c", "cascade_d"):
        assert records[name].info.state == PluginState.ENABLED
        assert records[name]._plugin_cls.events == ["enable", "disable", "enable"]
        assert await manager.services.require(name)() is records[name]._plugin


@pytest.mark.asyncio
async def test_reload_restore_failure_skips_branch_and_continues_other_branches(
    cascade_plugins,
):
    """恢复失败保留故障记录，不通过其子节点重试失败分支，其他分支继续恢复。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_c": ("cascade_b",),
            "cascade_d": ("cascade_a",),
        }
    )
    await manager.enable(records["cascade_c"])
    await manager.enable(records["cascade_d"])
    records["cascade_b"]._plugin_cls.fail_enable = True
    result = await manager.reload(records["cascade_a"])
    assert result["tear"] == {"cascade_b": {"cascade_c": {}}, "cascade_d": {}}
    assert result["restore"] == {"cascade_d": {}}
    assert records["cascade_a"].info.state == PluginState.ENABLED
    assert records["cascade_b"].info.state == PluginState.FAULT_RUNTIME
    assert not records["cascade_b"].info.enabled
    assert records["cascade_b"].info.last_error
    assert records["cascade_b"]._plugin_cls.events.count("enable") == 2
    assert records["cascade_c"].info.state == PluginState.DISABLED
    assert not records["cascade_c"].info.enabled
    assert records["cascade_c"]._plugin_cls.events.count("enable") == 1
    assert records["cascade_d"].info.state == PluginState.ENABLED
    assert await manager.services.require("cascade_d")() is records["cascade_d"]._plugin
