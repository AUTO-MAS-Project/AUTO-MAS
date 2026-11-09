"""来源式即时信号推送：同协程执行，允许事务过程态，不维护发布任务。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.config import config_manager
from app.core import Publisher
from app.core.task_manager import _TaskManager
from app.core.ws import protocol
from app.models.task import LogRecord
from app.task.script_expander import ScriptExpander
from tests.runtime_support import create_runtime_tree


async def runtime(monkeypatch):
    root, script, user = await create_runtime_tree()
    dispatcher = _TaskManager()
    run = ScriptExpander(root, dispatcher)
    dispatcher._running[root.uid] = run
    monkeypatch.setattr("app.core.task_manager.TaskManager", dispatcher)
    return dispatcher, run, script, user


@pytest.mark.asyncio
async def test_field_signal_is_awaited_in_same_task_inside_transaction(monkeypatch):
    _, run, _, user = await runtime(monkeypatch)
    owner = asyncio.current_task()
    observed = []
    states = []

    async def send(**message):
        observed.append(
            (asyncio.current_task(), config_manager.in_transaction, message["type"])
        )
        if message["type"] == protocol.TASK_INFO_UPDATED:
            states.append(message["data"])
        return True

    monkeypatch.setattr(Publisher, "send", send)
    async with config_manager.transaction():
        await user.set_state(status="运行")
        assert observed == [
            (owner, True, protocol.TASK_INFO_UPDATED),
        ]
        users = next(iter(states[0]["scripts"]["data"].values()))["users"]["data"]
        assert next(iter(users.values()))["info"]["status"] == "运行"
    assert run.task_info.script_list[0].user_list[0].status == "运行"


@pytest.mark.asyncio
async def test_collection_signal_publishes_and_unregistered_tree_does_not(monkeypatch):
    dispatcher, run, _, user = await runtime(monkeypatch)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    user.logs.add(LogRecord)
    await user.logs.commit()
    assert [call.kwargs["type"] for call in sent.await_args_list] == [
        protocol.TASK_INFO_UPDATED,
    ]
    await dispatcher.drop(run)
    sent.reset_mock()
    await user.set_state(status="完成")
    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_rollback_keeps_emitted_process_notice_but_query_reads_live_tree(
    monkeypatch,
):
    dispatcher, run, script, user = await runtime(monkeypatch)
    await script.set_current_index(0)
    uid = user.logs.add(LogRecord, payload={"info": {"content": ["before\n"]}})
    await user.logs.commit()
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    with pytest.raises(ValueError, match="rollback"):
        async with config_manager.transaction():
            await user.logs[uid].set_state(content=["after\n"])
            raise ValueError("rollback")
    messages = [
        call.kwargs["data"].log
        for call in sent.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]
    assert messages == ["after\n"]
    assert dispatcher.get_task(run.task_info.uid)["current"]["log"] == "before\n"
    assert run.task_info.get_log_snapshot()["logSeq"] is None
