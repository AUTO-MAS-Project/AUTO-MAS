from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.core.script_config_codec import storage_to_form
from app.core.script_types import ScriptRecordCapability, ScriptTypeProvider
from app.core import Config
from app.core.task_manager import _TaskManager
from app.models.plugin_script_config import PluginScriptConfig
from app.models.task import ScriptItem
from app.plugins import ScriptAdapterDefinition, ScriptAdapterHooks


def _provider(*, resolver=None, metadata=None) -> ScriptTypeProvider:
    return ScriptTypeProvider(
        type_key="Example",
        display_name="Example",
        script_config_class=object,
        user_config_class=object,
        supported_modes=("AutoProxy", "ManualReview"),
        manager_factory=lambda _item: None,
        record_capability_resolver=resolver,
        metadata=dict(metadata or {}),
    )


def test_record_capability_defaults_to_provider_modes() -> None:
    capability = _provider().resolve_record_capability({})

    assert capability == ScriptRecordCapability(
        available=True,
        unavailable_reason=None,
        supported_modes=("AutoProxy", "ManualReview"),
    )


def test_record_capability_accepts_plugin_owned_result_type() -> None:
    provider = _provider(
        resolver=lambda _config: SimpleNamespace(
            available=True,
            unavailable_reason=None,
            supported_modes=("AutoProxy",),
        )
    )

    capability = provider.resolve_record_capability({"Engine": {"Path": "C:/engine"}})

    assert capability.supported_modes == ("AutoProxy",)


def test_global_unavailability_skips_record_resolver() -> None:
    called = False

    def resolver(_config):
        nonlocal called
        called = True
        return ScriptRecordCapability()

    capability = _provider(
        resolver=resolver,
        metadata={"available": False, "unavailable_reason": "adapter missing"},
    ).resolve_record_capability({})

    assert called is False
    assert capability.available is False
    assert capability.unavailable_reason == "adapter missing"
    assert capability.supported_modes == ()


def test_record_capability_rejects_unknown_task_mode() -> None:
    provider = _provider(
        resolver=lambda _config: ScriptRecordCapability(
            supported_modes=("UnknownMode",),
        )
    )

    with pytest.raises(ValueError, match="UnknownMode"):
        provider.resolve_record_capability({})


def test_record_capability_preserves_an_explicit_empty_mode_set() -> None:
    provider = _provider(
        resolver=lambda _config: ScriptRecordCapability(supported_modes=())
    )

    assert provider.resolve_record_capability({}).supported_modes == ()


def test_task_creation_validation_rejects_an_unavailable_record(monkeypatch) -> None:
    script_id = uuid.uuid4()
    script = SimpleNamespace(get=lambda _group, _name: "HSR")

    async def resolve_capability(_script_id):
        return ScriptRecordCapability(
            available=False,
            unavailable_reason="engine path missing",
            supported_modes=(),
        )

    monkeypatch.setattr(Config, "ScriptConfig", {script_id: script})
    monkeypatch.setattr(Config, "get_script_record_capability", resolve_capability)

    with pytest.raises(RuntimeError, match="engine path missing"):
        asyncio.run(
            _TaskManager()._validate_task_capabilities("AutoProxy", [script_id])
        )


def test_task_creation_validation_rejects_an_unsupported_mode(monkeypatch) -> None:
    script_id = uuid.uuid4()
    script = SimpleNamespace(get=lambda _group, _name: "HSR")

    async def resolve_capability(_script_id):
        return ScriptRecordCapability(
            available=True,
            supported_modes=("AutoProxy",),
        )

    monkeypatch.setattr(Config, "ScriptConfig", {script_id: script})
    monkeypatch.setattr(Config, "get_script_record_capability", resolve_capability)

    with pytest.raises(RuntimeError, match="ManualReview"):
        asyncio.run(
            _TaskManager()._validate_task_capabilities("ManualReview", [script_id])
        )


def test_missing_plugin_record_uses_read_only_fallback() -> None:
    plugin_config = PluginScriptConfig()
    asyncio.run(plugin_config.set("Meta", "PluginTypeKey", "MissingExample"))

    provider = Config._resolve_plugin_record_provider(plugin_config)
    payload = {"Info": {"Name": "preserved"}, "Extra": {"Value": 1}}
    form = asyncio.run(storage_to_form(provider, payload, "script"))
    capability = provider.resolve_record_capability(form)

    assert form == payload
    assert capability.available is False
    assert capability.supported_modes == ()
    assert "MissingExample" in str(capability.unavailable_reason)


def test_script_adapter_custom_manager_is_additive_to_legacy_hooks() -> None:
    class ScriptModel(BaseModel):
        Name: str = "script"

    class UserModel(BaseModel):
        Name: str = "user"

    sentinel = object()
    custom_definition = ScriptAdapterDefinition(
        type_key="CustomManager",
        display_name="Custom manager",
        hooks_factory=None,
        script_model=ScriptModel,
        user_model=UserModel,
        manager_factory=lambda _script_item, _provider: sentinel,  # type: ignore[arg-type]
    )
    custom_provider = custom_definition.build_provider(owner="test")

    script_item = ScriptItem(
        script_id=str(uuid.uuid4()),
        name="custom",
        status="等待",
    )
    assert custom_provider.create_manager(script_item) is sentinel

    hook_definition = ScriptAdapterDefinition(
        type_key="LegacyHooks",
        display_name="Legacy hooks",
        hooks_factory=ScriptAdapterHooks,
        script_model=ScriptModel,
        user_model=UserModel,
    )
    hook_provider = hook_definition.build_provider(owner="test")
    assert hook_provider.metadata["hooks_factory"] is ScriptAdapterHooks
