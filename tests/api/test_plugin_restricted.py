"""受控插件只在神秘入口当日解锁后进入市场并可安装。

守的是：
- 市场目录接口对受控插件按不存在处理，其他插件不受影响；
- 直接提交安装触发器同样被拒，前端隐藏不是唯一防线；
- 解锁与未解锁只在同一个状态源上取反，不依赖请求参数。

破坏方式：去掉 get_plugin_catalog 的过滤、或把 on_install 的门禁挪到 Plugin.install 之后，
两条用例随即变红。
"""

import pytest
import pytest_asyncio

import app.api.plugin as plugin_api
import app.core.mystery as mystery_core
from app.config import ConfigCollection
from app.models.config import (
    GlobalConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from app.plugin.errors import PluginPrecheckError
from app.plugin.types import RESTRICTED_PLUGIN_NAMES


class _Gate:
    """把神秘入口状态固定为指定结果，避免测试依赖真实日期。"""

    def __init__(self, unlocked: bool) -> None:
        self.unlocked = unlocked

    def is_unlocked(self) -> bool:
        return self.unlocked


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
    gate = _Gate(unlocked)
    monkeypatch.setattr(plugin_api, "Mystery", gate)
    monkeypatch.setattr(mystery_core, "Mystery", gate)


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
    assert names == {"demo_adapter", "token_adapter"}


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
