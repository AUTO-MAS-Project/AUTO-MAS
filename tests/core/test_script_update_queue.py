"""预取遵守任务成功信号、登录保护窗口和下载取消的所有权。"""

import asyncio
import uuid
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update_queue as queue
from app.models.task import ScriptItem, UserItem


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(queue, "time", SimpleNamespace(monotonic=lambda: clock.now))
    user = UserItem("user", "", "运行")
    script = ScriptItem("script", "", "运行", user_list=[user], current_index=0)
    return script, user, clock


async def settle():
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_only_prefetches_after_success_and_sixty_seconds(running):
    script, user, clock = running
    started = asyncio.Event()
    operation = AsyncMock(side_effect=started.set)
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
    await settle()
    operation.assert_not_called()
    user.first_task_completed_at = 100
    clock.now = 159.9
    await settle()
    operation.assert_not_called()
    clock.now = 160
    await asyncio.wait_for(started.wait(), 1)
    await pipeline.finish()
    operation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["异常", "跳过", "等待"])
async def test_unhealthy_user_does_not_start_download(running, status):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    user.status = status
    operation = AsyncMock()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
    await settle()
    await pipeline.finish()
    operation.assert_not_called()


@pytest.mark.asyncio
async def test_short_script_does_not_leave_a_timer_for_next_login(running):
    script, user, _ = running
    user.first_task_completed_at = 100
    operation = AsyncMock()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
    await settle()
    await pipeline.finish()
    operation.assert_not_called()


@pytest.mark.asyncio
async def test_normal_finish_waits_for_inflight_download(running):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    started, release = asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    script.status = "完成"
    finishing = asyncio.create_task(pipeline.finish())
    await settle()
    assert not finishing.done()
    release.set()
    await asyncio.wait_for(finishing, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "switch", "retry", "failure"])
async def test_cancellation_waits_for_download_cleanup(running, stop):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    if stop == "switch":
        script.user_list.append(UserItem("next", "", "运行"))
        script.current_index = 1
    elif stop == "retry":
        user.first_task_completed_at = None
    elif stop == "failure":
        user.status = "异常"
    finishing = asyncio.create_task(pipeline.finish(cancelled=stop == "cancel"))
    await asyncio.wait_for(cleaning.wait(), 1)
    assert not finishing.done()
    release.set()
    await asyncio.wait_for(finishing, 1)


@pytest.mark.asyncio
async def test_failed_prefetch_does_not_fail_current_script(running):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    operation = AsyncMock(side_effect=RuntimeError("offline"))
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
    await settle()
    await pipeline.finish()
    assert script.status == "运行"
    operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_during_timer_cleanup_is_not_swallowed():
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def timer():
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline._watcher = asyncio.create_task(timer())
    await asyncio.sleep(0)
    finishing = asyncio.create_task(pipeline.finish())
    await cleaning.wait()
    finishing.cancel()
    await asyncio.sleep(0)
    assert not finishing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await finishing


@pytest.mark.asyncio
@pytest.mark.parametrize("change_config", [False, True])
async def test_three_scripts_download_then_install_in_queue_order(
    monkeypatch, change_config
):
    from app.core.task_manager import manager as scheduler
    from app.models.task import TaskExecuteBase

    monkeypatch.setattr(queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    ids = [uuid.uuid4() for _ in range(3)]
    configs = {}
    for uid in ids:
        config = SimpleNamespace(revision=0, is_locked=False)
        config.model_dump = lambda *, mode, config=config: {"revision": config.revision}
        configs[uid] = config
    monkeypatch.setattr(
        scheduler,
        "Config",
        SimpleNamespace(
            ScriptConfig=configs,
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(model_dump=lambda **_: {})),
        ),
    )
    monkeypatch.setattr(scheduler, "_exclusive_resources", lambda _: ((), None))
    info = scheduler.TaskInfo("AutoProxy", "test", "queue", None, None)
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    info.script_list = [ScriptItem(str(uid), "", "等待") for uid in ids]
    events = []
    prepared = [asyncio.Event() for _ in ids]

    class Manager(TaskExecuteBase):
        def __init__(self, item):
            super().__init__()
            self.item = item
            self.index = ids.index(uuid.UUID(item.script_id))
            self.ready = False

        async def prefetch_script_update(self):
            events.append(("download", self.index))
            self.ready = True
            if change_config and self.index == 1 and not prepared[1].is_set():
                configs[ids[1]].revision += 1
            prepared[self.index].set()

        async def main_task(self):
            if not self.ready:
                await self.prefetch_script_update()
            events.append(("install", self.index))
            user = UserItem(str(self.index), "", "运行")
            self.item.user_list = [user]
            self.item.current_index = 0
            user.mark_task_completed()
            events.append(("run", self.index))
            if self.index < 2:
                await asyncio.wait_for(prepared[self.index + 1].wait(), 1)
            events.append(("finish", self.index))
            self.item.status = "完成"

        async def final_task(self):
            pass

        async def on_crash(self, error):
            raise error

        async def discard_prefetched_update(self):
            self.ready = False

    task = scheduler.Task(
        info, [], manager_factories={SimpleNamespace: lambda item, _: Manager(item)}
    )
    monkeypatch.setattr(task, "spawn", lambda child: child.main_task())
    monkeypatch.setattr(task, "_observe_script_run", lambda *args: nullcontext())
    await task._run_script_list(0)
    for index in (1, 2):
        assert events.index(("run", index - 1)) < events.index(("download", index))
        assert events.index(("finish", index - 1)) < events.index(("install", index))
        assert events.index(("download", index)) < events.index(("install", index))
    assert events.count(("download", 1)) == (2 if change_config else 1)
    assert task._prefetched_manager is None
