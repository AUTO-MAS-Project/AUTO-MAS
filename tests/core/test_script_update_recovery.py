"""公共脚本安装恢复状态机：拒绝半安装，允许安全旧版并延后报告。"""

import asyncio
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
from app.task import script_update as task_updates


def inspection(
    *,
    pending: bool,
    healthy: bool,
    updated: bool = False,
    previous: bool = False,
) -> InstallInspection:
    """按测试指定的待完成、健康和版本确认状态构造公共安装检查结果。"""
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
    """验证已确认更新成功的安装直接结算恢复，不再重复下载。"""
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
    """验证只有未完成安装需要修复时才重试安装，健康安装不会多做修复。"""
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
    """验证重下载失败后仅在旧版已可靠确认时允许继续使用旧版。"""
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
    """验证下载失败不能绕过未确认安装状态并启动脚本。"""
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
    """验证安装错误保持其原本含义，不被错误归为可回退的网络下载失败。"""
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
    """验证用户取消原样传播，不会被当作下载故障而继续旧版任务。"""
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
    """验证公共恢复入口把事件绑定到当前任务，在任务结束时统一发布报告。"""
    notices = []
    task = SimpleNamespace(
        task_id="task-uuid",
        current=SimpleNamespace(recovery_summary=""),
        commit=AsyncMock(),
    )
    session = task_updates.ScriptRecoverySession(task)

    async def send(*, id, type, data):
        """收集发布目标、消息类型和内容，供断言恢复报告的归属与时机。"""
        notices.append((id, type, data))
        return True

    monkeypatch.setattr(task_updates.Publisher, "send", send)
    with session.bind():
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
@pytest.mark.parametrize("failure", ["initial", "acknowledge", "recheck", "post_retry"])
async def test_recovery_check_exceptions_are_reported(tmp_path, failure):
    """验证安装检查发生异常时生成恢复事件，错误不会静默丢失。"""
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
async def test_repeated_download_failure_is_only_notified_after_queue_completion(
    monkeypatch, tmp_path
):
    """验证重复下载失败在队列结束后统一通知，避免每次重试产生独立提示。"""
    events = [
        RecoveryIncident(
            script_id="bgi-one",
            script_type="BetterGI",
            install_root=str(tmp_path),
            outcome="old_version",
            installed_version="1.0.0",
            source="GitHub",
            reason="恢复时再次下载失败：连接超时；旧版已验证可用",
        )
    ]
    task = SimpleNamespace(
        task_id="task-done",
        current=SimpleNamespace(recovery_summary=""),
        commit=AsyncMock(),
    )
    session = task_updates.ScriptRecoverySession(task)
    for event in events:
        session.record_recovery(event)
    notices = []
    monkeypatch.setattr(
        task_updates.Publisher,
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
