"""MAA 官方安装失败与中断资源合并：用户恢复选择必须显式且 fail-closed。"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Dispatcher
from app.core.ws import protocol
from app.models.schema import WSEnvelope
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
async def test_unattended_maaupdate_does_not_clear_failure(maa_root, monkeypatch):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"MAA repair failed")
    monkeypatch.setattr(recovery.Publisher, "send", AsyncMock(return_value=False))
    with pytest.raises(MaaUpdateUnsafeError, match="主界面"):
        await recovery.ask_maa_recovery(
            "task", maa_root, managed_name="MAA 定时托管", takeover_enabled=False
        )
    assert flag.read_bytes() == b"MAA repair failed"


@pytest.mark.asyncio
async def test_prompt_shows_correct_installation_and_software_actions(
    maa_root, monkeypatch
):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"failure")
    shown = []

    async def send(*, id, type, data):
        if type == protocol.MAA_INSTALL_PROMPT:
            shown.append(data)
            Dispatcher.dispatch(
                WSEnvelope(
                    id=id,
                    type=protocol.MAA_INSTALL_DECISION,
                    data={
                        "taskId": data["taskId"],
                        "requestId": data["requestId"],
                        "action": "stop",
                    },
                )
            )
        return True

    monkeypatch.setattr(recovery.Publisher, "send", send)
    with pytest.raises(MaaUpdateUnsafeError, match="取消"):
        await recovery.ask_maa_recovery(
            "task", maa_root, managed_name="测试专用 MAA", takeover_enabled=False
        )
    assert shown[0]["managedName"] == "测试专用 MAA"
    assert shown[0]["installPath"] == str(maa_root.resolve())
    assert shown[0]["canSkip"] is True
    assert shown[0]["canRetry"] is False
    assert flag.exists()


@pytest.mark.asyncio
async def test_maa_resource_only_prompt_forbids_skip(maa_root, monkeypatch):
    flag = maa_root / ".automas-resource-update.json"
    flag.write_text("{}")
    monkeypatch.setattr(recovery.Publisher, "send", AsyncMock(return_value=True))
    monkeypatch.setattr(recovery, "_PROMPT_TIMEOUT", 0.003)
    with pytest.raises(MaaUpdateUnsafeError, match="超时"):
        await recovery.ask_maa_recovery(
            "task", maa_root, managed_name="MAA", takeover_enabled=False
        )
    assert flag.exists()


@pytest.mark.asyncio
async def test_manager_can_repair_resource_when_takeover_disabled(
    maa_root, monkeypatch
):
    resource = maa_root / ".automas-resource-update.json"
    resource.write_text('{"target":"2026-10-01T00:00:00+00:00"}')
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = maa_root / "config"
    instance.script_info = SimpleNamespace(name="MAA", set_log=AsyncMock())
    instance.task_info = SimpleNamespace(task_id="task")
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=False, MirrorChyanCDK="")
    )
    instance._maa_update_checked = False
    monkeypatch.setattr(
        recovery,
        "ask_maa_recovery",
        AsyncMock(return_value=("retry", {"resource": resource.read_bytes()})),
    )
    monkeypatch.setattr(manager, "resolve_takeover_cdk", lambda cdk: "")
    called = []

    async def repair(root, **kwargs):
        called.append(kwargs)
        resource.unlink()

    monkeypatch.setattr(manager, "prepare_install_resources", repair)
    await instance._recover_unconfirmed_update()
    assert called == [{"cdk": None, "github": True}]
    assert instance._maa_update_checked is True
    instance.script_info.set_log.assert_awaited_once()
    assert not resource.exists()


@pytest.mark.asyncio
async def test_maa_stop_on_change_during_prompt(maa_root, monkeypatch):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"original")

    async def send(*, id, type, data):
        if type == protocol.MAA_INSTALL_PROMPT:
            flag.write_bytes(b"other install failure")
            Dispatcher.dispatch(
                WSEnvelope(
                    id=id,
                    type=protocol.MAA_INSTALL_DECISION,
                    data={
                        "taskId": data["taskId"],
                        "requestId": data["requestId"],
                        "action": "skip",
                    },
                )
            )
        return True

    monkeypatch.setattr(recovery.Publisher, "send", send)
    with pytest.raises(MaaUpdateUnsafeError, match="变化"):
        await recovery.ask_maa_recovery(
            "task", maa_root, managed_name="MAA", takeover_enabled=True
        )
    assert flag.read_bytes() == b"other install failure"


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
async def test_maa_missing_exe_disallows_native_retry_even_with_pending_zip(
    maa_root, monkeypatch
):
    flag = maa_root / "pending-update-failure.txt"
    flag.write_bytes(b"official error")
    (maa_root / "MAA.exe").unlink()
    (maa_root / "pending.zip").write_bytes(b"archive")
    monkeypatch.setattr(
        recovery, "read_pending_update", lambda root: ("v6.3.0", "pending.zip")
    )
    shown = []

    async def send(*, id, type, data):
        if type == protocol.MAA_INSTALL_PROMPT:
            shown.append(data)
            Dispatcher.dispatch(
                WSEnvelope(
                    id=id,
                    type=protocol.MAA_INSTALL_DECISION,
                    data={
                        "taskId": data["taskId"],
                        "requestId": data["requestId"],
                        "action": "stop",
                    },
                )
            )
        return True

    monkeypatch.setattr(recovery.Publisher, "send", send)
    with pytest.raises(MaaUpdateUnsafeError, match="取消"):
        await recovery.ask_maa_recovery(
            "task", maa_root, managed_name="MAA", takeover_enabled=True
        )
    assert shown[0]["canRetry"] is False
    assert flag.exists()
