"""任务组的容量、一次性结果、取消和关闭契约。"""

import asyncio
from unittest.mock import Mock

import pytest
import pytest_asyncio

from app.core.background_tasks import (
    PENDING,
    BackgroundTaskRegistry,
    BackgroundTaskState,
    TaskOutcome,
)


@pytest_asyncio.fixture
async def registry():
    owner = BackgroundTaskRegistry()
    yield owner
    assert await owner.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_capacity_rejects_factory_and_completed_results_keep_record_slot(
    registry,
):
    group = registry.register_group("bounded", max_running=1, max_retained=2)
    release = asyncio.Event()

    async def work():
        await release.wait()
        return None

    first = group.spawn(work)
    rejected = Mock()
    assert group.spawn(rejected) is None
    rejected.assert_not_called()
    assert group.try_take(first) is PENDING
    release.set()
    assert await group.drain(2)
    second = group.spawn(work)
    assert await second.wait_done(2)
    assert group.spawn(rejected) is None
    rejected.assert_not_called()
    assert group.query(first).state == BackgroundTaskState.SUCCEEDED
    outcome = group.try_take(first)
    assert isinstance(outcome, TaskOutcome)
    assert outcome.unwrap() is None
    assert group.query(first) is None
    with pytest.raises(KeyError):
        group.try_take(first)
    again = group.spawn(work)
    assert again is not None
    assert await group.drain(2)


@pytest.mark.asyncio
async def test_wait_timeout_and_waiter_cancellation_keep_execution_and_result(registry):
    group = registry.register_group("wait", max_running=1, max_retained=1)
    release = asyncio.Event()

    async def work():
        await release.wait()
        return 42

    handle = group.spawn(work)
    with pytest.raises(TimeoutError):
        await group.wait_take(handle, timeout=0)
    assert not handle.done()
    assert not await group.drain(0)
    waiter = asyncio.create_task(handle.wait_take())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not handle.done()
    release.set()
    assert (await handle.wait_take(2)).unwrap() == 42


@pytest.mark.asyncio
async def test_only_one_waiter_can_extract(registry):
    group = registry.register_group("once", max_running=1, max_retained=1)

    async def work():
        return "result"

    handle = group.spawn(work)
    results = await asyncio.gather(
        handle.wait_take(), handle.wait_take(), return_exceptions=True
    )
    assert sum(isinstance(result, TaskOutcome) for result in results) == 1
    assert sum(isinstance(result, KeyError) for result in results) == 1


@pytest.mark.asyncio
async def test_errors_are_isolated_and_expiry_does_not_need_polling(registry):
    group = registry.register_group(
        "expiry", max_running=2, max_retained=2, result_ttl=0.02
    )
    error = ValueError("isolated failure")

    async def fail():
        raise error

    async def succeed():
        return 5

    failed, successful = group.spawn(fail), group.spawn(succeed)
    outcome = await failed.wait_take(2)
    assert outcome.state == BackgroundTaskState.FAILED
    with pytest.raises(ValueError) as raised:
        outcome.unwrap()
    assert raised.value is error
    assert await successful.wait_done(2)
    assert group.query(successful).state == BackgroundTaskState.SUCCEEDED
    await asyncio.sleep(0.04)
    assert group.query(successful) is None
    with pytest.raises(KeyError):
        await successful.wait_take()
    assert group.spawn(succeed) is not None


@pytest.mark.asyncio
async def test_execution_timeout_keeps_capacity_until_cleanup_finishes(registry):
    group = registry.register_group(
        "timeout", max_running=1, max_retained=1, execution_timeout=0.02
    )
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleaning.set()
            await release.wait()
            return "late return"

    handle = group.spawn(work)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(cleaning.wait(), 2)
        assert not handle.done()
        assert group.spawn(Mock()) is None
        release.set()
        outcome = await handle.wait_take(2)
        assert outcome.state == BackgroundTaskState.TIMED_OUT
        with pytest.raises(TimeoutError):
            outcome.unwrap()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_unregister_timeout_retains_closing_group_and_rejects_new_work(registry):
    group = registry.register_group("closing", max_running=1, max_retained=1)
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    handle = group.spawn(work, retain_result=False)
    try:
        await entered.wait()
        assert not await registry.unregister_group(group, timeout=0)
        await asyncio.wait_for(cleaning.wait(), 2)
        assert registry.get_group("closing") is group
        assert group.spawn(Mock()) is None
        with pytest.raises(ValueError):
            registry.register_group("closing", max_running=1, max_retained=1)
        # 重复注销不重复 cancel，避免打断任务的异步收尾。
        assert not await registry.unregister_group(group, timeout=0)
        assert not handle.done()
        release.set()
        assert await handle.wait_done(2)
        assert registry.get_group("closing") is None
        assert group.query(handle) is None
    finally:
        release.set()


@pytest.mark.asyncio
async def test_cancel_before_start_never_invokes_factory_and_no_result_is_released(
    registry,
):
    group = registry.register_group("cancel", max_running=1, max_retained=1)
    factory = Mock()
    handle = group.spawn(factory)
    handle.cancel()
    outcome = await handle.wait_take(2)
    assert outcome.state == BackgroundTaskState.CANCELLED
    factory.assert_not_called()
    with pytest.raises(asyncio.CancelledError):
        outcome.unwrap()

    async def work():
        return None

    handle = group.spawn(work, retain_result=False)
    assert await handle.wait_done(2)
    assert group.query(handle) is None
    with pytest.raises(KeyError):
        group.try_take(handle)


@pytest.mark.asyncio
async def test_group_identity_and_shutdown_barrier(registry):
    group = registry.register_group("first", max_running=1, max_retained=1)
    other = registry.register_group("second", max_running=1, max_retained=1)

    async def work():
        await asyncio.Event().wait()

    handle = group.spawn(work)
    with pytest.raises(ValueError):
        other.query(handle)
    foreign = BackgroundTaskRegistry()
    with pytest.raises(ValueError):
        await foreign.unregister_group(group)
    assert await registry.shutdown(timeout=2)
    assert handle.done() and group.query(handle) is None
    assert other.spawn(Mock()) is None
    with pytest.raises(RuntimeError):
        registry.register_group("late", max_running=1, max_retained=1)


@pytest.mark.parametrize(
    "options",
    [
        dict(max_running=0, max_retained=1),
        dict(max_running=1, max_retained=0),
        dict(max_running=1, max_retained=1, result_ttl=0),
        dict(max_running=1, max_retained=1, execution_timeout=-1),
    ],
)
def test_invalid_policy_is_rejected(options):
    with pytest.raises(ValueError):
        BackgroundTaskRegistry().register_group("invalid", **options)
