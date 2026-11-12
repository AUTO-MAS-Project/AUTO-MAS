"""MAA 官方本体失败与资源半更新：统一自动恢复且保持 fail-closed。"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import script_install
from app.task.MAA import manager
from app.task.MAA.tools import install_recovery as recovery
from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError


@pytest.fixture
def maa_root(tmp_path, monkeypatch):
    root = tmp_path / "maa"
    (root / "config").mkdir(parents=True)
    # 真实 PE 头：MZ -> e_lfanew=64 -> PE\0\0 + Machine=x64。
    executable = bytearray(128)
    executable[:2] = b"MZ"
    executable[60:64] = (64).to_bytes(4, "little")
    executable[64:70] = b"PE\x00\x00\x64\x86"
    (root / "MAA.exe").write_bytes(executable)
    (root / "MAA.dll").touch()
    monkeypatch.setattr(
        recovery,
        "read_installed_release",
        lambda root: ("v6.2.0", "x64"),
    )
    monkeypatch.setattr(
        recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(recovery, "read_pending_update", lambda root: ("", ""))
    monkeypatch.setattr(
        recovery.process, "is_process_running", AsyncMock(return_value=False)
    )
    return root


@pytest.mark.asyncio
async def test_manual_repair_can_acknowledge_old_official_failure(maa_root):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official install failed")
    version = await recovery.skip_delegated_failure(
        maa_root, {"software": flag.read_bytes()}
    )
    assert version == "v6.2.0"
    assert not flag.exists()
    backup = list(script_install.workspace(maa_root).glob("maa-failure-ack-*.txt"))
    assert len(backup) == 1
    assert backup[0].read_bytes() == b"official install failed"


@pytest.mark.asyncio
async def test_resource_write_can_never_be_skipped(maa_root):
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target": "2026-11-10T01:00:00+00:00"}')
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"failure")
    with pytest.raises(MaaUpdateUnsafeError, match="只能跳过"):
        await recovery.skip_delegated_failure(
            maa_root,
            {"software": flag.read_bytes(), "resource": resource.read_bytes()},
        )
    assert resource.exists()
    assert flag.exists()


@pytest.mark.asyncio
async def test_install_corrupted_or_pending_package_never_skips(maa_root, monkeypatch):
    flag = maa_root / "pending-update-failure.txt"
    flag.touch()
    snapshot = {"software": flag.read_bytes()}
    (maa_root / "MAA.dll").unlink()
    with pytest.raises(MaaUpdateUnsafeError, match="核心程序集"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    (maa_root / "MAA.dll").touch()
    (maa_root / "pending.zip").touch()
    monkeypatch.setattr(
        recovery, "read_pending_update", lambda root: ("v6.3.0", "pending.zip")
    )
    with pytest.raises(MaaUpdateUnsafeError, match="待安装"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    assert flag.exists()


@pytest.mark.asyncio
async def test_updater_running_or_marker_changed_never_skips(maa_root):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"old")
    snapshot = {"software": flag.read_bytes()}
    flag.write_bytes(b"new")
    with pytest.raises(MaaUpdateUnsafeError, match="变化"):
        await recovery.skip_delegated_failure(maa_root, snapshot)
    assert flag.read_bytes() == b"new"
    recovery.process.is_process_running.return_value = True
    with pytest.raises(MaaUpdateUnsafeError, match="仍在写盘"):
        await recovery.skip_delegated_failure(maa_root, {"software": flag.read_bytes()})
    assert flag.exists()


@pytest.mark.asyncio
async def test_maa_managed_recovery_does_not_depend_on_frontend(maa_root, monkeypatch):
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"native installer failed")
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    state = await adapter.inspect()
    assert state.pending
    assert not state.updated_confirmed
    assert flag.exists()


@pytest.mark.asyncio
async def test_maa_manager_resource_recovery_goes_through_common_entry(
    maa_root, monkeypatch
):
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target":"2026-10-01T00:00:00+00:00"}')
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(
        name="MAA", script_id="test-script", set_log=AsyncMock()
    )
    instance.task_info = SimpleNamespace(task_id="task")
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=False, MirrorChyanCDK="")
    )
    instance._maa_update_checked = False
    common = AsyncMock(return_value="reinstalled")
    monkeypatch.setattr(manager, "auto_recover_script_install", common)
    await instance._recover_unconfirmed_update()
    common.assert_awaited_once()
    assert instance._maa_update_checked
    instance.script_info.set_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_maa_corrupted_executable_blocks_manual_acknowledge(
    maa_root, monkeypatch
):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official error")
    (maa_root / "MAA.exe").write_bytes(b"")
    with pytest.raises(MaaUpdateUnsafeError, match="PE 架构"):
        await recovery.skip_delegated_failure(maa_root, {"software": flag.read_bytes()})
    assert flag.read_bytes() == b"official error"


@pytest.mark.asyncio
async def test_maa_missing_executable_never_becomes_healthy(maa_root, monkeypatch):
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official error")
    (maa_root / "MAA.exe").unlink()
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    state = await adapter.inspect()
    assert state.pending and not state.healthy
    assert flag.exists()


@pytest.mark.asyncio
async def test_native_failure_marker_with_package_does_not_fake_automatic_retry(
    maa_root, monkeypatch
):
    """真实公共入口必须在原生启动前阻断无效重试，保留原始失败现场。"""
    from app.task.MAA.tools import managed_recovery

    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official updater failed")
    package = maa_root / "pending.zip"
    package.write_bytes(b"official archive")
    monkeypatch.setattr(
        managed_recovery, "read_pending_update", lambda root: ("v6.3.0", "pending.zip")
    )
    monkeypatch.setattr(
        managed_recovery, "read_installed_release", lambda root: ("v6.2.0", "x64")
    )
    monkeypatch.setattr(
        managed_recovery,
        "read_resource_clock",
        lambda root: datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(script_id="test-script", set_log=AsyncMock())
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(MirrorChyanCDK="", TakeoverEnabled=True)
    )
    instance._maa_update_checked = False
    native = AsyncMock()
    monkeypatch.setattr(instance, "_install_pending_software_update", native)
    with pytest.raises(MaaUpdateUnsafeError, match="官方界面"):
        await instance._recover_unconfirmed_update()
    native.assert_not_awaited()
    assert flag.read_bytes() == b"official updater failed"
    assert package.read_bytes() == b"official archive"
    assert not instance._maa_update_checked


@pytest.mark.asyncio
async def test_resource_failure_without_official_marker_keeps_automatic_repair(
    maa_root, monkeypatch
):
    from app.task.MAA.tools import managed_recovery

    resource = maa_root / ".automas-resource-update.json"
    resource.write_bytes(b'{"target": "2026-11-10T00:00:00+00:00"}')
    adapter = managed_recovery.MAAInstallAdapter(maa_root)
    called = AsyncMock()

    async def prepared():
        resource.unlink()

    called.side_effect = prepared
    monkeypatch.setattr(
        managed_recovery,
        "verify_resource_recovery_marker",
        lambda root, snapshot: None,
    )
    monkeypatch.setattr(
        managed_recovery,
        "has_incomplete_resource_update",
        lambda root: resource.exists(),
    )
    await adapter.reinstall(called)
    called.assert_awaited_once()
    assert not resource.exists()
