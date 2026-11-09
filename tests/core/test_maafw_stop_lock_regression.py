"""A stop timeout must not abandon MaaFW configuration unlock."""

import asyncio
import uuid

import pytest

from app.models.config import MaaFWConfig
from app.models.task import TaskItem, TaskMode
from app.task.MaaFW import embedded_manager as maafw
from tests.task_stop_support import StopTask, add_script


@pytest.mark.asyncio
async def test_maafw_stop_does_not_abandon_config_unlock_after_callback_timeout(
    monkeypatch,
):
    info = TaskItem(info={"mode": TaskMode.AUTO_PROXY})
    script = await add_script(info, str(uuid.uuid4()))
    config = MaaFWConfig()
    await config.activate()
    ticket = await config.lock_x()
    manager = maafw.MaaFWEmbeddedManager(script)
    manager.script_config = config
    manager.config_locks[config.uid] = ticket
    manager._script_locked = True
    manager.stop_finalizer_timeout = 0.03

    async def flush():
        return None

    monkeypatch.setattr(maafw.config_manager, "flush", flush)
    entered = asyncio.Event()
    callback_entered = asyncio.Event()
    release_callback = asyncio.Event()

    async def pending_write():
        callback_entered.set()
        await release_callback.wait()

    manager.callbacks.submit(pending_write())

    async def run_manager():
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "main_task", run_manager)

    class Root(StopTask):
        async def main_task(self):
            await self.spawn(manager)

    task = Root(info)
    task.start()
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(callback_entered.wait(), 2)
        stopping = task.request_stop()
        await asyncio.wait_for(stopping, 3)
        assert config.is_locked  # The callback is still writing; release here is unsafe.
        release_callback.set()
        async with asyncio.timeout(2):
            while config.is_locked:
                await asyncio.sleep(0.01)
        next_ticket = await config.try_lock_x()
        assert next_ticket is not None
        await config.unlock(next_ticket)
    finally:
        release_callback.set()
        if not task.accomplish.is_set():
            task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
        workers = tuple(task._stop_scope.retained_workers)
        await asyncio.gather(*workers, return_exceptions=True)
        await manager.callbacks.close()
        if config.is_locked:
            await config.unlock(ticket)
