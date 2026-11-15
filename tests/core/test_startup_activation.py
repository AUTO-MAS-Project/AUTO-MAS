"""监督器放行前不启动自动业务，放行和关闭均保持幂等。"""

import asyncio

import pytest

from app.core.startup import StartupActivation


@pytest.mark.asyncio
async def test_deferred_start_waits_for_one_activation() -> None:
    activation = StartupActivation(deferred=True)
    entered = asyncio.Event()

    async def automatic_work() -> None:
        await activation.wait()
        entered.set()

    work = asyncio.create_task(automatic_work())
    await asyncio.sleep(0)
    assert not entered.is_set()
    assert activation.status == "pending"
    activation.activate()
    activation.activate()
    await work
    assert entered.is_set()
    assert activation.status == "active"


@pytest.mark.asyncio
async def test_closed_start_cannot_be_activated() -> None:
    activation = StartupActivation(deferred=True)
    activation.close()
    with pytest.raises(RuntimeError, match="关闭"):
        activation.activate()
    with pytest.raises(asyncio.CancelledError):
        await activation.wait()


@pytest.mark.asyncio
async def test_standalone_start_is_already_active() -> None:
    activation = StartupActivation(deferred=False)
    await activation.wait()
    assert activation.status == "active"


@pytest.mark.asyncio
async def test_close_after_activation_cancels_an_already_woken_waiter() -> None:
    activation = StartupActivation(deferred=True)
    waiter = asyncio.create_task(activation.wait())
    await asyncio.sleep(0)
    activation.activate()
    activation.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
