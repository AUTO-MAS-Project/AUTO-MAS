"""MAA 资源更新中断后的显式恢复门禁。"""

import json
from datetime import datetime, timezone
from tests.runtime_support import RuntimeStub as SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.task.MAA import manager
from app.task.MAA.tools import resource_install_recovery
from app.task.MAA.tools import resource_update as resource
from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError


@pytest.fixture
def partial(tmp_path, monkeypatch):
    install = tmp_path / "MAA"
    install.mkdir()
    (install / "MAA.exe").touch()
    (install / "config").mkdir()
    marker = install / ".automas-resource-update.json"
    marker.write_text(json.dumps({"target": "2026-11-10T00:00:00+00:00"}))
    instance = object.__new__(manager.MaaManager)
    instance.script_info = SimpleNamespace(
        script_id="test-maa", name="MAA 恢复", set_log=AsyncMock()
    )
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=False)
    )
    instance.task_info = SimpleNamespace(task_id="task", mode="AutoProxy")
    instance.maa_set_path = install / "config"
    return install, marker, instance


def test_resource_marker_is_not_skippable_when_changed(partial):
    root, marker, _ = partial
    snapshot = marker.read_bytes()
    marker.write_text('{"target":"2026-11-11T00:00:00+00:00"}')
    with pytest.raises(MaaUpdateUnsafeError, match="已变化"):
        resource.verify_resource_recovery_marker(root, snapshot)
    assert marker.is_file()


@pytest.mark.asyncio
async def test_maa_recovery_requires_user_confirmation(partial, monkeypatch):
    root, marker, instance = partial
    prompt = AsyncMock(side_effect=MaaUpdateUnsafeError("用户取消"))
    monkeypatch.setattr(resource_install_recovery, "ask_resource_recovery", prompt)
    with pytest.raises(MaaUpdateUnsafeError, match="取消"):
        await instance._recover_incomplete_resources()
    prompt.assert_awaited_once()
    assert marker.exists()


@pytest.mark.asyncio
async def test_maa_repair_reuses_verified_full_resource_pipeline(partial, monkeypatch):
    root, marker, instance = partial
    snapshot = marker.read_bytes()
    prompt = AsyncMock(return_value=("retry", snapshot))
    monkeypatch.setattr(resource_install_recovery, "ask_resource_recovery", prompt)
    async def install_resources(root, **kwargs):
        assert kwargs["github"] is True
        assert kwargs["recovery_snapshot"] == snapshot
        marker.unlink()
    monkeypatch.setattr(manager, "prepare_install_resources", install_resources)
    monkeypatch.setattr(
        manager,
        "read_resource_clock",
        lambda path: datetime(2026, 11, 10, tzinfo=timezone.utc),
    )
    await instance._recover_incomplete_resources()
    assert not marker.exists()
    instance.script_info.set_log.assert_awaited()


@pytest.mark.asyncio
async def test_maa_no_takeover_rejects_native_updater_failure(partial, monkeypatch):
    root, marker, instance = partial
    marker.unlink()
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda r: True)
    with pytest.raises(MaaUpdateUnsafeError, match="官方 GUI"):
        await instance._prepare_software_update(object())


@pytest.mark.asyncio
async def test_maa_prompt_without_frontend_keeps_resource_marker(partial, monkeypatch):
    root, marker, _ = partial
    monkeypatch.setattr(
        resource_install_recovery.Publisher,
        "send",
        AsyncMock(return_value=False),
    )
    with pytest.raises(MaaUpdateUnsafeError, match="MAS 主界面"):
        await resource_install_recovery.ask_resource_recovery(
            "task",
            root,
            managed_name="MAA",
            takeover_enabled=False,
        )
    assert marker.exists()
