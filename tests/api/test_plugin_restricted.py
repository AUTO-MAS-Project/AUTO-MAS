"""受控插件只在神秘入口当日解锁后进入市场、可安装并可启用。

守的是：
- 市场目录接口对受控插件按不存在处理，其他插件不受影响；
- 直接提交安装触发器同样被拒，前端隐藏不是唯一防线；
- 直接提交启用触发器同样被拒，且已安装已启用的存量不受解锁状态影响；
- 解锁与未解锁只在同一个状态源上取反，不依赖请求参数。

破坏方式：去掉 get_plugin_catalog 的过滤、把 on_install 的门禁挪到 Plugin.install 之后、
或把 manager.enable 里的门禁挪到 _is_enabled 早退之前，对应用例随即变红。
"""

import pytest
import pytest_asyncio

import app.api.plugin as plugin_api
import app.core.plugin.manager as plugin_manager
import app.mystery.gate as mystery_gate
from app.config import ConfigCollection
from app.core.plugin import Plugin as plugin_core
from app.models.config import (
    GlobalConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from app.plugin.base import BasePlugin
from app.plugin.errors import PluginPrecheckError
from app.plugin.types import RESTRICTED_PLUGIN_NAMES, LifecycleContext, PluginState


def _meta(package: str, identity: str) -> PluginMeta:
    """构造只带市场必需字段的目录条目。"""
    return PluginMeta.build(
        info={"package_name": package, "plugin_name": identity, "version": "0.1.0"}
    )


@pytest_asyncio.fixture
async def market(isolated_app_paths, monkeypatch):
    """激活真实目录集合，注册表只放核心插件。"""
    config = isolated_app_paths
    col = ConfigCollection[PluginMeta].build(
        [PluginMeta], file=config.config_path / "catalog.yaml"
    )
    registry = PluginRegistryCollection.build()
    await col.activate()
    await registry.activate()
    registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "auto_mas_core",
                "package_name": "auto-mas-core",
                "is_core": True,
            }
        },
    )
    await registry.commit()
    for package, identity in (
        ("auto-mas-demo-adapter", "demo_adapter"),
        ("auto-mas-token-adapter", "token_adapter"),
        ("signflow-token", "signflow_token"),
    ):
        col.add(
            PluginMeta, payload={"info": _meta(package, identity).info.model_dump()}
        )
    await col.commit()
    monkeypatch.setattr(config, "plugin_catalog", col)
    monkeypatch.setattr(config, "plugin_registry", registry)
    monkeypatch.setattr(config, "setting", GlobalConfig.build())
    return col


def _use_gate(monkeypatch, unlocked: bool) -> None:
    """市场过滤与安装门禁必须同时看到同一状态。"""

    def state() -> bool:
        return unlocked

    monkeypatch.setattr(plugin_api, "is_unlocked", state)
    monkeypatch.setattr(plugin_manager, "is_unlocked", state)
    monkeypatch.setattr(mystery_gate, "is_unlocked", state)


@pytest.mark.asyncio
async def test_restricted_plugin_hidden_until_unlocked(market, monkeypatch):
    """未解锁时只返回普通条目，解锁后受控条目重新出现。"""
    assert "token_adapter" in RESTRICTED_PLUGIN_NAMES

    _use_gate(monkeypatch, unlocked=False)
    locked = await plugin_api.get_plugin_catalog(plugin_api.PluginCatalogGetIn())
    names = {market[item.uid].effective.info.plugin_name for item in locked.order}
    assert names == {"demo_adapter"}

    _use_gate(monkeypatch, unlocked=True)
    opened = await plugin_api.get_plugin_catalog(plugin_api.PluginCatalogGetIn())
    names = {market[item.uid].effective.info.plugin_name for item in opened.order}
    assert names == {"demo_adapter", "token_adapter", "signflow_token"}


@pytest.mark.asyncio
async def test_restricted_plugin_install_rejected_until_unlocked(market, monkeypatch):
    """绕过市场直接提交安装触发器时，未解锁仍旧拒绝且不进入装包流程。"""
    restricted = next(
        item
        for item in market.values()
        if item.effective.info.plugin_name in RESTRICTED_PLUGIN_NAMES
    )

    _use_gate(monkeypatch, unlocked=False)
    with pytest.raises(PluginPrecheckError) as error:
        await restricted.on_install()
    assert "神秘入口" in str(error.value)


@pytest.mark.asyncio
async def test_signflow_token_is_restricted(market, monkeypatch):
    """SignFlow 的 Token 获取插件按发行名登记，未解锁时同样进不了市场。"""
    assert "signflow_token" in RESTRICTED_PLUGIN_NAMES

    _use_gate(monkeypatch, unlocked=False)
    locked = await plugin_api.get_plugin_catalog(plugin_api.PluginCatalogGetIn())
    names = {market[item.uid].effective.info.plugin_name for item in locked.order}
    assert "signflow_token" not in names

    restricted = next(
        item
        for item in market.values()
        if item.effective.info.plugin_name == "signflow_token"
    )
    with pytest.raises(PluginPrecheckError) as error:
        await restricted.on_install()
    assert "神秘入口" in str(error.value)


class _Plain(BasePlugin):
    """无配置、无服务的空插件，用于验证启用门禁本身。"""


async def _restricted_record(isolated_app_paths, monkeypatch, *, state: str):
    """在真实注册表集合里放一条受控插件记录并接上最小插件类。"""
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "signflow_token",
                "package_name": "signflow-token",
                "source": "installed",
                "state": state,
            }
        },
    )
    await registry.commit()
    record = registry[uid]
    record._plugin_cls = _Plain
    return record


@pytest.mark.asyncio
async def test_restricted_plugin_enable_rejected_until_unlocked(
    isolated_app_paths, monkeypatch
):
    """未解锁时绕过前端直接启用同样被拒，且不会落到 ENABLING 中间态。"""
    record = await _restricted_record(isolated_app_paths, monkeypatch, state="disabled")

    _use_gate(monkeypatch, unlocked=False)
    with pytest.raises(PluginPrecheckError) as error:
        await plugin_core.enable(record)
    assert "神秘入口" in str(error.value)
    assert record.info.state == PluginState.DISABLED
    assert record.info.enabled is False


@pytest.mark.asyncio
async def test_restricted_plugin_enable_allowed_once_unlocked(
    isolated_app_paths, monkeypatch
):
    """当日已解锁时受控插件与普通插件行为一致，可以正常启用。"""
    record = await _restricted_record(isolated_app_paths, monkeypatch, state="disabled")

    _use_gate(monkeypatch, unlocked=True)
    await plugin_core.enable(record)
    assert record.info.state == PluginState.ENABLED
    assert record.info.enabled is True


@pytest.mark.asyncio
async def test_enabled_restricted_plugin_survives_locking(
    isolated_app_paths, monkeypatch
):
    """已安装并启用的存量不受影响：锁回后再次启用直接早退，不报错也不停用。"""
    record = await _restricted_record(isolated_app_paths, monkeypatch, state="enabled")
    record.info.enabled = True
    await record.commit()

    _use_gate(monkeypatch, unlocked=False)
    assert await plugin_core.enable(record) == {}
    assert record.info.state == PluginState.ENABLED
    assert record.info.enabled is True


@pytest.mark.asyncio
async def test_restricted_plugin_enable_resumes_after_restart(
    isolated_app_paths, monkeypatch
):
    """上次启用过的受控插件在锁定后重启仍能恢复，不会因当日未解锁而掉线。"""
    record = await _restricted_record(isolated_app_paths, monkeypatch, state="disabled")
    record.info.enabled = True
    await record.commit()

    _use_gate(monkeypatch, unlocked=False)
    await plugin_core.enable(record)
    assert record.info.state == PluginState.ENABLED
    assert record.info.enabled is True


@pytest.mark.asyncio
async def test_restricted_plugin_cascade_restore_skips_the_gate(
    isolated_app_paths, monkeypatch
):
    """重载后恢复下游走级联语境，不被启用门禁拦下，避免连带插件掉线。"""
    record = await _restricted_record(isolated_app_paths, monkeypatch, state="disabled")

    _use_gate(monkeypatch, unlocked=False)
    await plugin_core.enable(record, ctx=LifecycleContext.RELOAD_CASCADE)
    assert record.info.state == PluginState.ENABLED
