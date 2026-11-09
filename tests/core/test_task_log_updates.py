"""完整信息树查询与独立增量日志协议。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core import Publisher
from app.core.task_manager import _TaskManager
from app.core.ws import protocol
from app.models.task import LogRecord, TaskUserItem
from app.task.script_expander import ScriptExpander
from tests.runtime_support import create_runtime_tree


async def runtime(monkeypatch):
    root, script, user = await create_runtime_tree()
    manager = _TaskManager()
    manager._running[root.uid] = ScriptExpander(root, manager)
    monkeypatch.setattr("app.core.task_manager.TaskManager", manager)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    return root, script, user, manager, sent


def packets(sent, kind):
    return [
        call.kwargs["data"]
        for call in sent.await_args_list
        if call.kwargs["type"] == kind
    ]


@pytest.mark.asyncio
async def test_initial_snapshot_has_zero_sequence_and_first_packet_replaces(
    monkeypatch,
):
    root, script, _ = await create_runtime_tree()
    await script.set_log("before registration")
    manager = _TaskManager()
    manager._running[root.uid] = ScriptExpander(root, manager)
    monkeypatch.setattr("app.core.task_manager.TaskManager", manager)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    snapshot = manager.get_runtime_snapshot().tasks[0]
    assert snapshot.log == "before registration" and snapshot.logSeq == 0
    await script.append_log("+first publication")
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert packet.seq == 1 and not packet.append
    assert packet.log == "before registration+first publication"


@pytest.mark.asyncio
async def test_append_reset_and_empty_logs_use_independent_channel(monkeypatch):
    root, script, user, manager, sent = await runtime(monkeypatch)
    for text in ("one\n", "one\ntwo\n", "reset\n", ""):
        await script.set_log(text)
    assert [data.model_dump() for data in packets(sent, protocol.TASK_LOG_UPDATED)] == [
        {"log": "one\n", "seq": 1, "append": False, "firstLine": 1},
        {"log": "two\n", "seq": 2, "append": True, "firstLine": 1},
        {"log": "reset\n", "seq": 3, "append": False, "firstLine": 1},
        {"log": "", "seq": 4, "append": False, "firstLine": 1},
    ]
    assert not packets(sent, protocol.TASK_INFO_UPDATED)
    sent.reset_mock()
    await script.set_log("")
    await user.set_state(status="完成")
    assert not packets(sent, protocol.TASK_LOG_UPDATED)
    assert len(packets(sent, protocol.TASK_INFO_UPDATED)) == 1
    sent.reset_mock()
    await user.set_state(status="完成")
    assert not sent.await_args_list
    snapshot = manager.get_runtime_snapshot().tasks[0]
    assert snapshot.logSeq == 4 and snapshot.log == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", [[f"{n}\n" for n in range(1002)], ["head\n", "x" * 200_005]]
)
async def test_tree_and_queries_keep_full_logs_but_metadata_omits_bodies(
    monkeypatch, content
):
    root, script, user, manager, sent = await runtime(monkeypatch)
    await script.set_log("legacy body")
    await script.set_current_index(0)
    uid = user.logs.add(LogRecord, payload={"info": {"content": content}})
    await user.logs.commit()
    expected = "".join(content)
    snapshot = manager.get_runtime_snapshot().tasks[0]
    assert snapshot.log == expected and snapshot.logSeq is not None
    assert snapshot.task.current.log == expected
    tree = manager.get_task(root.uid)
    assert tree["current"]["log"] == expected
    stored = tree["scripts"]["data"][str(script.uid)]
    assert stored["current"]["log"] == "legacy body"
    assert (
        stored["users"]["data"][str(user.uid)]["logs"]["data"][str(uid)]["info"][
            "content"
        ]
        == content
    )
    assert script.model_dump()["current"]["log"] == "legacy body"
    metadata = root.get_update()
    # 元数据通道不应先导出整棵含正文的树，再删除字段。
    monkeypatch.setattr(
        type(root),
        "model_dump",
        lambda *args, **kwargs: pytest.fail("full tree export"),
    )
    assert root.get_update() == metadata
    assert "log" not in metadata["current"]
    script_info = metadata["scripts"]["data"][str(script.uid)]
    assert (
        "log" not in script_info["current"]
        and "first_line" not in script_info["current"]
    )
    assert (
        "content"
        not in script_info["users"]["data"][str(user.uid)]["logs"]["data"][str(uid)][
            "info"
        ]
    )
    sent.reset_mock()
    await user.logs[uid].append_content("tail\n")
    assert not packets(sent, protocol.TASK_INFO_UPDATED)
    assert packets(sent, protocol.TASK_LOG_UPDATED)[0].log == "tail\n"


@pytest.mark.asyncio
async def test_large_replacement_is_bounded_and_snapshot_is_not(monkeypatch):
    root, script, _, manager, sent = await runtime(monkeypatch)
    text = "discarded\n" + "x" * 200_000
    await script.set_log(text)
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert packet.log == "x" * 200_000 and not packet.append and packet.firstLine == 2
    snapshot = manager.get_runtime_snapshot().tasks[0]
    assert (
        snapshot.log == text
        and snapshot.logFirstLine == 1
        and snapshot.logSeq == packet.seq
    )
    sent.reset_mock()
    await script.set_log(text + "\n" + "y" * 200_000)
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert not packet.append and packet.firstLine == 3 and packet.seq == 2


@pytest.mark.asyncio
async def test_source_switch_replaces_identical_text_and_inactive_body_does_not_push(
    monkeypatch,
):
    root, script, user, manager, sent = await runtime(monkeypatch)
    await script.set_current_index(0)
    first = user.logs.add(LogRecord, payload={"info": {"content": ["same\n"]}})
    await user.logs.commit()
    other = script.users.add(TaskUserItem, payload={"info": {"user_id": "other"}})
    await script.users.commit()
    second = script.users[other].logs.add(
        LogRecord, payload={"info": {"content": ["same\n"]}}
    )
    await script.users[other].logs.commit()
    seq = manager.get_runtime_snapshot().tasks[0].logSeq
    sent.reset_mock()
    await script.set_current_index(1)
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert not packet.append and packet.log == "same\n" and packet.seq == seq + 1
    sent.reset_mock()
    await user.logs[first].append_content("inactive\n")
    assert not sent.await_args_list
    await script.users[other].logs[second].append_content("active\n")
    assert packets(sent, protocol.TASK_LOG_UPDATED)[0].log == "active\n"


@pytest.mark.asyncio
async def test_publication_exception_does_not_advance_cursor_or_block_later_changes(
    monkeypatch,
):
    from app.config.errors import ConfigAggregateError

    root, script, _, manager, sent = await runtime(monkeypatch)
    sent.side_effect = RuntimeError("publication failed")
    with pytest.raises(ConfigAggregateError):
        await script.set_log("failed")
    assert root.get_log_snapshot()["logSeq"] == 0
    sent.side_effect = None
    sent.reset_mock()
    await script.set_log("recovered")
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert packet.seq == 1 and not packet.append and packet.log == "recovered"


@pytest.mark.asyncio
async def test_model_declared_subscription_uses_transaction_order(monkeypatch):
    root, script, user = await create_runtime_tree()
    await script.set_current_index(0)
    uid = user.logs.add(LogRecord)
    await user.logs.commit()
    manager = _TaskManager()
    run = ScriptExpander(root, manager)
    manager._running[root.uid] = run
    monkeypatch.setattr("app.core.task_manager.TaskManager", manager)
    entered, release = asyncio.Event(), asyncio.Event()
    messages = []

    async def send(**message):
        if message["type"] != protocol.TASK_LOG_UPDATED:
            return True
        if not messages:
            entered.set()
            await release.wait()
        messages.append(message["data"].model_dump())
        return True

    monkeypatch.setattr(Publisher, "send", send)
    one = asyncio.create_task(user.logs[uid].append_content("one\n"))
    two = None
    try:
        await asyncio.wait_for(entered.wait(), 3)
        two = asyncio.create_task(user.logs[uid].append_content("two\n"))
        await asyncio.sleep(0)
        assert not two.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(one, two), 3)
        assert messages == [
            {"log": "one\n", "seq": 1, "append": False, "firstLine": 1},
            {"log": "two\n", "seq": 2, "append": True, "firstLine": 1},
        ]
        assert root.get_log_snapshot() == {
            "log": "one\ntwo\n",
            "logSeq": 2,
            "logFirstLine": 1,
        }
        await manager.drop(run)
        await user.logs[uid].append_content("detached\n")
        assert len(messages) == 2
        assert root.get_log_snapshot()["logSeq"] == 0
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (one, two) if task is not None), return_exceptions=True
        )
        manager._running.pop(root.uid, None)
        root.clear_log_cursor()


@pytest.mark.asyncio
async def test_legacy_in_place_append_uses_line_baseline(monkeypatch):
    root, script, user, _, sent = await runtime(monkeypatch)
    await script.set_current_index(0)
    uid = user.logs.add(LogRecord, payload={"info": {"content": ["one\n"]}})
    await user.logs.commit()
    sent.reset_mock()
    # 旧专项在原列表追加，再用托管镜像触发配置通知。
    user.logs[uid].content.append("two\n")
    await script.set_log("one\ntwo\n")
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert packet.append and packet.log == "two\n"
    assert root.get_log_snapshot()["log"] == "one\ntwo\n"


@pytest.mark.asyncio
async def test_append_after_process_state_rollback_replaces_sent_baseline(monkeypatch):
    from app.config import config_manager

    root, script, user, _, sent = await runtime(monkeypatch)
    await script.set_current_index(0)
    uid = user.logs.add(LogRecord, payload={"info": {"content": ["one\n"]}})
    await user.logs.commit()
    with pytest.raises(ValueError, match="rollback"):
        async with config_manager.transaction():
            await user.logs[uid].append_content("discarded\n")
            raise ValueError("rollback")
    assert root.get_log_snapshot()["logSeq"] is None
    sent.reset_mock()
    await user.logs[uid].append_content("actual\n")
    packet = packets(sent, protocol.TASK_LOG_UPDATED)[0]
    assert not packet.append and packet.log == "one\nactual\n"
    assert root.get_log_snapshot()["logSeq"] == packet.seq


@pytest.mark.asyncio
async def test_legacy_flow_logs_are_visible_with_an_active_user_record(monkeypatch):
    root, script, user, manager, sent = await runtime(monkeypatch)
    script._manager_controls_users = True
    await script.set_current_index(0)
    record = user.logs.add(LogRecord)
    await user.logs.commit()
    sent.reset_mock()

    # 旧专项在建立本轮记录后、启动模拟器前更新托管展示日志。
    await script.set_log("starting device")
    messages = packets(sent, protocol.TASK_LOG_UPDATED)
    assert messages and messages[-1].log == "starting device"
    assert manager.get_runtime_snapshot().tasks[0].log == "starting device"
    assert root.current.log == "starting device"

    # 原生日志仍完整留在用户记录；由旧专项的既有镜像写入接管展示。
    await user.logs[record].set_state(content=["native one\n"])
    await script.set_log("native one\n")
    await user.logs[record].append_content("native two\n")
    await script.set_log("native one\nnative two\n")
    assert packets(sent, protocol.TASK_LOG_UPDATED)[-1].log == "native two\n"
    assert packets(sent, protocol.TASK_LOG_UPDATED)[-1].append
    await script.set_log("waiting for process shutdown")
    assert (
        packets(sent, protocol.TASK_LOG_UPDATED)[-1].log
        == "waiting for process shutdown"
    )
    assert manager.get_runtime_snapshot().tasks[0].log == "waiting for process shutdown"
    assert user.logs[record].content == ["native one\n", "native two\n"]
