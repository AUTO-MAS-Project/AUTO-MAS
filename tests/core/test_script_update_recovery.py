"""公共脚本安装恢复状态机：拒绝半安装，允许安全旧版并延后报告。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update
from app.core.script_update_recovery import (
    DownloadRetryFailed,
    InstallInspection,
    InstallReportedFailure,
    InstallTimedOut,
    RecoveryIncident,
    reconcile_installation,
    run_managed_installation,
)
from app.services.script_install import InstallUnsafeError
from app.services.script_install_backup import ManagedInstallBackup


def inspection(
    *,
    pending: bool,
    healthy: bool,
    updated: bool = False,
    previous: bool = False,
) -> InstallInspection:
    return InstallInspection(
        pending=pending,
        healthy=healthy,
        installed_version="1.0.0" if previous else "1.1.0",
        target_version="1.1.0",
        updated_confirmed=updated,
        previous_confirmed=previous,
    )


@pytest.mark.asyncio
async def test_verified_finished_install_is_acknowledged_without_download(tmp_path):
    states = iter(
        [
            inspection(pending=True, healthy=True, updated=True),
            inspection(pending=False, healthy=True, updated=True),
        ]
    )
    events: list[RecoveryIncident] = []
    ack = AsyncMock()
    retry = AsyncMock()
    result = await reconcile_installation(
        script_id="one",
        script_type="SRC",
        install_root=tmp_path,
        inspect=AsyncMock(side_effect=lambda: next(states)),
        acknowledge=ack,
        reinstall=retry,
        report=events.append,
    )
    assert result == "verified"
    ack.assert_awaited_once()
    retry.assert_not_awaited()
    assert events[0].outcome == "verified"


@pytest.mark.asyncio
async def test_retries_only_when_a_pending_install_needs_repair(tmp_path):
    states = iter(
        [
            inspection(pending=True, healthy=False),
            inspection(pending=False, healthy=True),
        ]
    )
    events: list[RecoveryIncident] = []
    retry = AsyncMock()
    result = await reconcile_installation(
        script_id="two",
        script_type="BAAH",
        install_root=tmp_path,
        inspect=AsyncMock(side_effect=lambda: next(states)),
        acknowledge=AsyncMock(),
        reinstall=retry,
        report=events.append,
    )
    assert result == "reinstalled"
    retry.assert_awaited_once()
    assert events[0].outcome == "reinstalled"


@pytest.mark.asyncio
async def test_download_failure_with_trusted_previous_version_can_continue(tmp_path):
    states = iter(
        [
            inspection(pending=True, healthy=False),
            inspection(pending=False, healthy=True, previous=True),
        ]
    )
    events: list[RecoveryIncident] = []
    result = await reconcile_installation(
        script_id="three",
        script_type="MaaEnd",
        install_root=tmp_path,
        inspect=AsyncMock(side_effect=lambda: next(states)),
        acknowledge=AsyncMock(),
        reinstall=AsyncMock(
            side_effect=DownloadRetryFailed(source="GitHub", reason="下载超时")
        ),
        report=events.append,
    )
    assert result == "old_version"
    assert events[0].outcome == "old_version"
    assert events[0].reason == "下载超时"
    assert events[0].installed_version == "1.0.0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pending,healthy,previous",
    [
        (True, True, True),
        (False, True, False),
        (False, False, True),
        (True, False, False),
    ],
)
async def test_download_failure_never_bypasses_unconfirmed_install(
    tmp_path, pending, healthy, previous
):
    states = iter(
        [
            inspection(pending=True, healthy=False),
            inspection(pending=pending, healthy=healthy, previous=previous),
        ]
    )
    events: list[RecoveryIncident] = []
    with pytest.raises(InstallUnsafeError, match="禁止启动"):
        await reconcile_installation(
            script_id="unsafe",
            script_type="BetterGI",
            install_root=tmp_path,
            inspect=AsyncMock(side_effect=lambda: next(states)),
            acknowledge=AsyncMock(),
            reinstall=AsyncMock(
                side_effect=DownloadRetryFailed(source="MirrorChyan", reason="连接失败")
            ),
            report=events.append,
        )
    assert events[0].outcome == "blocked"


@pytest.mark.asyncio
async def test_install_error_does_not_masquerade_as_download_failure(tmp_path):
    events: list[RecoveryIncident] = []
    with pytest.raises(RuntimeError, match="installer failed"):
        await reconcile_installation(
            script_id="unsafe",
            script_type="Whimbox",
            install_root=tmp_path,
            inspect=AsyncMock(return_value=inspection(pending=True, healthy=False)),
            acknowledge=AsyncMock(),
            reinstall=AsyncMock(side_effect=RuntimeError("installer failed")),
            report=events.append,
        )
    assert events[0].outcome == "blocked"


@pytest.mark.asyncio
async def test_cancel_is_not_converted_into_old_version_fallback(tmp_path):
    events: list[RecoveryIncident] = []
    with pytest.raises(asyncio.CancelledError):
        await reconcile_installation(
            script_id="cancel",
            script_type="MAA",
            install_root=tmp_path,
            inspect=AsyncMock(return_value=inspection(pending=True, healthy=False)),
            acknowledge=AsyncMock(),
            reinstall=AsyncMock(side_effect=asyncio.CancelledError()),
            report=events.append,
        )
    assert not events


@pytest.mark.asyncio
async def test_common_entry_attaches_report_and_publishes_at_end(monkeypatch, tmp_path):
    notices = []
    task = SimpleNamespace(
        task_id="task-uuid",
        current=SimpleNamespace(recovery_summary=""),
        commit=AsyncMock(),
    )
    session = object.__new__(script_update.ScriptUpdateSession)
    session._task = task
    session._recovery_events = []
    session._recovery_reported = False

    async def send(*, id, type, data):
        notices.append((id, type, data))
        return True

    monkeypatch.setattr(script_update.Publisher, "send", send)
    token = script_update._current_recovery_session.set(session)
    try:
        states = iter(
            [
                inspection(pending=True, healthy=False),
                inspection(pending=False, healthy=True, previous=True),
            ]
        )
        outcome = await script_update.auto_recover_script_install(
            script_update.ScriptUpdateRequest("script", "SRC"),
            install_root=tmp_path,
            inspect=AsyncMock(side_effect=lambda: next(states)),
            acknowledge=AsyncMock(),
            reinstall=AsyncMock(
                side_effect=DownloadRetryFailed(source="GitHub", reason="下载超时")
            ),
        )
        assert outcome == "old_version"
    finally:
        script_update._current_recovery_session.reset(token)

    assert not notices, "脚本运行中不能提前发公共结算通知"
    await session.publish_recovery_summary()
    await session.publish_recovery_summary()
    assert len(notices) == 1
    assert notices[0][0] == "task-uuid"
    assert notices[0][2].level == "warning"
    assert "下载超时" in notices[0][2].message
    assert "旧版" in task.current.recovery_summary
    task.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_download_failure_uses_verified_previous_and_defers_notice(
    monkeypatch, tmp_path
):
    reports = []
    session = object.__new__(script_update.ScriptUpdateSession)
    session.record_recovery = reports.append
    token = script_update._current_recovery_session.set(session)
    try:

        async def download():
            raise DownloadRetryFailed(source="GitHub", reason="连接超时")

        result = await script_update.run_script_update_with_safe_fallback(
            script_update.ScriptUpdateRequest("bgi-one", "BetterGI"),
            download,
            tmp_path,
            AsyncMock(
                return_value=inspection(pending=False, healthy=True, previous=True)
            ),
        )
        assert "继续任务" in result
        assert len(reports) == 1 and reports[0].outcome == "old_version"
    finally:
        script_update._current_recovery_session.reset(token)


@pytest.mark.asyncio
async def test_normal_download_failure_never_bypasses_pending_marker(tmp_path):
    reports = []
    session = object.__new__(script_update.ScriptUpdateSession)
    session.record_recovery = reports.append
    token = script_update._current_recovery_session.set(session)
    try:

        async def download():
            raise DownloadRetryFailed(source="GitHub", reason="连接超时")

        with pytest.raises(DownloadRetryFailed):
            await script_update.run_script_update_with_safe_fallback(
                script_update.ScriptUpdateRequest("bgi-two", "BetterGI"),
                download,
                tmp_path,
                AsyncMock(
                    return_value=inspection(pending=True, healthy=True, previous=True)
                ),
            )
        assert reports[0].outcome == "blocked"
    finally:
        script_update._current_recovery_session.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["initial", "acknowledge", "recheck", "post_retry"])
async def test_recovery_check_exceptions_are_reported(tmp_path, failure):
    events = []
    if failure == "initial":
        check = AsyncMock(side_effect=OSError("read failed"))
        acknowledge = AsyncMock()
        reinstall = AsyncMock()
    elif failure in {"acknowledge", "recheck"}:
        checks = [
            inspection(pending=True, healthy=True, updated=True),
            inspection(pending=False, healthy=True, updated=True),
        ]
        check = AsyncMock(
            side_effect=checks
            if failure == "acknowledge"
            else [checks[0], OSError("recheck failed")]
        )
        acknowledge = AsyncMock(
            side_effect=OSError("journal moved") if failure == "acknowledge" else None
        )
        reinstall = AsyncMock()
    else:
        check = AsyncMock(
            side_effect=[
                inspection(pending=True, healthy=False),
                OSError("verify failed"),
            ]
        )
        acknowledge = AsyncMock()
        reinstall = AsyncMock()
    with pytest.raises(OSError):
        await reconcile_installation(
            script_id="test",
            script_type="BetterGI",
            install_root=tmp_path,
            inspect=check,
            acknowledge=acknowledge,
            reinstall=reinstall,
            report=events.append,
        )
    assert len(events) == 1
    assert events[0].outcome == "blocked"


@pytest.mark.asyncio
async def test_install_backup_is_persistent_and_cleaned_only_after_success(tmp_path):
    root = tmp_path / "BetterGI"
    root.mkdir()
    (root / "program.exe").write_bytes(b"old-good-program")
    backup = ManagedInstallBackup(root, script_id="one", script_type="BetterGI")
    await backup.create("1.0.0")
    assert backup.snapshot.joinpath("program.exe").read_bytes() == b"old-good-program"
    assert backup.read()["phase"] == "ready"
    backup.set_phase("installing")
    (root / "program.exe").write_bytes(b"new-good-program")
    await backup.finish_success()
    assert (root / "program.exe").read_bytes() == b"new-good-program"
    assert not backup.record.exists()
    assert not backup.snapshot.exists()


@pytest.mark.asyncio
async def test_installer_reported_failure_rolls_back_and_continues(tmp_path):
    root = tmp_path / "BetterGI"
    root.mkdir()
    exe = root / "program.exe"
    exe.write_bytes(b"old-good-program")
    events = []

    async def inspect():
        version = exe.read_bytes()
        return InstallInspection(
            pending=False,
            healthy=version in {b"old-good-program", b"new-good-program"},
            installed_version="1.0.0" if version == b"old-good-program" else "1.1.0",
            updated_confirmed=version == b"new-good-program",
            previous_confirmed=version == b"old-good-program",
        )

    async def install():
        exe.write_bytes(b"corrupt")
        raise InstallReportedFailure("installer exited 1")

    result = await run_managed_installation(
        script_id="one",
        script_type="BetterGI",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=install,
        ensure_idle=AsyncMock(),
        after_rollback=AsyncMock(),
        report=events.append,
    )
    assert result == "old_version"
    assert exe.read_bytes() == b"old-good-program"
    assert not ManagedInstallBackup(
        root, script_id="one", script_type="BetterGI"
    ).record.exists()
    assert events[-1].outcome == "old_version"


@pytest.mark.asyncio
async def test_timeout_keeps_backup_until_next_run_then_retries_and_rolls_back(
    tmp_path,
):
    root = tmp_path / "MAA"
    root.mkdir()
    exe = root / "program.exe"
    exe.write_bytes(b"old-good")
    events = []
    install_count = 0

    async def inspect():
        blob = exe.read_bytes()
        return InstallInspection(
            pending=blob == b"pending",
            healthy=blob in {b"old-good", b"new-good"},
            installed_version="1.0.0" if blob == b"old-good" else "1.1.0",
            updated_confirmed=blob == b"new-good",
            previous_confirmed=blob == b"old-good",
        )

    async def install():
        nonlocal install_count
        install_count += 1
        if install_count == 1:
            exe.write_bytes(b"pending")
            raise InstallTimedOut("installer timed out")
        raise DownloadRetryFailed(source="GitHub", reason="network timed out again")

    args = dict(
        script_id="one",
        script_type="MAA",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=install,
        ensure_idle=AsyncMock(),
        after_rollback=AsyncMock(),
        report=events.append,
    )
    with pytest.raises(InstallUnsafeError, match="下一次运行"):
        await run_managed_installation(**args)
    backup = ManagedInstallBackup(root, script_id="one", script_type="MAA")
    assert backup.read()["phase"] == "timed_out"
    assert exe.read_bytes() == b"pending"
    assert events[-1].outcome == "deferred"
    assert await run_managed_installation(**args) == "old_version"
    assert exe.read_bytes() == b"old-good"
    assert not backup.record.exists()
    assert install_count == 2
    assert events[-1].source == "GitHub"
    assert "再次下载失败" in events[-1].reason


@pytest.mark.asyncio
async def test_timeout_next_run_accepts_verified_success_without_retry(tmp_path):
    root = tmp_path / "SRC"
    root.mkdir()
    exe = root / "program.exe"
    exe.write_bytes(b"old-good")
    events = []
    install = AsyncMock(side_effect=InstallTimedOut("time exceeded"))

    async def inspect():
        blob = exe.read_bytes()
        return InstallInspection(
            pending=blob == b"pending",
            healthy=blob in {b"old-good", b"new-good"},
            installed_version="1.1.0" if blob == b"new-good" else "1.0.0",
            updated_confirmed=blob == b"new-good",
            previous_confirmed=blob == b"old-good",
        )

    args = dict(
        script_id="one",
        script_type="SRC",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=install,
        ensure_idle=AsyncMock(),
        after_rollback=AsyncMock(),
        report=events.append,
    )
    with pytest.raises(InstallUnsafeError):
        await run_managed_installation(**args)
    exe.write_bytes(b"new-good")
    assert await run_managed_installation(**args) == "verified"
    assert install.await_count == 1
    assert events[-1].outcome == "verified"


@pytest.mark.asyncio
async def test_uncertain_installer_does_not_rollback_while_still_running(tmp_path):
    root = tmp_path / "BAAH"
    root.mkdir()
    exe = root / "program.exe"
    exe.write_bytes(b"old-good")
    active = False
    events = []

    async def inspect():
        blob = exe.read_bytes()
        return InstallInspection(
            pending=blob != b"old-good",
            healthy=blob == b"old-good",
            installed_version="1.0.0",
            previous_confirmed=blob == b"old-good",
        )

    async def install():
        nonlocal active
        active = True
        exe.write_bytes(b"not-finished")
        raise InstallReportedFailure("installer failed")

    async def ensure_idle():
        if active:
            raise InstallUnsafeError("installer is still writing")

    args = dict(
        script_id="one",
        script_type="BAAH",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=install,
        ensure_idle=ensure_idle,
        after_rollback=AsyncMock(),
        report=events.append,
    )
    with pytest.raises(InstallUnsafeError, match="still writing"):
        await run_managed_installation(**args)
    assert exe.read_bytes() == b"not-finished"
    assert events[-1].outcome == "blocked"
    assert ManagedInstallBackup(
        root, script_id="one", script_type="BAAH"
    ).record.exists()


@pytest.mark.asyncio
async def test_repeated_download_failure_is_only_notified_after_queue_completion(
    monkeypatch, tmp_path
):
    events = [
        RecoveryIncident(
            script_id="bgi-one",
            script_type="BetterGI",
            install_root=str(tmp_path),
            outcome="old_version",
            installed_version="1.0.0",
            source="GitHub",
            reason="恢复时再次下载失败：连接超时；已从更新前备份恢复旧版",
        )
    ]
    task = SimpleNamespace(
        task_id="task-done",
        current=SimpleNamespace(recovery_summary=""),
        commit=AsyncMock(),
    )
    session = object.__new__(script_update.ScriptUpdateSession)
    session._task = task
    session._recovery_events = events
    session._recovery_reported = False
    notices = []
    monkeypatch.setattr(
        script_update.Publisher,
        "send",
        AsyncMock(side_effect=lambda **kwargs: notices.append(kwargs)),
    )
    assert not notices
    await session.publish_recovery_summary()
    assert len(notices) == 1
    assert "再次下载失败" in notices[0]["data"].message
    assert "GitHub" in notices[0]["data"].message
    assert "旧版" in task.current.recovery_summary
    assert notices[0]["data"].level == "warning"


@pytest.mark.asyncio
async def test_install_snapshot_recovers_across_different_profiles(tmp_path):
    root = tmp_path / "shared-BetterGI"
    root.mkdir()
    (root / "program.exe").write_bytes(b"before")
    first = ManagedInstallBackup(root, script_id="profile-one", script_type="BetterGI")
    await first.create("1.0.0")
    second = ManagedInstallBackup(root, script_id="profile-two", script_type="BetterGI")
    assert second.read()["script_id"] == "profile-one"
    assert second.read()["files"]["program.exe"]
    other_type = ManagedInstallBackup(root, script_id="profile-two", script_type="MAA")
    with pytest.raises(InstallUnsafeError, match="身份变化"):
        other_type.read()


@pytest.mark.asyncio
async def test_restore_journal_can_finish_after_crash_during_directory_swap(tmp_path):
    root = tmp_path / "script"
    root.mkdir()
    (root / "bin").write_bytes(b"old")
    backup = ManagedInstallBackup(root, script_id="one", script_type="SRC")
    await backup.create("1.0.0")
    backup.set_phase("installing")
    (root / "bin").write_bytes(b"broken")
    backup.set_phase("restoring")
    root.replace(backup.failed)
    backup.snapshot.replace(root)
    reinstall = AsyncMock()

    async def inspect():
        return InstallInspection(
            pending=False,
            healthy=True,
            installed_version="1.0.0",
            previous_confirmed=True,
        )

    events = []
    result = await run_managed_installation(
        script_id="one",
        script_type="SRC",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=reinstall,
        ensure_idle=AsyncMock(),
        after_rollback=AsyncMock(),
        report=events.append,
    )
    assert result == "old_version"
    reinstall.assert_not_awaited()
    assert (root / "bin").read_bytes() == b"old"
    assert not backup.record.exists()


@pytest.mark.asyncio
async def test_corrupt_backup_does_not_overwrite_current_install(tmp_path):
    root = tmp_path / "script"
    root.mkdir()
    (root / "bin").write_bytes(b"old")
    backup = ManagedInstallBackup(root, script_id="one", script_type="MAA")
    await backup.create("1.0.0")
    backup.set_phase("installing")
    (root / "bin").write_bytes(b"broken-install")
    (backup.snapshot / "bin").write_bytes(b"tampered-backup")
    with pytest.raises(InstallUnsafeError, match="备份文件不完整"):
        await backup.restore()
    assert (root / "bin").read_bytes() == b"broken-install"
    assert backup.record.exists()


@pytest.mark.asyncio
async def test_new_public_entry_reports_only_through_current_session(tmp_path):
    root = tmp_path / "script"
    root.mkdir()
    exe = root / "bin"
    exe.write_bytes(b"old")
    incidents = []
    session = object.__new__(script_update.ScriptUpdateSession)
    session.record_recovery = incidents.append
    token = script_update._current_recovery_session.set(session)

    async def inspect():
        updated = exe.read_bytes() == b"new"
        return InstallInspection(
            pending=False,
            healthy=True,
            installed_version="1.1.0" if updated else "1.0.0",
            updated_confirmed=updated,
            previous_confirmed=not updated,
        )

    async def install():
        exe.write_bytes(b"new")

    try:
        result = await script_update.run_managed_script_install(
            script_update.ScriptUpdateRequest("one", "MAA"),
            install_root=root,
            inspect=inspect,
            acknowledge=AsyncMock(),
            install=install,
            ensure_idle=AsyncMock(),
            after_rollback=AsyncMock(),
        )
    finally:
        script_update._current_recovery_session.reset(token)
    assert result == "installed"
    assert len(incidents) == 1
    assert incidents[0].outcome == "installed"
    assert not ManagedInstallBackup(
        root, script_id="one", script_type="MAA"
    ).record.exists()
