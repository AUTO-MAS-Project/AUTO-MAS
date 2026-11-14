"""脚本运行旁路保留消息顺序与单次统计。"""

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
