"""通知的有限等待、取消隔离与任务组注销。"""

import asyncio
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
async def test_community_wait_timeout_or_request_cancellation_keeps_delivery(
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
    finally:
        release.set()
        assert await owner.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_community_fast_path_returns_result_once_and_full_group_rejects():
    owner = BackgroundTaskRegistry()
    group = owner.register_group("community", max_running=1, max_retained=1)
    dispatch = AsyncMock(return_value=DispatchResult())
    coordinator = CommunityNotificationCoordinator(
        CommunityNotificationDependencies(
            dispatch=dispatch,
            prepare_targets=lambda: (),
            render=lambda results: NotifyPayload(title="test", text="test"),
            enabled=lambda: True,
            report_failure=AsyncMock(),
            background_group=lambda: group,
            fast_path_seconds=2,
        )
    )
    try:
        assert await coordinator.submit(RESULTS) == []
        # 前一次结果已被唯一提取，容量立即可复用。
        assert await coordinator.submit(RESULTS) == []
        dispatch.assert_awaited()
        held = group.spawn(asyncio.Event().wait)
        assert await coordinator.submit(RESULTS) == ["通知服务"]
        assert dispatch.await_count == 2
        held.cancel()
        assert await group.drain(2)
    finally:
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
