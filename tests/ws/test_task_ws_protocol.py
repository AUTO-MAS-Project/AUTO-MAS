from unittest.mock import AsyncMock, patch

import pytest

from app.core.task_manager import TaskInfo
from app.core.ws import protocol
from app.models.task import ScriptItem


@pytest.mark.asyncio
async def test_task_change_publishes_separate_info_and_log_events() -> None:
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-1",
        queue_id=None,
        script_id=None,
        user_id=None,
        script_list=[
            ScriptItem(
                script_id="script-1",
                name="示例脚本",
                status="运行",
                log="line-1",
            )
        ],
        current_index=0,
    )

    with patch("app.core.task_manager.Publisher.send", new_callable=AsyncMock) as send, patch.object(
        task_info, "_emit_task_progress", new_callable=AsyncMock
    ), patch.object(task_info, "_emit_task_log", new_callable=AsyncMock):
        await task_info.on_change()

    assert [call.kwargs["type"] for call in send.await_args_list] == [
        protocol.TASK_INFO_UPDATED,
        protocol.TASK_LOG_UPDATED,
    ]
    assert send.await_args_list[0].kwargs["data"]["task_info"] == task_info.asdict
    assert send.await_args_list[1].kwargs["data"] == {"log": "line-1"}


def test_cycle_task_ws_data_preserves_legacy_task_info_and_adds_state() -> None:
    task_info = TaskInfo(
        mode="CycleRun",
        task_id="task-cycle",
        queue_id="queue-1",
        script_id=None,
        user_id=None,
        cycle_next_run_at="2026-07-24 18:30:00",
        cycle_waiting_reason="等待下一个队列项",
        cycle_current_item_id="item-2",
    )

    assert task_info.ws_data == {
        "task_info": [],
        "cycleQueueId": "queue-1",
        "cycleNextRunAt": "2026-07-24 18:30:00",
        "cycleWaitingReason": "等待下一个队列项",
        "cycleCurrentItemId": "item-2",
        "cycleNext": None,
        "cycleNextList": [],
    }


@pytest.mark.asyncio
async def test_cycle_change_publishes_cycle_state_not_only_legacy_list() -> None:
    preview = {
        "queueItemId": "item-1",
        "scriptId": "script-1",
        "scriptName": "示例脚本",
        "nextRunAt": "2026-07-24 18:30:00",
        "isDue": False,
        "isRunning": False,
    }
    task_info = TaskInfo(
        mode="CycleRun",
        task_id="task-cycle",
        queue_id="queue-1",
        script_id=None,
        user_id=None,
        cycle_next_list=[preview],
    )

    with patch(
        "app.core.task_manager.Publisher.send",
        new_callable=AsyncMock,
    ) as send, patch.object(
        task_info,
        "_emit_task_progress",
        new_callable=AsyncMock,
    ), patch.object(
        task_info,
        "_emit_task_log",
        new_callable=AsyncMock,
    ):
        await task_info.on_change()

    assert send.await_args.kwargs["data"]["cycleNext"] == preview
    assert send.await_args.kwargs["data"]["cycleNextList"] == [preview]


def test_non_cycle_task_ws_data_keeps_legacy_shape() -> None:
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-legacy",
        queue_id="queue-1",
        script_id=None,
        user_id=None,
    )

    assert task_info.ws_data == {"task_info": []}
