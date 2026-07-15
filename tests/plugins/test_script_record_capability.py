from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.core.script_config_codec import storage_to_form
from app.core.script_types import ScriptRecordCapability, ScriptTypeProvider
from app.core import Config
from app.core.task_manager import _TaskManager
from app.models.ConfigBase import MultipleConfig
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


def test_legacy_hsr_storage_survives_without_the_plugin(
    tmp_path,
    monkeypatch,
) -> None:
    script_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    config_path = tmp_path / "ScriptConfig.json"
    config_path.write_text(
        json.dumps(
            {
                "instances": [{"uid": script_id, "type": "HSRConfig"}],
                script_id: {
                    "Info": {
                        "Name": "legacy HSR",
                        "M7APath": "C:/M7A",
                        "SRAPath": "C:/SRA",
                    },
                    "Run": {"LowPerformanceMode": True},
                    "SubConfigsInfo": {
                        "UserData": {
                            "instances": [
                                {"uid": user_id, "type": "HSRUserConfig"}
                            ],
                            user_id: {
                                "Info": {
                                    "Name": "legacy user",
                                    "Id": "account",
                                    "Password": "secret",
                                },
                                "Data": {"ProxyTimes": 2},
                                "SubConfigsInfo": {
                                    "Notify_CustomWebhooks": {
                                        "instances": [],
                                    }
                                },
                            },
                        }
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert Config._migrate_legacy_hsr_storage(config_path) == 1
    assert Config._migrate_legacy_hsr_storage(config_path) == 0

    migrated = json.loads(config_path.read_text(encoding="utf-8"))
    assert migrated["instances"] == [
        {"uid": script_id, "type": "PluginScriptConfig"}
    ]
    script_payload = json.loads(migrated[script_id]["PluginData"]["Config"])
    assert script_payload["SRA"]["Path"] == "C:/SRA"
    assert script_payload["M7A"] == {
        "Path": "C:/M7A",
        "LowPerformanceMode": True,
    }

    migrated_user = migrated[script_id]["SubConfigsInfo"]["UserData"][user_id]
    user_payload = json.loads(migrated_user["PluginData"]["Config"])
    assert user_payload["SRA"] == {"Id": "account", "Password": "secret"}
    assert user_payload["Data"]["ProxyTimes"] == 2
    assert user_payload["Notify"]["CustomWebhooks"] == {"instances": []}

    async def load_migrated_storage() -> MultipleConfig[PluginScriptConfig]:
        storage = MultipleConfig([PluginScriptConfig])
        await storage.connect(config_path)
        return storage

    storage = asyncio.run(load_migrated_storage())
    assert len(storage) == 1
    assert len(storage[uuid.UUID(script_id)].UserData) == 1

    monkeypatch.setattr(Config, "ScriptConfig", storage)
    script_records = asyncio.run(Config.get_script_records())
    user_records = asyncio.run(Config.get_user_records(script_id))

    assert script_records[0].available is False
    assert script_records[0].type == "HSR"
    assert script_records[0].config["SRA"]["Path"] == "C:/SRA"
    assert user_records[0].config["SRA"] == {
        "Id": "account",
        "Password": "secret",
    }


def test_legacy_hsr_migration_stops_before_dropping_malformed_users(tmp_path) -> None:
    script_id = str(uuid.uuid4())
    missing_user_id = str(uuid.uuid4())
    config_path = tmp_path / "ScriptConfig.json"
    original = {
        "instances": [{"uid": script_id, "type": "HSRConfig"}],
        script_id: {
            "Info": {"Name": "legacy HSR"},
            "SubConfigsInfo": {
                "UserData": {
                    "instances": [
                        {"uid": missing_user_id, "type": "HSRUserConfig"}
                    ]
                }
            },
        },
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="避免数据丢失"):
        Config._migrate_legacy_hsr_storage(config_path)

    assert json.loads(config_path.read_text(encoding="utf-8")) == original
