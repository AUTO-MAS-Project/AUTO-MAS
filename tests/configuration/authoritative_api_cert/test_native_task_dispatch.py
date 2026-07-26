"""Config v2 authoritative task dispatch and lease regression tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.configuration as configuration
import app.core.script_types as script_types
import app.core.task_manager as task_manager


class _FakeScriptNode:
    def __init__(self, *, fail_lock: bool = False) -> None:
        self.is_locked = False
        self.fail_lock = fail_lock
        self.lock_count = 0
        self.unlock_count = 0

    async def lock(self) -> None:
        if self.fail_lock:
            raise RuntimeError("lock failed")
        self.is_locked = True
        self.lock_count += 1

    async def unlock(self) -> None:
        self.is_locked = False
        self.unlock_count += 1


@pytest.mark.asyncio
async def test_authoritative_dispatch_fails_closed_before_native_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )
    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(initialized=False),
    )

    with pytest.raises(task_manager.TaskRuntimeUnavailableError, match="initialized"):
        await task_manager._ensure_task_runtime_available()


@pytest.mark.asyncio
async def test_authoritative_dispatch_opens_after_native_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )
    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(initialized=True),
    )

    await task_manager._ensure_task_runtime_available()


def test_authoritative_provider_resolution_uses_native_type_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_provider = object()
    registry = SimpleNamespace(
        bootstrap=lambda: None,
        get=lambda type_key: expected_provider if type_key == "General" else None,
    )
    monkeypatch.setattr(
        configuration,
        "CONFIG_V2_MODE",
        configuration.CONFIG_V2_MODE_AUTHORITATIVE,
    )
    monkeypatch.setattr(script_types, "script_type_registry", registry)
    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(get_script_type_key=lambda _script_id: "General"),
    )

    task = task_manager.Task.__new__(task_manager.Task)
    assert task._resolve_script_provider(uuid.uuid4()) is expected_provider


@pytest.mark.asyncio
async def test_script_leases_are_owner_aware_and_release_residual_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_id = uuid.uuid4()
    first_task = uuid.uuid4()
    second_task = uuid.uuid4()
    node = _FakeScriptNode()
    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(ScriptConfig={script_id: node}),
    )
    manager = task_manager._TaskManager()

    await manager._acquire_script_leases(first_task, [script_id, script_id])
    assert manager._script_leases == {script_id: first_task}
    assert node.is_locked is True
    assert node.lock_count == 1

    with pytest.raises(RuntimeError, match="占用"):
        await manager._acquire_script_leases(second_task, [script_id])

    await manager._release_script_leases(first_task)
    assert manager._script_leases == {}
    assert node.is_locked is False
    assert node.unlock_count == 1


@pytest.mark.asyncio
async def test_script_lease_release_uses_mapping_access_not_async_export_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MultipleConfig.get exports data asynchronously; leases need the live node."""

    script_id = uuid.uuid4()
    task_id = uuid.uuid4()
    node = _FakeScriptNode()

    class _FakeMultipleConfig:
        def __contains__(self, key: uuid.UUID) -> bool:
            return key == script_id

        def __getitem__(self, key: uuid.UUID) -> _FakeScriptNode:
            assert key == script_id
            return node

        async def get(self, _key: uuid.UUID) -> dict:
            raise AssertionError("lease cleanup must not call async export get()")

    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(ScriptConfig=_FakeMultipleConfig()),
    )
    manager = task_manager._TaskManager()
    manager._script_leases[script_id] = task_id
    node.is_locked = True

    await manager._release_script_leases(task_id)

    assert manager._script_leases == {}
    assert node.is_locked is False
    assert node.unlock_count == 1


@pytest.mark.asyncio
async def test_partial_lease_acquire_rolls_back_owned_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    task_id = uuid.uuid4()
    first = _FakeScriptNode()
    second = _FakeScriptNode(fail_lock=True)
    monkeypatch.setattr(
        task_manager,
        "Config",
        SimpleNamespace(ScriptConfig={first_id: first, second_id: second}),
    )
    manager = task_manager._TaskManager()

    with pytest.raises(RuntimeError, match="lock failed"):
        await manager._acquire_script_leases(task_id, [first_id, second_id])

    assert manager._script_leases == {}
    assert first.is_locked is False
    assert first.unlock_count == 1
