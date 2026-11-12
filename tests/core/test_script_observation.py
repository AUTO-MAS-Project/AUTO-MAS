"""有界旁路复用后台任务所有者，保留配额及结束消息顺序。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import app.core
from app.core import Publisher
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.ws import protocol
from app.services.common import telemetry
from tests.runtime_support import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize("started_sent", [False, True])
async def test_script_observation_keeps_message_order_and_single_metric(
    monkeypatch, started_sent
):
    root, script, user = await create_runtime_tree()
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(app.core, "BackgroundTaskManager", registry)
    sent = AsyncMock(return_value=started_sent)
    monkeypatch.setattr(Publisher, "send", sent)
    metric = Mock()
    monkeypatch.setattr(telemetry, "record_count", metric)
    try:
        with telemetry.observe_script_run(root, script):
            await user.set_state(status="完成")
        assert await registry.get_group("script-run-observation").drain(2)
        kinds = [call.kwargs["type"] for call in sent.await_args_list]
        assert kinds == (
            [protocol.TASK_SCRIPT_STARTED, protocol.TASK_SCRIPT_FINISHED]
            if started_sent
            else [protocol.TASK_SCRIPT_STARTED]
        )
        metric.assert_called_once()
        assert metric.call_args.kwargs["attributes"]["outcome"] == "success"
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
async def test_observation_capacity_drops_only_messages_and_keeps_business_metrics(
    monkeypatch,
):
    root, script, _ = await create_runtime_tree()
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(app.core, "BackgroundTaskManager", registry)
    release = asyncio.Event()

    async def send(**kwargs):
        await release.wait()
        return True

    sender = AsyncMock(side_effect=send)
    monkeypatch.setattr(Publisher, "send", sender)
    metric = Mock()
    monkeypatch.setattr(telemetry, "record_count", metric)
    try:
        # 每轮各注册一个 started/finished；超出 32 个在途项只丢本地消息。
        for _ in range(17):
            with telemetry.observe_script_run(root, script):
                pass
        assert metric.call_count == 17
        release.set()
        assert await registry.get_group("script-run-observation").drain(2)
        assert sender.await_count == 32
    finally:
        release.set()
        await registry.shutdown()
