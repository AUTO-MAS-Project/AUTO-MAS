"""旧专项回调桥负责跨线程提交，运行树无需宿主子类。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.background_tasks import BackgroundTaskRegistry
from app.models.task import TaskItem, TaskMode
from app.task import legacy
from tests.runtime_support import create_runtime_tree


@pytest.mark.asyncio
async def test_stop_reaches_child_finalizer_and_still_waits_for_cleanup():
    from blinker import Signal

    root, _, _ = await create_runtime_tree()
    finalizing, cancel_capture, allow_cleanup, cleaned = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )

    class Child(legacy.TaskExecuteBase):
        async def main_task(self):
            pass

        async def final_task(self):
            finalizing.set()
            await cancel_capture.wait()
            await allow_cleanup.wait()
            cleaned.set()

        def _on_finalize_cancel_requested(self):
            cancel_capture.set()

        on_crash = AsyncMock()

    child = Child()

    class Parent(legacy.TaskExecuteBase):
        async def main_task(self):
            await self.spawn(child)

        final_task = AsyncMock()
        on_crash = AsyncMock()

    parent = Parent()
    # 独立验收旧执行桥，结束通知不发给只登记 ScriptExpander 的全局调度器。
    parent.execution.ended = Signal()
    parent.task_info, parent.history = root, AsyncMock()
    parent.execute()
    await asyncio.wait_for(finalizing.wait(), 2)
    stopping = asyncio.create_task(parent.stop())
    try:
        await asyncio.wait_for(cancel_capture.wait(), 2)
        assert child.stopped_manually
        assert not stopping.done()
    finally:
        allow_cleanup.set()
        await asyncio.wait_for(stopping, 2)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_specialized_state_is_shared_by_execution_without_entering_tree():
    root, script, user = await create_runtime_tree()

    class Operation(legacy.TaskExecuteBase):
        async def main_task(self):
            state = self.user_state(user)
            state.maintenance_skipped = True
            state.push_log_mode = "逐条"
            await state.append_push_log(("普通", "通知明细"))

        final_task = AsyncMock()
        on_crash = AsyncMock()

    parent, child = Operation(), Operation()
    parent.task_info = root
    parent.history = AsyncMock()
    await parent.spawn(child)
    assert parent.user_state(user) is child.user_state(user)
    assert parent.user_state(user).push_log == [("普通", "通知明细")]
    assert parent.user_state(user).maintenance_skipped
    assert Operation().user_state(user).push_log == []
    document = root.model_dump()
    stored = document["scripts"]["data"][str(script.uid)]["users"]["data"][
        str(user.uid)
    ]
    assert not (
        {"locked", "maintenance_skipped", "push_log", "push_log_mode"}
        & stored["info"].keys()
    )


@pytest.mark.asyncio
async def test_thread_callback_commits_in_consumer_and_close_waits(monkeypatch):
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(legacy, "BackgroundTaskManager", registry)
    root, _, user = await create_runtime_tree()
    assert type(root) is TaskItem
    assert not hasattr(root, "submit_runtime")
    bridge = legacy.LegacyCallbacks()
    entered, release = asyncio.Event(), asyncio.Event()
    owners = []

    async def update():
        owners.append(asyncio.current_task())
        user.info.status = "完成"
        entered.set()
        await release.wait()
        await user.commit()
        owners.append(asyncio.current_task())

    try:
        await asyncio.to_thread(bridge.submit, update())
        await asyncio.wait_for(entered.wait(), 2)
        closing = asyncio.create_task(bridge.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 2)
        assert user.status == "完成"
        assert owners[0] is owners[1]
        assert owners[0] is not asyncio.current_task()
        rejected = user.set_state(status="异常")
        await asyncio.to_thread(bridge.submit, rejected)
        assert rejected.cr_frame is None
        assert user.status == "完成"
    finally:
        release.set()
        await registry.shutdown()


@pytest.mark.asyncio
async def test_failed_callback_does_not_drop_remaining_writes(monkeypatch):
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(legacy, "BackgroundTaskManager", registry)
    _, _, user = await create_runtime_tree()
    bridge = legacy.LegacyCallbacks()

    async def fail():
        raise ValueError("synthetic callback failure")

    try:
        bridge.submit(fail())
        bridge.submit(user.set_state(status="完成"))
        await bridge.close()
        assert user.status == "完成"
        assert len(bridge.errors) == 1
        assert isinstance(bridge.errors[0], ValueError)
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
async def test_shutdown_before_consumer_starts_closes_queued_coroutines(monkeypatch):
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(legacy, "BackgroundTaskManager", registry)
    bridge = legacy.LegacyCallbacks()

    async def update():
        raise AssertionError("operation must not start")

    operation = update()
    bridge.submit(operation)
    await registry.shutdown()
    await asyncio.wait_for(bridge.close(), 2)
    assert operation.cr_frame is None
    assert not bridge.pending and bridge.closed
    late = legacy.LegacyCallbacks()
    rejected = update()
    late.submit(rejected)
    assert rejected.cr_frame is None
    assert late.closed and not late.pending


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(TaskMode))
async def test_mode_mapping_lives_only_in_legacy_execution(mode):
    class Operation(legacy.TaskExecuteBase):
        main_task = AsyncMock()
        final_task = AsyncMock()
        on_crash = AsyncMock()

    operation = Operation()
    operation.task_info = TaskItem(info={"mode": mode})
    assert not hasattr(operation.task_info, "execution_mode")
    assert operation.execution_mode == (
        TaskMode.SCRIPT_CONFIG if mode is TaskMode.SCRIPT_VIEW else mode
    )
    operation.maintenance = True
    assert operation.execution_mode == "Update"
    assert operation.task_info.mode is mode
    await operation.task_info.set_state(status="cancelled")
    assert operation.stopped_manually
