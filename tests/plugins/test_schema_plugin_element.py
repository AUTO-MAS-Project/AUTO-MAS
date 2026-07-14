from types import SimpleNamespace

import pytest

from app.plugins import PluginField, ScriptAdapterDefinition, ScriptAdapterHooks
from app.plugins.frontend_extensions import (
    PluginFrontendElementDescriptor,
    PluginFrontendManifest,
    resolve_plugin_frontend_element,
)


class _Hooks(ScriptAdapterHooks):
    pass


def test_frontend_element_descriptor_validates_manifest_and_assets(monkeypatch):
    manifest = PluginFrontendManifest.model_validate(
        {
            "version": 2,
            "entry": "frontend/index.js",
            "style": ["frontend/index.css"],
            "elements": [{"tag": "schema-test-element"}],
        }
    )
    loaded_assets = []
    monkeypatch.setattr(
        "app.plugins.frontend_extensions._load_frontend_dev_manifest",
        lambda plugin_name, plugin_source: None,
    )
    monkeypatch.setattr(
        "app.plugins.frontend_extensions.load_frontend_manifest",
        lambda plugin_name, plugin_source: manifest,
    )
    monkeypatch.setattr(
        "app.plugins.frontend_extensions.load_frontend_asset",
        lambda plugin_name, plugin_source, asset_path: loaded_assets.append(asset_path),
    )

    descriptor = resolve_plugin_frontend_element(
        "schema-element-plugin",
        "schema-test-element",
        plugin_source=SimpleNamespace(),
    )

    assert loaded_assets == ["frontend/index.js", "frontend/index.css"]
    assert descriptor.manifest_version == 2
    assert descriptor.entry_asset_url.endswith("/frontend/index.js?v=2")
    assert descriptor.style_asset_urls[0].endswith("/frontend/index.css?v=2")


def test_frontend_element_descriptor_rejects_undeclared_tag(monkeypatch):
    manifest = PluginFrontendManifest.model_validate(
        {
            "entry": "frontend/index.js",
            "elements": [{"tag": "declared-element"}],
        }
    )
    monkeypatch.setattr(
        "app.plugins.frontend_extensions._load_frontend_dev_manifest",
        lambda plugin_name, plugin_source: None,
    )
    monkeypatch.setattr(
        "app.plugins.frontend_extensions.load_frontend_manifest",
        lambda plugin_name, plugin_source: manifest,
    )

    with pytest.raises(ValueError, match="未出现在插件 frontend manifest"):
        resolve_plugin_frontend_element(
            "schema-element-plugin",
            "missing-element",
            plugin_source=SimpleNamespace(),
        )


def test_plugin_element_is_resolved_and_not_persisted(monkeypatch):
    descriptor = PluginFrontendElementDescriptor(
        frontend_plugin="schema-element-plugin",
        element_tag="schema-test-element",
        entry_asset_url="/api/plugins/assets/schema-element-plugin/frontend/index.js",
        style_asset_urls=[],
        manifest_version=1,
    )
    monkeypatch.setattr(
        "app.plugins.frontend_extensions.resolve_plugin_frontend_element",
        lambda plugin_name, element_tag: descriptor,
    )
    definition = ScriptAdapterDefinition(
        type_key="SchemaElementTest",
        display_name="Schema Element 测试",
        hooks_factory=_Hooks,
        script_groups=[
            PluginField.group(
                "Info",
                "基础设置",
                [PluginField.string("Name", "名称")],
            )
        ],
        user_groups=[
            PluginField.group(
                "Task",
                "任务设置",
                [
                    PluginField.plugin_element(
                        "TaskEditor",
                        "schema-test-element",
                        size="1/1",
                    )
                ],
            )
        ],
    )

    provider = definition.build_provider(
        owner="schema-element-owner",
        plugin_context=SimpleNamespace(plugin_name="schema-element-plugin"),
    )
    field = provider.user_schema["groups"][0]["fields"][0]

    assert field["type"] == "plugin-element"
    assert field["persisted"] is False
    assert field["frontend_extension"]["element_tag"] == "schema-test-element"
    assert not hasattr(provider.user_config_class(), "Task_TaskEditor")
