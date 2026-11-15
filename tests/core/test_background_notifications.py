"""通知的有限等待、取消隔离与任务组注销。"""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.background_tasks import BackgroundTaskRegistry
from app.core.notify import tasks
from app.core.notify.community import (
    CommunityNotificationCoordinator,
    CommunityNotificationDependencies,
)
from app.models.notification import NotifyPayload
from app.models.notification.channel import DispatchResult
from app.models.notification.community import CommunityNotificationResult

RESULTS = (CommunityNotificationResult("name", "uid", "game", "platform", "success"),)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_request", [False, True])
async def test_notification_waiter_stop_preserves_delivery_and_releases_capacity(
    cancel_request,
):
    owner = BackgroundTaskRegistry()
    group = owner.register_group("community", max_running=2, max_retained=2)
    entered, release, delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    feedback = AsyncMock()

    async def dispatch(*args, **kwargs):
        entered.set()
        await release.wait()
        delivered.set()
        return DispatchResult(failed=("channel",))

    coordinator = CommunityNotificationCoordinator(
        CommunityNotificationDependencies(
            dispatch=dispatch,
            prepare_targets=lambda: (),
            render=lambda results: NotifyPayload(title="test", text="test"),
            enabled=lambda: True,
            report_failure=feedback,
            background_group=lambda: group,
            fast_path_seconds=10 if cancel_request else 0,
        )
    )
    try:
        request = asyncio.create_task(coordinator.submit(RESULTS))
        await asyncio.wait_for(entered.wait(), 2)
        if cancel_request:
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            assert await request is None
        assert not delivered.is_set()
        assert not await coordinator.drain(0)
        release.set()
        assert await coordinator.drain(2)
        assert delivered.is_set()
        feedback.assert_awaited_once()
        dispatch_now = AsyncMock(return_value=DispatchResult())
        fast = CommunityNotificationCoordinator(
            replace(
                coordinator.dependencies, dispatch=dispatch_now, fast_path_seconds=2
            )
        )
        assert await fast.submit(RESULTS) == []
        assert await fast.submit(RESULTS) == []
        # 慢通知的未领取结果占一个保留位置；快请求取走自己的结果后仍可复用余位。
        held = group.spawn(asyncio.Event().wait)
        assert held is not None
        assert await fast.submit(RESULTS) == ["通知服务"]
        assert dispatch_now.await_count == 2
        held.cancel()
        assert await group.drain(2)
    finally:
        release.set()
        assert await owner.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_notification_close_waits_for_cleanup_and_rejects_without_invoking_factory(
    monkeypatch,
):
    owner = BackgroundTaskRegistry()
    monkeypatch.setattr(tasks, "BackgroundTaskManager", owner)
    notifications = tasks.NotificationTasks()
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def send():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    handle = notifications.spawn_notification(send, task_id="root")
    await asyncio.wait_for(entered.wait(), 2)
    await notifications.close()
    assert cleaned.is_set() and handle.done()
    refused = Mock()
    assert notifications.spawn_notification(refused, task_id="root") is None
    refused.assert_not_called()
    assert owner.get_group(notifications.group.name) is None
    assert await owner.shutdown(timeout=2)
