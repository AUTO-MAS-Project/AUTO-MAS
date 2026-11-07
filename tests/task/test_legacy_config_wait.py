"""旧专项在配置锁所在层等待；取消、失效和热态路径不依赖外部预约。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.notify.lifecycle import NotificationTaskBase
from app.models.config import SrcConfig
from app.task.SRC.manager import SrcManager
from tests.core.test_task_tree_dispatch import scheduler as scheduler
from tests.runtime_support import create_runtime_tree


async def wait_for_lock_state(script):
    async def wait():
        while script.status != "等待" or "等待托管配置" not in script.log:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["release", "cancel", "delete"])
async def test_legacy_waits_at_config_lock_and_handles_cancel_or_deletion(
    scheduler, action
):
    _, scripts, _, sid = scheduler
    config = scripts[sid]
    _, script, _ = await create_runtime_tree(script_id=str(sid))
    owner = SimpleNamespace(script_info=script)
    held = await config.lock_x()

    async def acquire():
        ticket = await NotificationTaskBase.lock_script_config(owner, config)
        try:
            assert config.Info.Name == "latest"
        finally:
            await config.unlock(ticket)

    waiter = asyncio.create_task(acquire())
    try:
        await wait_for_lock_state(script)
        assert not waiter.done()
        config.Info.Name = "latest"
        await config.commit()
        if action == "cancel":
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert config.is_locked
        else:
            await config.unlock(held)
            held = None
            if action == "delete":
                scripts.remove(sid)
                await scripts.commit()
                with pytest.raises(ValueError, match="删除或替换"):
                    await asyncio.wait_for(waiter, 3)
            else:
                await asyncio.wait_for(waiter, 3)
            assert not config.is_locked
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        if held is not None:
            await config.unlock(held)


@pytest.mark.asyncio
async def test_src_captures_latest_path_after_config_lock(scheduler, tmp_path):
    _, scripts, _, _ = scheduler
    initial, latest = tmp_path / "initial", tmp_path / "latest"
    initial.mkdir()
    latest.mkdir()
    scripts.add_type(SrcConfig)
    await scripts.commit()
    sid = scripts.add(SrcConfig, payload={"Info": {"Path": initial}})
    await scripts.commit()
    config = scripts[sid]
    _, script, _ = await create_runtime_tree(script_id=str(sid))
    manager = SrcManager(script)
    held = await config.lock_x()

    async def prepare():
        try:
            await manager._initialize_recovery_context()
            assert manager.src_root_path == latest.resolve()
            assert manager.src_set_path == latest.resolve() / "config"
        finally:
            ticket = manager.config_locks.pop(sid, None)
            if ticket is not None:
                await config.unlock(ticket)

    preparing = asyncio.create_task(prepare())
    try:
        await wait_for_lock_state(script)
        config.Info.Path = latest
        await config.commit()
        await config.unlock(held)
        held = None
        await asyncio.wait_for(preparing, 3)
        assert not config.is_locked
    finally:
        if not preparing.done():
            preparing.cancel()
        await asyncio.gather(preparing, return_exceptions=True)
        if held is not None:
            await config.unlock(held)
