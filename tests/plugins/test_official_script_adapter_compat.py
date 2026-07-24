from __future__ import annotations

import asyncio
from functools import wraps
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.script_types import (
    LEGACY_SCRIPT_TYPE_BY_TYPE_KEY,
    ScriptTypeRegistry,
)
from app.plugins.fields import PluginFieldDeclaration, PluginFieldGroup
from app.plugins.script_adapter import ScriptAdapterDefinition
from app.plugins.emulator_compat import LegacyEmulatorService
from app.plugins.event_bus import EventBus
from app.plugins.loader import (
    EMULATOR_SERVICE_NAME,
    HOST_EMULATOR_COMPAT_OWNER,
    PluginLoader,
    PluginRecord,
)
from app.plugins.service_registry import ServiceRegistry


def _run_async(test_func):
    """让异步测试在不依赖 pytest-asyncio 的环境中运行。"""

    @wraps(test_func)
    def wrapper(*args: Any, **kwargs: Any):
        return asyncio.run(test_func(*args, **kwargs))

    return wrapper


class _MaaAdapterPlugin:
    provides: list[str] = []
    needs = [EMULATOR_SERVICE_NAME]
    wants: list[str] = []


class _MaaEndAdapterPlugin(_MaaAdapterPlugin):
    pass


class _RealEmulatorPlugin:
    provides = [EMULATOR_SERVICE_NAME]
    needs: list[str] = []
    wants: list[str] = []

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    async def on_start(self) -> None:
        self.ctx.service.set(EMULATOR_SERVICE_NAME, self)

    async def on_stop(self, _reason: str) -> None:
        return None


class _FailingRealEmulatorPlugin(_RealEmulatorPlugin):
    async def on_start(self) -> None:
        raise RuntimeError("emulator startup failed")


class _StartingMaaAdapterPlugin(_MaaAdapterPlugin):
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    async def on_start(self) -> None:
        assert isinstance(
            self.ctx.service.get(EMULATOR_SERVICE_NAME),
            LegacyEmulatorService,
        )

    async def on_stop(self, _reason: str) -> None:
        return None


class _NativeScriptInfo(BaseModel):
    Name: str = "native script"


class _NativeScriptModel(BaseModel):
    Info: _NativeScriptInfo = _NativeScriptInfo()


class _NativeUserInfo(BaseModel):
    Name: str = "native user"


class _NativeUserModel(BaseModel):
    Info: _NativeUserInfo = _NativeUserInfo()


def _plugin_instance(instance_id: str, plugin_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=instance_id,
        plugin=plugin_name,
        enabled=True,
        name=plugin_name,
        config={},
    )


def _prepare_loader(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    plugin_classes: dict[str, type[Any]],
) -> tuple[PluginLoader, list[str]]:
    service = ServiceRegistry()
    loader = PluginLoader(
        EventBus(),
        plugins_dir=tmp_path / "plugins",
        service=service,
    )
    loader.discovered_plugins = {
        plugin_name: PluginLoader.PluginSource(source="pypi")
        for plugin_name in plugin_classes
    }

    def resolve_plugin(plugin_name: str, *_args: Any, **_kwargs: Any):
        return None, plugin_classes[plugin_name]

    loaded: list[str] = []

    async def load_instance(**kwargs: Any) -> PluginRecord:
        loaded.append(str(kwargs["instance_id"]))
        return PluginRecord(
            instance_id=str(kwargs["instance_id"]),
            plugin_name=str(kwargs["plugin_name"]),
            path=None,
            status="active",
        )

    monkeypatch.setattr(loader, "_resolve_plugin_module_and_class", resolve_plugin)
    monkeypatch.setattr(loader, "load_instance", load_instance)
    return loader, loaded


def test_maaend_is_reserved_for_the_official_plugin_adapter() -> None:
    registry = ScriptTypeRegistry()

    registry._register_builtin_providers()

    with pytest.raises(KeyError, match="MaaEnd"):
        registry.get("MaaEnd")


def test_maaend_legacy_metadata_remains_available_before_plugin_activation() -> None:
    metadata = LEGACY_SCRIPT_TYPE_BY_TYPE_KEY["MaaEnd"]

    assert metadata["script_class_name"] == "MaaEndConfig"
    assert metadata["user_class_name"] == "MaaEndUserConfig"


def test_authoritative_model_adapter_keeps_pydantic_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.configuration as configuration

    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )
    definition = ScriptAdapterDefinition(
        type_key="NativeModel",
        display_name="Native Model",
        hooks_factory=None,
        script_model=_NativeScriptModel,
        user_model=_NativeUserModel,
        manager_factory=lambda _item, _provider: object(),
    )

    provider = definition.build_provider()

    assert provider.script_config_class is _NativeScriptModel
    assert provider.user_config_class is _NativeUserModel
    assert provider.build_script_schema()["groups"][0]["key"] == "Info"
    assert provider.build_user_schema()["groups"][0]["key"] == "Info"


def test_authoritative_group_adapter_uses_pydantic_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.configuration as configuration

    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )
    groups = (
        PluginFieldGroup(
            key="Info",
            label="Info",
            fields=(
                PluginFieldDeclaration(
                    name="Name",
                    label="Name",
                    field_type="string",
                    default="native group",
                ),
            ),
        ),
    )
    definition = ScriptAdapterDefinition(
        type_key="NativeGroups",
        display_name="Native Groups",
        hooks_factory=None,
        script_groups=groups,
        user_groups=groups,
        script_class_name="NativeGroupsConfig",
        user_class_name="NativeGroupsUserConfig",
        manager_factory=lambda _item, _provider: object(),
    )

    provider = definition.build_provider()

    assert issubclass(provider.script_config_class, BaseModel)
    assert issubclass(provider.user_config_class, BaseModel)
    assert provider.script_config_class.model_validate(
        {"Info": {"Name": "custom"}}
    ).model_dump() == {"Info": {"Name": "custom"}}
    assert provider.build_script_schema()["groups"][0]["fields"][0]["default"] == (
        "native group"
    )


@_run_async
async def test_host_emulator_fallback_satisfies_maa_adapter_planning(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader, loaded = _prepare_loader(
        tmp_path,
        monkeypatch,
        {
            "script_MAA": _MaaAdapterPlugin,
            "maaend_adapter": _MaaEndAdapterPlugin,
        },
    )

    await loader.load_instances(
        [
            _plugin_instance("script_MAA:default", "script_MAA"),
            _plugin_instance("maaend_adapter:default", "maaend_adapter"),
        ]
    )

    assert set(loaded) == {"script_MAA:default", "maaend_adapter:default"}
    assert loader.startup_failed_instances == {}
    assert isinstance(
        loader.service.get(EMULATOR_SERVICE_NAME),
        LegacyEmulatorService,
    )
    assert loader.service.owners(EMULATOR_SERVICE_NAME) == {
        HOST_EMULATOR_COMPAT_OWNER
    }


@_run_async
async def test_real_emulator_provider_suppresses_host_fallback(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader, loaded = _prepare_loader(
        tmp_path,
        monkeypatch,
        {
            "emulator": _RealEmulatorPlugin,
            "script_MAA": _MaaAdapterPlugin,
        },
    )

    await loader.load_instances(
        [
            _plugin_instance("emulator:real", "emulator"),
            _plugin_instance("script_MAA:default", "script_MAA"),
        ]
    )

    assert loaded == ["emulator:real", "script_MAA:default"]
    assert HOST_EMULATOR_COMPAT_OWNER not in loader.service.owners(
        EMULATOR_SERVICE_NAME
    )

    real_service = object()
    loader.service.set(EMULATOR_SERVICE_NAME, real_service, "emulator:real")
    assert loader.service.get(EMULATOR_SERVICE_NAME) is real_service


@_run_async
async def test_started_real_emulator_provider_never_coexists_with_host_fallback(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PluginLoader(
        EventBus(),
        plugins_dir=tmp_path / "plugins",
        service=ServiceRegistry(),
    )
    loader.discovered_plugins = {
        "emulator": PluginLoader.PluginSource(source="pypi")
    }
    monkeypatch.setattr(
        loader,
        "_resolve_plugin_module_and_class",
        lambda *_args, **_kwargs: (None, _RealEmulatorPlugin),
    )

    await loader.load_instances(
        [_plugin_instance("emulator:real", "emulator")]
    )

    assert loader.records["emulator:real"].status == "active"
    assert loader.service.owners(EMULATOR_SERVICE_NAME) == {"emulator:real"}
    assert HOST_EMULATOR_COMPAT_OWNER not in loader.service.owners(
        EMULATOR_SERVICE_NAME
    )

    await loader.unload_all()


@_run_async
async def test_failed_real_emulator_provider_restores_host_fallback_for_consumers(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = PluginLoader(
        EventBus(),
        plugins_dir=tmp_path / "plugins",
        service=ServiceRegistry(),
    )
    plugin_classes = {
        "emulator": _FailingRealEmulatorPlugin,
        "script_MAA": _StartingMaaAdapterPlugin,
    }
    loader.discovered_plugins = {
        plugin_name: PluginLoader.PluginSource(source="pypi")
        for plugin_name in plugin_classes
    }

    def resolve_plugin(plugin_name: str, *_args: Any, **_kwargs: Any):
        return None, plugin_classes[plugin_name]

    monkeypatch.setattr(loader, "_resolve_plugin_module_and_class", resolve_plugin)

    await loader.load_instances(
        [
            _plugin_instance("emulator:real", "emulator"),
            _plugin_instance("script_MAA:default", "script_MAA"),
        ]
    )

    assert loader.records["emulator:real"].status == "error"
    assert loader.records["script_MAA:default"].status == "active"
    assert loader.service.owners(EMULATOR_SERVICE_NAME) == {
        HOST_EMULATOR_COMPAT_OWNER
    }
    assert isinstance(
        loader.service.get(EMULATOR_SERVICE_NAME),
        LegacyEmulatorService,
    )

    await loader.unload_all()


@_run_async
async def test_host_emulator_fallback_is_removed_during_loader_shutdown(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader, _loaded = _prepare_loader(
        tmp_path,
        monkeypatch,
        {"script_MAA": _MaaAdapterPlugin},
    )
    await loader.load_instances(
        [_plugin_instance("script_MAA:default", "script_MAA")]
    )
    assert loader.service.ready(EMULATOR_SERVICE_NAME)

    await loader.unload_all()

    assert not loader.service.ready(EMULATOR_SERVICE_NAME)
    assert HOST_EMULATOR_COMPAT_OWNER not in loader.service.owners(
        EMULATOR_SERVICE_NAME
    )
