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
    RecoveryIncident,
    reconcile_installation,
)
from app.services.script_install import InstallUnsafeError


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
        [inspection(pending=True, healthy=True, updated=True),
         inspection(pending=False, healthy=True, updated=True)]
    )
    events: list[RecoveryIncident] = []
    ack = AsyncMock()
    retry = AsyncMock()
    result = await reconcile_installation(
        script_id="one", script_type="SRC", install_root=tmp_path,
        inspect=AsyncMock(side_effect=lambda: next(states)),
        acknowledge=ack, reinstall=retry, report=events.append,
    )
    assert result == "verified"
    ack.assert_awaited_once()
    retry.assert_not_awaited()
    assert events[0].outcome == "verified"


@pytest.mark.asyncio
async def test_retries_only_when_a_pending_install_needs_repair(tmp_path):
    states = iter(
        [inspection(pending=True, healthy=False),
         inspection(pending=False, healthy=True)]
    )
    events: list[RecoveryIncident] = []
    retry = AsyncMock()
    result = await reconcile_installation(
        script_id="two", script_type="BAAH", install_root=tmp_path,
        inspect=AsyncMock(side_effect=lambda: next(states)),
        acknowledge=AsyncMock(), reinstall=retry, report=events.append,
    )
    assert result == "reinstalled"
    retry.assert_awaited_once()
    assert events[0].outcome == "reinstalled"


@pytest.mark.asyncio
async def test_download_failure_with_trusted_previous_version_can_continue(tmp_path):
    states = iter(
        [inspection(pending=True, healthy=False),
         inspection(pending=False, healthy=True, previous=True)]
    )
    events: list[RecoveryIncident] = []
    result = await reconcile_installation(
        script_id="three", script_type="MaaEnd", install_root=tmp_path,
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
@pytest.mark.parametrize("pending,healthy,previous", [
    (True, True, True),
    (False, True, False),
    (False, False, True),
    (True, False, False),
])
async def test_download_failure_never_bypasses_unconfirmed_install(
    tmp_path, pending, healthy, previous
):
    states = iter(
        [inspection(pending=True, healthy=False),
         inspection(pending=pending, healthy=healthy, previous=previous)]
    )
    events: list[RecoveryIncident] = []
    with pytest.raises(InstallUnsafeError, match="禁止启动"):
        await reconcile_installation(
            script_id="unsafe", script_type="BetterGI", install_root=tmp_path,
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
            script_id="unsafe", script_type="Whimbox", install_root=tmp_path,
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
            script_id="cancel", script_type="MAA", install_root=tmp_path,
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
        current=SimpleNamespace(log="original log\n"),
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
            [inspection(pending=True, healthy=False),
             inspection(pending=False, healthy=True, previous=True)]
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
    assert "旧版" in task.current.log
    task.commit.assert_awaited_once()
