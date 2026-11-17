"""QQ 入站命令的帮助、配置查询、调度请求及访问控制。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio

from app.config import ConfigCollection
from app.core import Config, TaskManager
from app.core.notify.channels.openclaw_qq import transport
from app.core.notify.commands import execute_notification_command
from app.models.config import GeneralConfig, QueueConfig, ScriptConfigType
from app.models.notification.channel import QQSessionDependencies
from app.models.task import TaskMode


def message(content, *, group=False, author="owner", age=0, message_id=None):
    return {
        "id": message_id or uuid4().hex,
        "content": f"<@!bot> {content}" if group else content,
        "author": {"member_openid" if group else "user_openid": author},
        "group_openid": "group-1",
        "timestamp": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
    }


@pytest_asyncio.fixture
async def commands(monkeypatch):
    scripts = ConfigCollection[ScriptConfigType].build([GeneralConfig])
    queues = ConfigCollection[QueueConfig].build([QueueConfig])
    await scripts.activate()
    await queues.activate()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "QueueConfig", queues)
    start = AsyncMock(return_value=uuid4())
    monkeypatch.setattr(TaskManager, "start", start)
    values = {
        "IfOpenClawQQ": True,
        "OpenClawQQAppId": "test-app",
        "OpenClawQQClientSecret": "test-secret",
        "OpenClawQQTargetOpenId": "owner",
        "OpenClawQQTargetType": "all",
        "OpenClawQQGroupOpenIds": ["group-1"],
        "OpenClawQQRejectedGroupOpenIds": [],
        "OpenClawQQGroupCommandWhitelist": ["allowed-member"],
    }
    sender = transport.Sender(
        QQSessionDependencies(
            config=SimpleNamespace(get=values.__getitem__),
            read_proxy=lambda: None,
            http_factory=Mock(side_effect=AssertionError("unexpected HTTP client")),
            websocket_connect=Mock(side_effect=AssertionError("unexpected gateway")),
            notification_command_executor=execute_notification_command,
        )
    )
    request = AsyncMock()
    monkeypatch.setattr(sender, "_request_with_token", request)
    monkeypatch.setattr(transport, "GROUP_MESSAGE_INTERVAL_SECONDS", 0)
    return SimpleNamespace(
        sender=sender,
        scripts=scripts,
        queues=queues,
        config=values,
        start=start,
        request=request,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("帮助", ("retry", "start", "myid")),
        ("/HeLp", ("retry", "start", "myid")),
        ("重试", ("retry help", "retry list")),
        ("retry HELP", ("retry help", "retry list")),
        ("重试 帮助", ("retry help", "retry list")),
        ("启动队列", ("start help", "start list")),
        ("/start help", ("start help", "start list")),
        ("启动队列 帮助", ("start help", "start list")),
    ],
)
async def test_help_shows_command_usage_without_starting(commands, content, expected):
    await commands.sender._handle_command(message(content))

    reply = commands.request.await_args.kwargs["body"]["content"]
    assert all(command in reply for command in expected)
    commands.start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "kind"),
    [
        ("重试 列表", "script"),
        ("/ReTrY LIST", "script"),
        ("启动队列 list", "queue"),
        ("start 列表", "queue"),
    ],
)
async def test_list_reads_only_corresponding_config_names(commands, content, kind):
    commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "MAA Main Script"}})
    commands.queues.add(QueueConfig, payload={"Info": {"Name": "Daily Queue"}})
    await commands.scripts.commit()
    await commands.queues.commit()

    await commands.sender._handle_command(message(content))

    reply = commands.request.await_args.kwargs["body"]["content"]
    included, excluded = (
        ("MAA Main Script", "Daily Queue")
        if kind == "script"
        else ("Daily Queue", "MAA Main Script")
    )
    assert included in reply and excluded not in reply
    commands.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_lists_and_duplicate_names_do_not_schedule(commands):
    await commands.sender._handle_command(message("retry list"))
    assert "尚未配置托管" in commands.request.await_args.kwargs["body"]["content"]
    await commands.sender._handle_command(message("start list"))
    assert "尚未配置队列" in commands.request.await_args.kwargs["body"]["content"]
    for _ in range(2):
        commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "duplicate"}})
    await commands.scripts.commit()

    await commands.sender._handle_command(message("retry list"))
    reply = commands.request.await_args.kwargs["body"]["content"]
    assert reply.count("duplicate") == 2
    assert "同名" in reply
    await commands.sender._handle_command(message("retry duplicate"))
    assert "同名" in commands.request.await_args.kwargs["body"]["content"]
    commands.start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "kind", "name"),
    [
        ("重试 MAA Main Script", "script", "MAA Main Script"),
        ("/RETRY MAA Main Script", "script", "MAA Main Script"),
        ("启动队列 Daily Queue", "queue", "Daily Queue"),
        ("/START Daily Queue", "queue", "Daily Queue"),
        ("retry -- help", "script", "help"),
        ("start -- list", "queue", "list"),
        ("retry -- -- help", "script", "-- help"),
    ],
)
async def test_aliases_and_literal_names_preserve_exact_target(
    commands, content, kind, name
):
    collection = commands.scripts if kind == "script" else commands.queues
    model = GeneralConfig if kind == "script" else QueueConfig
    uid = collection.add(model, payload={"Info": {"Name": name}})
    await collection.commit()
    data = message(content)

    await commands.sender._handle_command(data)
    await commands.sender._handle_command(data)

    selection = (
        {"uid": "-", "children": {0: {"uid": str(uid)}}}
        if kind == "script"
        else {"uid": str(uid)}
    )
    commands.start.assert_awaited_once_with(TaskMode.AUTO_PROXY, {0: selection})
    assert commands.request.await_count == 1
    body = commands.request.await_args.kwargs["body"]
    assert body["msg_id"] == data["id"]
    if kind == "queue":
        assert "运行一次" in body["content"]


@pytest.mark.asyncio
async def test_unknown_exact_name_and_start_failure_give_feedback(commands):
    commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "Main Script"}})
    await commands.scripts.commit()
    await commands.sender._handle_command(message("retry main script"))
    assert "retry list" in commands.request.await_args.kwargs["body"]["content"]
    commands.start.assert_not_awaited()
    commands.start.side_effect = RuntimeError("task busy")

    await commands.sender._handle_command(message("retry Main Script"))

    assert "暂时无法启动" in commands.request.await_args.kwargs["body"]["content"]


@pytest.mark.asyncio
async def test_option_like_existing_name_is_not_changed_to_another_target(commands):
    uid = commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "-- alpha"}})
    commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "alpha"}})
    await commands.scripts.commit()

    await commands.sender._handle_command(message("retry -- alpha"))

    commands.start.assert_awaited_once_with(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(uid)}}}}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", ["help", "retry list", "start list", "retry private"]
)
async def test_help_lists_and_execution_share_identity_and_freshness_checks(
    commands, content
):
    commands.scripts.add(GeneralConfig, payload={"Info": {"Name": "private"}})
    await commands.scripts.commit()
    for data, group in [
        (message(content, author="stranger"), False),
        (message(content, group=True, author="stranger"), True),
        (message(content, age=301), False),
    ]:
        await commands.sender._handle_command(data, group=group)
    commands.config["IfOpenClawQQ"] = False
    await commands.sender._handle_command(message(content))
    commands.start.assert_not_awaited()
    commands.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_help_list_and_identity_follow_existing_permissions(commands):
    for content in ("/HELP", "retry list", "start list"):
        await commands.sender._handle_command(
            message(content, group=True, author="allowed-member"), group=True
        )
        assert (
            "/groups/group-1/messages" in commands.request.await_args.kwargs["endpoint"]
        )
    for content in ("我的ID", "/MYID"):
        await commands.sender._handle_command(
            message(content, group=True, author="stranger"), group=True
        )
        assert "stranger" in commands.request.await_args.kwargs["body"]["content"]
    count = commands.request.await_count
    await commands.sender._handle_command(message("myid"))
    assert commands.request.await_count == count

    commands.config["OpenClawQQGroupCommandWhitelist"] = []
    await commands.sender._handle_command(
        message("help", group=True, author="stranger"), group=True
    )
    assert commands.request.await_count == count + 1
    commands.config["OpenClawQQRejectedGroupOpenIds"] = ["group-1"]
    await commands.sender._handle_command(
        message("retry list", group=True, author="allowed-member"), group=True
    )
    assert commands.request.await_count == count + 1
    commands.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_list_is_paginated_with_one_reply_per_request(commands):
    names = [f"托管-{i}-" + "a" * 150 for i in range(120)]
    for name in names:
        commands.scripts.add(GeneralConfig, payload={"Info": {"Name": name}})
    await commands.scripts.commit()
    data = message("retry list")

    await commands.sender._handle_command(data)

    body = commands.request.await_args.kwargs["body"]
    assert commands.request.await_count == 1
    assert body["msg_id"] == data["id"] and body["msg_seq"] == 1
    assert "retry list 2" in body["content"]
    page_count = int(body["content"].split("/", 1)[1].split()[0])
    assert page_count > 5
    for page in range(2, page_count + 1):
        data = message(f"retry list {page}")
        await commands.sender._handle_command(data)
        assert commands.request.await_count == page
        body = commands.request.await_args.kwargs["body"]
        assert body["msg_id"] == data["id"] and body["msg_seq"] == 1
    bodies = [call.kwargs["body"] for call in commands.request.await_args_list]
    assert all(len(body["content"]) <= transport.TEXT_CHUNK_LIMIT for body in bodies)
    reply = "\n".join(body["content"] for body in bodies)
    assert all(name in reply for name in names)
    commands.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_list_page_and_escaped_page_like_name(commands):
    uid = commands.queues.add(QueueConfig, payload={"Info": {"Name": "list 2"}})
    for name in ("list -1", "list invalid", "help example"):
        commands.queues.add(QueueConfig, payload={"Info": {"Name": name}})
    await commands.queues.commit()
    for content in (
        "start list 0",
        "start 列表 999",
        "start list -1",
        "start list invalid",
    ):
        await commands.sender._handle_command(message(content))
        assert "页码无效" in commands.request.await_args.kwargs["body"]["content"]
    await commands.sender._handle_command(message("start help example"))
    assert "start help" in commands.request.await_args.kwargs["body"]["content"]
    commands.start.assert_not_awaited()

    await commands.sender._handle_command(message("start -- list 2"))
    commands.start.assert_awaited_once_with(TaskMode.AUTO_PROXY, {0: {"uid": str(uid)}})
