"""宿主合并状态变化，并在关闭时回收发布任务。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.runtime_tasks import OwnedTaskRegistry
from app.core.task_manager import manager
from app.models.task import ScriptItem, UserItem


@pytest.fixture
def runtime(monkeypatch):
    registry = OwnedTaskRegistry()
    monkeypatch.setattr(manager, "RuntimeTasks", registry)
    return registry


def task_info():
    return manager.TaskInfo(
        mode="AutoProxy",
        task_id="state-change-test",
        queue_id=None,
        script_id=None,
        user_id=None,
    )


@pytest.mark.asyncio
async def test_changes_merge_and_changes_during_publish_are_not_lost(runtime):
    info = task_info()
    user = UserItem(user_id="user", name="User", status="waiting")
    script = ScriptItem(
        script_id="script", name="Script", status="waiting", user_list=[user]
    )
    info.script_list = [script]
    entered = asyncio.Event()
    release = asyncio.Event()
    snapshots = []

    async def publish():
        snapshots.append((script.status, user.status))
        if len(snapshots) == 1:
            entered.set()
            await release.wait()

    info.on_change = publish
    script.status = "running"
    user.status = "running"
    pending = info._change_task
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        user.status = "finished"
        script.status = "finished"
        assert info._change_task is pending
        release.set()
        await asyncio.wait_for(asyncio.shield(pending), timeout=2)
        assert snapshots == [("running", "running"), ("finished", "finished")]
        assert info._change_task is None
        assert not info._change_dirty
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_inflight_publish_and_rejects_new_changes(runtime):
    info = task_info()
    entered = asyncio.Event()
    finalized = asyncio.Event()

    async def publish():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            finalized.set()

    info.on_change = publish
    info.schedule_on_change()
    pending = info._change_task
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
    finally:
        await runtime.shutdown()
    assert pending.cancelled()
    assert finalized.is_set()
    assert info._change_task is None
    info.on_change = AsyncMock()
    info.schedule_on_change()
    assert info._change_task is None
    assert not info._change_dirty
    info.on_change.assert_not_awaited()
