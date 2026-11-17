"""发现冲突在修改注册表和运行实现之前拒绝，源码覆盖遵守唯一来源规则。"""

import importlib.metadata
import shutil
import sys
from email.message import Message
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import tomli_w

from app.config import config_manager
from app.models.config import PluginMeta, PluginRecord, PluginRegistryCollection
from app.plugin.base import BasePlugin
from app.plugin.errors import PluginPrecheckError
from app.plugin.runtime import discover, loader
from app.plugin.types import PluginCodeDrift, PluginState, SourceChange


def write_plugin(
    path,
    *,
    package="discovery-probe",
    identity="discovery_probe",
    module="discovery_probe",
    version="1.0",
    installed=False,
):
    """落地真实工程或发行元数据，入口代码在发现期间绝不允许执行。"""
    root = path if installed else path / "src"
    directory = root / module
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text(
        'raise RuntimeError("discovery imported plugin code")\n', encoding="utf-8"
    )
    keywords = ["auto-mas-plugin", f"auto-mas-id:{identity}"]
    if installed:
        info = path / f"{package.replace('-', '_')}-{version}.dist-info"
        info.mkdir(exist_ok=True)
        metadata = Message()
        metadata["Name"] = package
        metadata["Version"] = version
        metadata["Keywords"] = ", ".join(keywords)
        metadata["Requires-Dist"] = "auto-mas-core>=5,<6"
        (info / "METADATA").write_text(str(metadata), encoding="utf-8")
        (info / "RECORD").write_text(f"{module}/__init__.py,,\n", encoding="utf-8")
    else:
        (path / "pyproject.toml").write_text(
            tomli_w.dumps(
                {
                    "project": {
                        "name": package,
                        "version": version,
                        "keywords": keywords,
                        "dependencies": ["auto-mas-core>=5,<6"],
                    }
                }
            ),
            encoding="utf-8",
        )
    return path


@pytest_asyncio.fixture
async def discovery(isolated_app_paths, monkeypatch, tmp_path):
    """隔离工程、发行包及持久化根，发现和配置提交仍使用真实实现。"""
    config = isolated_app_paths
    source = tmp_path / "source"
    (source / "plugins").mkdir(parents=True)
    config.plugins_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "source_path", source)
    registry = PluginRegistryCollection.build(
        [PluginRecord], file=config.config_path / "discovery-registry.yaml"
    )
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    site = tmp_path / "site"
    site.mkdir()
    distributions = importlib.metadata.distributions
    monkeypatch.setattr(
        importlib.metadata,
        "distributions",
        lambda **kwargs: distributions(path=[str(site)]),
    )
    from app.core.i18n import I18n

    previous = dict(I18n._plugin_sources)
    yield SimpleNamespace(
        config=config, source=source / "plugins", site=site, registry=registry
    )
    I18n.set_plugin_sources(previous)


@pytest.mark.asyncio
async def test_user_plugin_survives_source_tree_replacement(discovery):
    """后端源码目录替换后，根目录的独立插件仓库及其发现身份必须仍然可用。"""
    state = discovery
    project = state.config.plugins_path / "root_plugin"
    write_plugin(project)
    entry = project / "src/discovery_probe/__init__.py"
    entry.write_text(
        "from app.plugin.base import BasePlugin\n"
        "class Plugin(BasePlugin):\n"
        "    def value(self): return 42\n"
        "PLUGIN = Plugin\n",
        encoding="utf-8",
    )
    (project / ".git").mkdir()
    marker = project / ".git/config"
    marker.write_text("independent plugin repository", encoding="utf-8")
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    uid = record.uid
    assert loader.load(record)().value() == 42
    loader.clear(record)
    old_source = state.config.source_path
    retired = old_source.with_name("retired-source")
    old_source.rename(retired)
    (old_source / "plugins").mkdir(parents=True)
    shutil.rmtree(retired)
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    assert record.uid == uid and record.info.source == "local"
    assert record._project_dir == project / "src"
    assert marker.read_text(encoding="utf-8") == "independent plugin repository"
    assert loader.load(record)().value() == 42
    loader.clear(record)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "collision", ["local", "identity", "import", "installed", "package"]
)
async def test_conflict_preserves_registry_config_and_loaded_implementation(
    discovery, collision
):
    """重复候选不能覆盖已生效项，也不能提前写入同次扫描中的其他有效插件。"""
    state = discovery
    local = state.source / "original"
    if collision in ("identity", "installed", "package"):
        write_plugin(state.site, installed=True)
    else:
        write_plugin(local)
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    record.info.enabled = True
    record.info.state = PluginState.ENABLED
    await record.commit()
    record._plugin_cls = BasePlugin
    record._plugin = BasePlugin(record=record)
    implementation = record._plugin
    before = record.info.model_dump()
    before_path = record._project_dir
    await config_manager.flush()
    registry_file = state.config.config_path / "discovery-registry.yaml"
    original_registry = registry_file.read_bytes()
    saved = state.config.config_path / "discovery-owned.yaml"
    saved.write_bytes(b"value: preserved\n")
    write_plugin(
        state.source / "extra",
        package="unrelated-probe",
        identity="unrelated_probe",
        module="unrelated_probe",
    )
    if collision == "local":
        write_plugin(state.config.plugins_path / "duplicate")
    elif collision == "identity":
        write_plugin(local, package="different-distribution")
    elif collision == "import":
        write_plugin(
            state.config.plugins_path / "duplicate",
            package="different-distribution",
            identity="different_identity",
        )
    elif collision == "installed":
        write_plugin(state.site, version="2.0", installed=True)
    else:
        write_plugin(local, identity="different_identity", module="different_module")
    with pytest.raises(PluginPrecheckError):
        await discover.refresh()
    await config_manager.flush()
    assert list(state.registry.values()) == [record]
    assert record.info.model_dump() == before
    assert record._project_dir == before_path
    assert record._plugin_cls is BasePlugin and record._plugin is implementation
    assert registry_file.read_bytes() == original_registry
    assert saved.read_bytes() == b"value: preserved\n"
    assert "discovery_probe" not in sys.modules


@pytest.mark.asyncio
async def test_incremental_refresh_rejects_conflict_with_unchanged_plugin(discovery):
    """监视刷新同样检查未变更的插件，不能只在变化目录内确认导入名唯一。"""
    state = discovery
    write_plugin(state.source / "original")
    await discover.refresh()
    before = await state.registry.to_dict()
    changed = write_plugin(
        state.config.plugins_path / "new", package="new-probe", identity="new_probe"
    )
    with pytest.raises(PluginPrecheckError):
        await discover.refresh(
            scope=discover.RefreshScope(changes=(SourceChange(str(changed)),))
        )
    assert await state.registry.to_dict() == before


@pytest.mark.asyncio
async def test_unique_local_override_and_removal_preserve_identity_and_intent(
    discovery,
):
    """同一发行包的唯一源码优先；移除后回落发行包，保留 UUID、配置和启用意图。"""
    state = discovery
    write_plugin(state.site, installed=True)
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    uid = record.uid
    record.info.enabled = True
    await record.commit()
    local = write_plugin(
        state.config.plugins_path / "local", package="discovery_probe", version="2.0"
    )
    await discover.refresh(
        scope=discover.RefreshScope(changes=(SourceChange(str(local)),))
    )
    assert state.registry.by_name("discovery_probe") is record
    assert record.uid == uid and record.info.enabled
    assert record.info.source == "local" and record.info.is_local
    assert record.info.version == "2.0"
    assert record._project_dir == (local / "src").resolve()
    assert record.info.code_drift == PluginCodeDrift.NEEDS_RELOAD
    local.resolve().relative_to(state.config.plugins_path.resolve())
    shutil.rmtree(local)
    await discover.refresh(
        scope=discover.RefreshScope(changes=(SourceChange(str(local)),))
    )
    assert state.registry.by_name("discovery_probe") is record
    assert record.uid == uid and record.info.enabled
    assert record.info.source == "installed" and not record.info.is_local
    assert record._project_dir == state.site.resolve()
    assert record.info.code_drift == PluginCodeDrift.NEEDS_RELOAD


@pytest.mark.asyncio
async def test_same_source_directory_is_discovered_once(discovery, monkeypatch):
    """宿主与用户插件根实际相同时，不能将同一工程当成两份本地源码。"""
    state = discovery
    monkeypatch.setattr(state.config, "source_path", state.config.plugins_path.parent)
    write_plugin(state.config.plugins_path / "local")
    await discover.refresh()
    assert len(list(state.registry.values())) == 1


@pytest.mark.asyncio
async def test_repeated_distribution_search_does_not_create_duplicate_candidate(
    discovery, monkeypatch
):
    """同一发行元数据因重复搜索路径出现两次时，只保留一个实际候选。"""
    state = discovery
    write_plugin(state.site, installed=True)
    distributions = list(importlib.metadata.distributions())
    monkeypatch.setattr(
        importlib.metadata,
        "distributions",
        lambda **kwargs: [*distributions, *distributions],
    )
    await discover.refresh()
    assert len(list(state.registry.values())) == 1


@pytest.mark.asyncio
async def test_loaded_namespace_is_reserved_until_implementation_is_unloaded(discovery):
    """移除源码不等于卸载运行实例，其他插件不能立即接管仍在运行的导入名。"""
    state = discovery
    local = write_plugin(state.source / "original")
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    record._plugin_cls = BasePlugin
    before = await state.registry.to_dict()
    local.resolve().relative_to(state.source.resolve())
    shutil.rmtree(local)
    write_plugin(
        state.config.plugins_path / "new",
        package="new-package",
        identity="new_identity",
    )
    with pytest.raises(PluginPrecheckError):
        await discover.refresh()
    assert await state.registry.to_dict() == before
    record._plugin_cls = None
    await discover.refresh()
    assert state.registry.by_name("new_identity") is not None
    assert record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED


@pytest.mark.asyncio
async def test_install_rejects_local_override_before_changing_distribution(
    discovery, monkeypatch
):
    """本地工程生效时明确拒绝发行包安装，不能装包后才报告来源不一致。"""
    from app.core.plugin.manager import _PluginManager
    from app.plugin import uv

    write_plugin(discovery.source / "local")
    install = AsyncMock()
    monkeypatch.setattr(uv, "install", install)
    meta = PluginMeta.build(
        info={"plugin_name": "discovery_probe", "package_name": "discovery-probe"}
    )
    with pytest.raises(PluginPrecheckError, match="本地源码"):
        await _PluginManager().install(meta)
    install.assert_not_awaited()
    assert discovery.registry.by_name("discovery_probe").info.source == "local"


@pytest.mark.asyncio
async def test_reloading_local_override_replaces_installed_submodules(discovery):
    """显式重载来源后，入口与子模块都来自本地工程，不能混用旧发行包缓存。"""
    state = discovery
    write_plugin(state.site, installed=True)
    package = state.site / "discovery_probe"
    code = "from app.plugin.base import BasePlugin\nfrom .payload import VALUE\nclass Implementation(BasePlugin):\n    marker = VALUE\nPLUGIN = Implementation\n"
    (package / "__init__.py").write_text(code, encoding="utf-8")
    (package / "payload.py").write_text('VALUE="installed"\n', encoding="utf-8")
    record_file = state.site / "discovery_probe-1.0.dist-info/RECORD"
    record_file.write_text(
        record_file.read_text(encoding="utf-8") + "discovery_probe/payload.py,,\n",
        encoding="utf-8",
    )
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    record._plugin_cls = loader.load(record)
    try:
        assert record._plugin_cls.marker == "installed"
        local = write_plugin(state.config.plugins_path / "local", version="2.0")
        (local / "src/discovery_probe/__init__.py").write_text(code, encoding="utf-8")
        (local / "src/discovery_probe/payload.py").write_text(
            'VALUE="local"\n', encoding="utf-8"
        )
        await discover.refresh(
            scope=discover.RefreshScope(changes=(SourceChange(str(local)),))
        )
        loader.clear(record)
        implementation = loader.load(record)
        assert implementation.marker == "local"
        record._plugin_cls = implementation
    finally:
        loader.clear(record)


@pytest.mark.asyncio
async def test_removed_source_can_release_its_loaded_namespace(discovery):
    """工程消失后仍可按已加载入口的归属清理模块，避免命名空间永久被占用。"""
    state = discovery
    local = write_plugin(state.source / "original")
    (local / "src/discovery_probe/__init__.py").write_text(
        "from app.plugin.base import BasePlugin\nPLUGIN=BasePlugin\n", encoding="utf-8"
    )
    await discover.refresh()
    record = state.registry.by_name("discovery_probe")
    record._plugin_cls = loader.load(record)
    try:
        local.resolve().relative_to(state.source.resolve())
        shutil.rmtree(local)
        await discover.refresh()
        assert record._project_dir is None
        loader.clear(record)
        assert "discovery_probe" not in sys.modules
    finally:
        sys.modules.pop("discovery_probe", None)
