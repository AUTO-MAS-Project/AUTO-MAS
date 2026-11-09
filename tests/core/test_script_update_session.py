"""预下载在真实运行树中交接，进度独立于脚本日志与日志序号。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core import Publisher, script_update
from app.core import script_update_queue as update_queue
from app.core.script_update import ScriptUpdateSession
from app.core.script_update_queue import (
    report_script_task_completed,
    report_script_task_retrying,
    script_task_completed,
    script_task_retrying,
)
from app.core.task_manager import _TaskManager
from app.core.update import download_observer
from app.core.ws import protocol
from app.models.config import MaaConfig
from app.models.config.setting import GlobalConfig
from app.models.task import TaskScriptItem, TaskUserItem, WSTaskPrefetchData
from app.task.legacy import LegacyCallbacks
from app.task.script_expander import ScriptExpander
from tests.config_support import activate_config
from tests.runtime_support import create_runtime_tree


async def setup_session(monkeypatch):
    uid = uuid4()
    root, script, user = await create_runtime_tree(script_id=str(uid))
    config = await activate_config(MaaConfig.build())
    setting = await activate_config(GlobalConfig.build())
    manager = SimpleNamespace(
        prefetch_script_update=AsyncMock(),
        discard_prefetched_update=AsyncMock(),
        callbacks=LegacyCallbacks(),
    )
    host = SimpleNamespace(ScriptConfig={uid: config}, setting=setting)
    session = ScriptUpdateSession(root, make_manager=lambda _: manager, config=host)
    registry = _TaskManager()
    registry._running[root.uid] = ScriptExpander(root, registry)
    monkeypatch.setattr("app.core.task_manager.TaskManager", registry)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    return session, root, script, config, manager, registry, sent


@pytest.mark.asyncio
async def test_progress_snapshot_and_clear_preserve_large_log_increment(monkeypatch):
    session, root, script, config, manager, registry, sent = await setup_session(
        monkeypatch
    )
    await script.set_log("x" * 200_010 + "\n")
    baseline = root.get_log_snapshot()["logSeq"]
    sent.reset_mock()
    progress = WSTaskPrefetchData(target="MaaEnd", method="FluxDown", progress="50%")
    await session._set_progress("downloading", progress)
    snapshot = registry.get_runtime_snapshot().tasks[0]
    assert snapshot.task.current.prefetch == progress
    assert snapshot.logSeq == baseline
    assert snapshot.log == script.current.log
    await script.append_log("next\n")
    await session._set_progress("")
    logs = [
        c.kwargs["data"]
        for c in sent.await_args_list
        if c.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]
    assert len(logs) == 1 and logs[0].append and logs[0].log == "next\n"
    assert root.current.prefetch is None
    assert root.get_log_snapshot()["logSeq"] == baseline + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [False, True])
async def test_candidate_handoff_checks_current_policy_and_releases_lock(
    monkeypatch, change
):
    session, root, script, config, manager, _, _ = await setup_session(monkeypatch)

    async def prepare():
        assert config.is_locked
        observer = download_observer.get()
        observer(script_update.Path("package.zip"), 1, 2, 3)

    manager.prefetch_script_update.side_effect = prepare
    await session._prefetch(0)
    assert not config.is_locked
    assert root.current.prefetch is not None
    assert "完成" in root.current.prefetch.status
    if change:
        config.Update.TakeoverEnabled = not config.Update.TakeoverEnabled
        await config.commit()
    assert (await session.take(script.uid)) is (None if change else manager)
    assert root.current.prefetch is None
    assert manager.discard_prefetched_update.await_count == int(change)
    await session.close()
    await manager.callbacks.close()


@pytest.mark.asyncio
async def test_cancel_waits_for_download_cleanup_before_releasing_config(monkeypatch):
    session, root, script, config, manager, _, _ = await setup_session(monkeypatch)
    started, release = asyncio.Event(), asyncio.Event()

    async def prepare():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await release.wait()
            assert config.is_locked

    manager.prefetch_script_update.side_effect = prepare
    worker = asyncio.create_task(session._prefetch(0))
    await started.wait()
    worker.cancel()
    await asyncio.sleep(0)
    assert not worker.done() and config.is_locked
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await worker
    assert not config.is_locked
    assert download_observer.get() is None
    manager.discard_prefetched_update.assert_awaited_once()
    await session.close()
    assert root.current.prefetch is None


@pytest.mark.asyncio
async def test_other_task_holding_target_lock_skips_prefetch(monkeypatch):
    session, root, _, config, manager, _, _ = await setup_session(monkeypatch)
    ticket = await config.lock_x(cascade=False)
    try:
        await session._prefetch(0)
        manager.prefetch_script_update.assert_not_awaited()
        assert root.current.prefetch is None
    finally:
        await config.unlock(ticket)
        await manager.callbacks.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_boundary", ["maa", "maafw"])
async def test_real_session_retry_stops_download_before_relogin_and_restarts_clock(
    monkeypatch, retry_boundary
):
    """首次成功 -> 预下载 -> MAA 重登边界 -> 停写确认 -> 重新成功计时。"""
    session, root, current, config, _, _, _ = await setup_session(monkeypatch)
    next_uid = uuid4()
    next_run = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": str(next_uid), "name": "Next"}}
    )
    await root.scripts.commit()
    following = root.scripts[next_run]
    following.users.add(
        TaskUserItem, payload={"info": {"user_id": str(uuid4()), "name": "User"}}
    )
    await following.users.commit()
    session._config.ScriptConfig[next_uid] = config
    await current.set_state(status="运行")

    monkeypatch.setattr(update_queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(update_queue, "PREFETCH_POLL_SECONDS", 0.001)
    first_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    second_started = asyncio.Event()
    attempts = 0
    managers = []

    async def download():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            first_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await allow_cleanup.wait()
        else:
            second_started.set()

    def make_manager(_item):
        manager = SimpleNamespace(
            prefetch_script_update=download,
            discard_prefetched_update=AsyncMock(),
            callbacks=LegacyCallbacks(),
        )
        managers.append(manager)
        return manager

    session._make_manager = make_manager
    completed_token = script_task_completed.set(session.mark_completed)
    retry_token = script_task_retrying.set(lambda: session.retry(current, 1))
    retry_task = None
    client_closed = asyncio.Event()
    try:
        session.watch(current, 1)
        report_script_task_completed()
        await asyncio.wait_for(first_started.wait(), 2)
        assert config.is_locked
        assert session._completed_at is not None

        if retry_boundary == "maafw":
            from app.task.MaaFW.tools.embedded.runner_task import (
                MaaFWPluginAutoProxyTask,
            )

            runner = object.__new__(MaaFWPluginAutoProxyTask)
            runner.script_config = SimpleNamespace(Run=SimpleNamespace(RunTimesLimit=3))
            runner._extra_attempts = 0
            runner.opened_game = True
            runner.opened_emulator = False
            runner._append_log = lambda _text: None

            async def close_game():
                client_closed.set()
                runner.opened_game = False
                return True

            runner._close_emulator = AsyncMock(return_value=True)
            runner._close_game = close_game
            retry_task = asyncio.create_task(runner._reset_client_for_retry(1))
        else:
            retry_task = asyncio.create_task(report_script_task_retrying())
        await asyncio.wait_for(cleanup_started.wait(), 2)
        assert not retry_task.done()
        assert session._completed_at is None
        assert config.is_locked
        assert not second_started.is_set()
        assert not client_closed.is_set()

        allow_cleanup.set()
        await asyncio.wait_for(retry_task, 2)
        if retry_boundary == "maafw":
            assert client_closed.is_set()
        assert not config.is_locked
        assert root.current.prefetch is None
        assert managers[0].discard_prefetched_update.await_count == 1
        await asyncio.sleep(0.02)
        assert attempts == 1  # 旧时间不会让重新登录期间再次启动预下载。

        report_script_task_completed()
        await asyncio.wait_for(second_started.wait(), 2)
        assert attempts == 2
    finally:
        allow_cleanup.set()
        if retry_task is not None:
            await asyncio.gather(retry_task, return_exceptions=True)
        await session.close()
        script_task_retrying.reset(retry_token)
        script_task_completed.reset(completed_token)
