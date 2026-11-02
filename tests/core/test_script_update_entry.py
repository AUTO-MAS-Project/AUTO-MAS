"""统一更新入口必须等待完整操作，并保留取消与安装异常。"""

import asyncio

import pytest

from app.core.script_update import ScriptUpdateRequest, run_script_update


@pytest.mark.asyncio
@pytest.mark.parametrize("script_type", ["MAA", "MaaEnd", "Whimbox", "MaaFW", "HSR"])
async def test_update_waits_for_installation_before_returning(script_type):
    installing = asyncio.Event()
    installed = asyncio.Event()
    result = object()

    async def update(*, package):
        assert package == "downloaded"
        installing.set()
        await installed.wait()
        return result

    task = asyncio.create_task(
        run_script_update(
            ScriptUpdateRequest("script", script_type),
            update,
            package="downloaded",
        )
    )
    await installing.wait()
    assert not task.done()
    installed.set()
    assert await task is result


@pytest.mark.asyncio
async def test_cancellation_waits_for_operation_cleanup():
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()

    async def update():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await allow_cleanup.wait()

    task = asyncio.create_task(
        run_script_update(ScriptUpdateRequest("script", "HSR", "SRA"), update)
    )
    await started.wait()
    task.cancel()
    await cleanup_started.wait()
    assert not task.done()
    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_install_failure_is_not_reported_as_completion():
    error = RuntimeError("native updater failed")

    async def update():
        raise error

    with pytest.raises(RuntimeError) as caught:
        await run_script_update(ScriptUpdateRequest("script", "HSR", "M7A"), update)
    assert caught.value is error
