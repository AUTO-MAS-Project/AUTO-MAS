"""插件发现测试：元数据解析、增量刷新与代码漂移状态迁移。"""

from __future__ import annotations

import asyncio
import tempfile
import tomllib
from email.message import Message
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from pyproject_metadata import StandardMetadata

import app.core.config as core_config
from app.models.config import PluginRecord, PluginRegistryCollection
from app.plugin.runtime import discover
from app.plugin.runtime.metadata import parse_to_plugin_record
from app.plugin.types import PluginCodeDrift, PluginState, SourceChange


class Registry(PluginRegistryCollection):
    """不触碰全局配置持久化的独立插件注册表。"""

    _default_entry_types: ClassVar[tuple[type, ...]] = ()


async def _registry() -> Registry:
    registry = Registry()
    await registry.activate()
    registry.add_type(PluginRecord)
    await registry.commit()
    return registry


def _write_local(
    root: Path,
    *,
    plugin_name: str = "demo",
    import_name: str = "demo_pkg",
    keywords: list[str] | None = None,
    extra_tops: int = 0,
) -> Path:
    """在 root 下写入标准本地插件工程并返回工程根。"""
    child = root / plugin_name
    src = child / "src" / import_name
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("PLUGIN = None\n", encoding="utf-8")
    for index in range(extra_tops):
        extra = child / "src" / f"extra_{index}"
        extra.mkdir()
        (extra / "__init__.py").write_text("", encoding="utf-8")
    plugin_keywords = (
        keywords
        if keywords is not None
        else [
            "auto-mas-plugin",
            f"auto-mas-id:{plugin_name}",
        ]
    )
    (child / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "automas-plugin-{plugin_name}"\n'
        'version = "1.0.0"\n'
        'description = "demo desc"\n'
        f"keywords = {plugin_keywords!r}\n"
        "[project.urls]\n"
        'Documentation = "https://doc.example.com/demo"\n',
        encoding="utf-8",
    )
    return child


def _draft(**overrides: object) -> PluginRecord:
    info: dict[str, Any] = {
        "plugin_name": "demo",
        "package_name": "automas-plugin-demo",
        "version": "1.0.0",
        "docs_url": "",
        "import_name": "demo_pkg",
        "source": "local",
        "is_local": True,
    }
    info.update(overrides)
    return PluginRecord.build(info=info)


def test_draft_local_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        child = _write_local(Path(tmp))
        data = tomllib.loads((child / "pyproject.toml").read_text(encoding="utf-8"))
        metadata = StandardMetadata.from_pyproject(
            data,
            project_dir=child,
        ).as_rfc822()
        draft = parse_to_plugin_record(
            metadata,
            import_name="demo_pkg",
            source="local",
        )

        assert draft is not None
        assert draft.info.plugin_name == "demo"
        assert draft.info.import_name == "demo_pkg"
        assert draft.info.source == "local"
        assert draft.info.is_local
        assert not draft.info.is_core
        assert draft.info.state == PluginState.UNLOADED


def test_draft_local_invalid() -> None:
    metadata = Message()
    metadata["Keywords"] = "no-gate"
    assert (
        parse_to_plugin_record(
            metadata,
            import_name="demo_pkg",
            source="local",
        )
        is None
    )

    metadata["Keywords"] = "auto-mas-plugin, auto-mas-id:a, auto-mas-id:b"
    assert (
        parse_to_plugin_record(
            metadata,
            import_name="demo_pkg",
            source="local",
        )
        is None
    )


def test_draft_installed() -> None:
    metadata = Message()
    metadata["Name"] = "automas-plugin-demo"
    metadata["Version"] = "1.0.0"
    metadata["Keywords"] = "auto-mas-plugin, auto-mas-id:demo"
    metadata["Summary"] = "demo summary"
    metadata["Project-URL"] = "Documentation, https://doc.example.com/demo"
    draft = parse_to_plugin_record(
        metadata,
        import_name="demo_pkg",
        source="installed",
    )

    assert draft is not None
    assert draft.info.plugin_name == "demo"
    assert draft.info.import_name == "demo_pkg"
    assert draft.info.source == "installed"
    assert not draft.info.is_local
    assert draft.info.docs_url == "https://doc.example.com/demo"


def test_refresh_adds_new_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            await discover.refresh(
                scope=discover.RefreshScope(
                    changes=(
                        SourceChange(local_dir=str(child), code_touched=True),
                    )
                )
            )
            record = registry.by_name("demo")
            assert record is not None
            assert record.info.code_drift == PluginCodeDrift.NORMAL
            assert record.info.state == PluginState.UNLOADED
            assert not record.info.enabled
            assert record._project_dir == (child / "src").resolve()

    asyncio.run(_run())


def test_refresh_metadata_preserves_runtime_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            record.info.state = PluginState.ENABLED
            record.info.enabled = True
            record.info.requires = ["service_a"]
            await record.commit()

            pyproject = child / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8").replace(
                    'version = "1.0.0"',
                    'version = "2.0.0"',
                ),
                encoding="utf-8",
            )

            await discover.refresh(scope=scope)

            assert record.info.version == "2.0.0"
            assert record.info.state == PluginState.ENABLED
            assert record.info.enabled
            assert record.info.requires == ["service_a"]
            assert record.info.code_drift == PluginCodeDrift.NORMAL
            assert record._project_dir == (child / "src").resolve()

    asyncio.run(_run())


def test_refresh_code_change_only_marks_selected_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha_dir = _write_local(root, plugin_name="alpha", import_name="alpha_pkg")
            beta_dir = _write_local(root, plugin_name="beta", import_name="beta_pkg")

            await discover.refresh(
                scope=discover.RefreshScope(
                    changes=(
                        SourceChange(local_dir=str(alpha_dir)),
                        SourceChange(local_dir=str(beta_dir)),
                    )
                )
            )
            await discover.refresh(
                scope=discover.RefreshScope(
                    changes=(
                        SourceChange(local_dir=str(alpha_dir), code_touched=True),
                    )
                )
            )

            alpha = registry.by_name("alpha")
            beta = registry.by_name("beta")
            assert alpha is not None
            assert beta is not None
            assert alpha.info.code_drift == PluginCodeDrift.NEEDS_RELOAD
            assert beta.info.code_drift == PluginCodeDrift.NORMAL

    asyncio.run(_run())


def test_refresh_keeps_needs_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            record.info.code_drift = PluginCodeDrift.NEEDS_RELOAD
            await record.commit()

            await discover.refresh(scope=scope)

            assert record.info.code_drift == PluginCodeDrift.NEEDS_RELOAD

    asyncio.run(_run())


def test_refresh_rediscovery_marks_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            record.info.code_drift = PluginCodeDrift.PACKAGE_REMOVED
            await record.commit()

            await discover.refresh(scope=scope)

            assert record.info.code_drift == PluginCodeDrift.NEEDS_RELOAD

    asyncio.run(_run())


def test_refresh_does_not_infer_reload_from_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            changed = _draft(import_name="renamed_pkg")
            with patch.object(
                discover,
                "_parse_source_package",
                new=AsyncMock(return_value=changed),
            ):
                await discover.refresh(scope=scope)

            assert record.info.import_name == "renamed_pkg"
            assert record.info.code_drift == PluginCodeDrift.NORMAL

    asyncio.run(_run())


def test_refresh_uses_installed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            installed = _draft(source="installed", is_local=False)
            with (
                patch.object(
                    discover,
                    "_parse_source_package",
                    new=AsyncMock(return_value=None),
                ),
                patch.object(
                    discover.importlib_metadata,
                    "distribution",
                    return_value=object(),
                ),
                patch.object(
                    discover,
                    "_parse_installed_package",
                    new=AsyncMock(return_value=installed),
                ),
            ):
                await discover.refresh(scope=scope)

            assert record.info.source == "installed"
            assert record.info.code_drift == PluginCodeDrift.NEEDS_RELOAD
            assert record._project_dir is None

    asyncio.run(_run())


def test_refresh_marks_removed_when_sources_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        registry = await _registry()
        monkeypatch.setattr(core_config.Config, "plugin_registry", registry)

        with tempfile.TemporaryDirectory() as tmp:
            child = _write_local(Path(tmp))
            scope = discover.RefreshScope(
                changes=(SourceChange(local_dir=str(child)),),
            )
            await discover.refresh(scope=scope)
            record = registry.by_name("demo")
            assert record is not None

            with (
                patch.object(
                    discover,
                    "_parse_source_package",
                    new=AsyncMock(side_effect=ValueError("broken local package")),
                ),
                patch.object(
                    discover.importlib_metadata,
                    "distribution",
                    side_effect=discover.importlib_metadata.PackageNotFoundError(
                        "automas-plugin-demo"
                    ),
                ),
            ):
                await discover.refresh(scope=scope)

            assert record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED
            assert record._project_dir is None

    asyncio.run(_run())
