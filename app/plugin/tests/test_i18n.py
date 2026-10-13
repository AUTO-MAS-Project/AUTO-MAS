"""全局 i18n 资源服务测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core.config as core_config
from app.core.i18n import I18nManager
from app.models.config import PluginRecord
from app.plugin.types import PluginCodeDrift, PluginState


class Registry:
    def __init__(self, records: list[PluginRecord]) -> None:
        self._records = records

    def values(self):
        return iter(self._records)


def _record(project_dir: Path) -> PluginRecord:
    record = PluginRecord.build(
        info={
            "plugin_name": "demo",
            "package_name": "automas-plugin-demo",
            "import_name": "demo_pkg",
            "source": "local",
            "is_local": True,
            "state": PluginState.ENABLED,
            "code_drift": PluginCodeDrift.NORMAL,
        }
    )
    record._project_dir = project_dir
    return record


@pytest.mark.asyncio
async def test_messages_use_fixed_package_path_and_vue_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        package = src / "demo_pkg"
        i18n_dir = package / "i18n"
        i18n_dir.mkdir(parents=True)
        (i18n_dir / "en.json").write_text(
            '{"plugins.demo.title": "Demo", "plugins.demo.only_en": "Only"}',
            encoding="utf-8",
        )
        (i18n_dir / "zh_CN.json").write_text(
            '{"plugins.demo.title": "演示"}',
            encoding="utf-8",
        )
        (Path(tmp) / "i18n").mkdir()
        (Path(tmp) / "i18n" / "zh_CN.json").write_text(
            '{"plugins.demo.title": "错误候选路径"}',
            encoding="utf-8",
        )

        record = _record(src)
        monkeypatch.setattr(
            core_config.Config,
            "plugin_registry",
            Registry([record]),
        )
        monkeypatch.setattr(
            core_config.Config,
            "setting",
            SimpleNamespace(language=SimpleNamespace(locale="zh_CN")),
        )

        manager = I18nManager()
        manager._initialized = True
        messages = await manager.get_messages("zh_CN")

        assert messages == {
            "plugins": {
                "demo": {
                    "only_en": "Only",
                    "title": "演示",
                }
            }
        }


@pytest.mark.asyncio
async def test_missing_locale_falls_back_to_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        i18n_dir = src / "demo_pkg" / "i18n"
        i18n_dir.mkdir(parents=True)
        (i18n_dir / "ja.json").write_text(
            '{"plugins.demo.only_ja": "だけ"}',
            encoding="utf-8",
        )
        record = _record(src)
        monkeypatch.setattr(core_config.Config, "plugin_registry", Registry([record]))
        monkeypatch.setattr(
            core_config.Config,
            "setting",
            SimpleNamespace(language=SimpleNamespace(locale="zh_CN")),
        )

        manager = I18nManager()
        manager._initialized = True
        messages = await manager.get_messages("zh_CN")

        assert messages["plugins"]["demo"]["only_ja"] == "plugins.demo.only_ja"


@pytest.mark.asyncio
async def test_empty_translation_does_not_use_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        i18n_dir = src / "demo_pkg" / "i18n"
        i18n_dir.mkdir(parents=True)
        (i18n_dir / "en.json").write_text(
            '{"plugins.demo.title": "English"}',
            encoding="utf-8",
        )
        (i18n_dir / "zh_CN.json").write_text(
            '{"plugins.demo.title": ""}',
            encoding="utf-8",
        )
        record = _record(src)
        monkeypatch.setattr(core_config.Config, "plugin_registry", Registry([record]))
        monkeypatch.setattr(
            core_config.Config,
            "setting",
            SimpleNamespace(language=SimpleNamespace(locale="zh_CN")),
        )

        manager = I18nManager()
        manager._initialized = True
        messages = await manager.get_messages("zh_CN")

        assert messages["plugins"]["demo"]["title"] == ""
