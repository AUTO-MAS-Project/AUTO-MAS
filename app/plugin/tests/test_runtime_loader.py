from __future__ import annotations

import sys
import types
import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from app.plugin.errors import PluginPrecheckError
from app.plugin.runtime import discover
from app.plugin.runtime import loader


def _record(tmp_path: Path, name: str):
    src = tmp_path / "src"
    package = src / name
    package.mkdir(parents=True)
    return types.SimpleNamespace(
        info=types.SimpleNamespace(
            import_name=name,
            source="local",
            package_name=name,
            plugin_name=name,
            requires=[],
            wants=[],
        ),
        _project_dir=src,
    ), package


def _write_plugin(package: Path, version: str) -> None:
    package.joinpath("__init__.py").write_text(
        "from app.plugin.base.plugin import BasePlugin\n"
        f"class Plugin(BasePlugin):\n    VERSION = '{version}'\n"
        "PLUGIN = Plugin\n",
        encoding="utf-8",
    )


def test_local_reload_reads_same_size_source_without_pyc(tmp_path: Path) -> None:
    record, package = _record(tmp_path, "fresh_plugin")
    _write_plugin(package, "one")

    first = loader.load(record)
    assert getattr(first, "VERSION") == "one"
    loader.clear(record)
    _write_plugin(package, "two")

    second = loader.load(record)
    assert getattr(second, "VERSION") == "two"
    assert not list(package.joinpath("__pycache__").glob("*.pyc"))
    loader.clear(record)


def test_clear_removes_none_sentinels_only_for_target(tmp_path: Path) -> None:
    record, package = _record(tmp_path, "sentinel_plugin")
    _write_plugin(package, "one")
    loader.load(record)
    sys.modules["sentinel_plugin.failed"] = cast(Any, None)
    sys.modules["other_plugin.failed"] = cast(Any, None)

    loader.clear(record)

    assert "sentinel_plugin" not in sys.modules
    assert "sentinel_plugin.failed" not in sys.modules
    assert sys.modules["other_plugin.failed"] is None


def test_namespace_package_is_rejected(tmp_path: Path) -> None:
    record, package = _record(tmp_path, "namespace_plugin")

    with pytest.raises(PluginPrecheckError, match="不支持 namespace package"):
        loader.load(record)


def test_plugin_api_version_mismatch_is_rejected(tmp_path: Path) -> None:
    record, package = _record(tmp_path, "versioned_plugin")
    package.joinpath("__init__.py").write_text(
        "from app.plugin.base.plugin import BasePlugin\n"
        "PLUGIN_API_VERSION = '4'\n"
        "class Plugin(BasePlugin):\n    pass\n"
        "PLUGIN = Plugin\n",
        encoding="utf-8",
    )

    with pytest.raises(PluginPrecheckError, match="不兼容"):
        loader.load(record)


def test_package_outside_module_has_explicit_error(tmp_path: Path) -> None:
    record, package = _record(tmp_path, "outside_plugin")
    _write_plugin(package, "one")
    package.joinpath("__init__.py").write_text(
        "from outside_module import VALUE\n"
        "from app.plugin.base.plugin import BasePlugin\n"
        "class Plugin(BasePlugin):\n    VERSION = VALUE\n"
        "PLUGIN = Plugin\n",
        encoding="utf-8",
    )
    package.parent.joinpath("outside_module.py").write_text("VALUE = 'one'\n", encoding="utf-8")

    with pytest.raises(PluginPrecheckError, match="包外模块 outside_module"):
        loader.load(record)


def test_refresh_invalidates_directory_finder_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    class Registry:
        def values(self):
            return []

        def by_name(self, name: str):
            return None

    class Config:
        plugin_path = Path("missing-plugin-root")
        plugin_registry = Registry()

    class I18n:
        async def invalidate(self) -> None:
            return None

    monkeypatch.setattr(discover.importlib, "invalidate_caches", lambda: called.append(True))
    monkeypatch.setitem(sys.modules, "app.core.config", types.SimpleNamespace(Config=Config))
    monkeypatch.setitem(sys.modules, "app.models.config", types.SimpleNamespace(PluginRecord=object))
    monkeypatch.setitem(sys.modules, "app.core.i18n", types.SimpleNamespace(i18n=I18n()))

    asyncio.run(discover.refresh(scope=discover.RefreshScope(changes=())))

    assert called == [True]


def test_installed_discovery_persists_search_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = tmp_path / "site-packages"
    package = site / "installed_plugin"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text("", encoding="utf-8")
    record = types.SimpleNamespace(_project_dir=None)
    record.info = types.SimpleNamespace(plugin_name="installed")

    class Distribution:
        name = "installed-plugin"
        files = [Path("installed_plugin/__init__.py")]
        metadata = types.SimpleNamespace()

        def locate_file(self, name: str) -> Path:
            return site

    monkeypatch.setattr(
        "app.plugin.runtime.discover.parse_to_plugin_record",
        lambda *args, **kwargs: record,
    )

    result = asyncio.run(discover._parse_installed_package(Distribution()))

    assert result is record
    assert record._project_dir == site.resolve()
