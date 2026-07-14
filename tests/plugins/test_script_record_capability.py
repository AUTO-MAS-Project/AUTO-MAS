from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.script_types import ScriptRecordCapability, ScriptTypeProvider
from app.core import Config
from app.core.task_manager import _TaskManager


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
