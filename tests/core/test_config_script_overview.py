"""卫星所用概览仅由配置和持久化历史提供。"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core import Config
from app.core.history import HistoryStore
from app.models.config import GeneralConfig, QueueConfig, QueueItem, TimeSet
from app.models.schema import HistoryWrite
from tests.core.test_history_archive import store as store
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.asyncio
async def test_latest_results_survive_a_new_history_store(store):
    now = datetime.now(timezone.utc)
    for name, time, status in (
        ("first", now - timedelta(days=1), "error"),
        ("second", now, "error"),
        ("first", now, "success"),
    ):
        await store.record(
            HistoryWrite(
                time=time,
                username="synthetic",
                script_name=name,
                status=status,
                message="result",
                logs="log body",
            )
        )
    restored = HistoryStore()
    await restored.initialize(video_limit_bytes=1024 * 1024)
    try:
        result = await restored.get_latest_script_results(
            script_names=["first", "second", "first", "absent"]
        )
        assert result == {"first": (now, "success"), "second": (now, "error")}
        assert await restored.get_latest_script_results(script_names=[]) == {}
    finally:
        await restored.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("info", "timed", "expected"),
    [
        ({"CycleEnabled": True}, False, True),
        ({"TimeEnabled": True}, True, True),
        ({"TimeEnabled": True}, False, False),
        ({"StartUpMode": "Always"}, False, False),
        ({}, False, False),
    ],
)
async def test_config_overview_reads_schedules_and_history_without_running_tasks(
    scheduler, info, timed, expected
):
    manager, scripts, queues, sid = scheduler
    other = scripts.add(GeneralConfig, payload={"Info": {"Name": "other"}})
    await scripts.commit()
    qid = queues.add(QueueConfig, payload={"Info": info})
    await queues.commit()
    queue = queues[qid]
    for _ in range(2):
        queue.QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queue.QueueItem.commit()
    if timed:
        queue.TimeSet.add(
            TimeSet, payload={"Info": {"Enabled": True, "Days": ["Monday"]}}
        )
        await queue.TimeSet.commit()
    before = queues.model_dump()
    now = datetime.now(timezone.utc)
    history = AsyncMock(return_value={"script": (now, "error")})
    with patch("app.core.History.get_latest_script_results", history):
        result = await Config.get_script_status_overview()
    by_id = {item.scriptId: item for item in result}
    assert len(result) == 2
    assert by_id[str(sid)].scheduled is expected
    assert by_id[str(sid)].lastFailed and by_id[str(sid)].lastRunAt == now
    assert not by_id[str(other)].scheduled and not by_id[str(other)].lastFailed
    assert by_id[str(other)].lastRunAt is None
    assert queues.model_dump() == before
    assert not manager.task_info
    assert manager.get_runtime_snapshot().model_dump() == {"tasks": []}
    history.assert_awaited_once_with(script_names=["script", "other"])


@pytest.mark.asyncio
async def test_duplicate_config_names_do_not_borrow_an_ambiguous_history(scheduler):
    _, scripts, _, sid = scheduler
    scripts.add(GeneralConfig, payload={"Info": {"Name": "script"}})
    await scripts.commit()
    history = AsyncMock(return_value={})
    with patch("app.core.History.get_latest_script_results", history):
        result = await Config.get_script_status_overview()
    assert len(result) == 2 and any(item.scriptId == str(sid) for item in result)
    assert all(item.lastRunAt is None and not item.lastFailed for item in result)
    history.assert_awaited_once_with(script_names=[])


@pytest.mark.asyncio
async def test_overview_endpoint_reports_history_failure_without_a_false_result(
    monkeypatch,
):
    from app.api.info import get_script_status_overview
    from app.core.history import HistoryStorageError

    monkeypatch.setattr(
        Config,
        "get_script_status_overview",
        AsyncMock(side_effect=HistoryStorageError("unavailable")),
    )
    result = await get_script_status_overview()
    assert result.code == 503 and result.status == "error" and result.data == []
