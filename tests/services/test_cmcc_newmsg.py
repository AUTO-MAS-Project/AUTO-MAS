import asyncio
import json

import pytest

from app.services import cmcc_newmsg


class _Connection:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = [json.dumps(message) for message in messages]
        self.sent: list[dict] = []

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def recv(self) -> str:
        return self.messages.pop(0)


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *args) -> None:
        return None


def test_send_authenticates_and_uses_api_key_as_target(monkeypatch) -> None:
    connection = _Connection([{"type": "connected"}, {"type": "auth_ok"}])
    connect_kwargs = {}

    def connect(url, **kwargs):
        connect_kwargs.update(kwargs)
        assert url == cmcc_newmsg.SERVER_URL
        return _ConnectionContext(connection)

    monkeypatch.setattr(cmcc_newmsg.websockets, "connect", connect)
    message_ids = asyncio.run(
        cmcc_newmsg.send_cmcc_newmsg(
            api_key="ak_secret",
            content="测试通知",
            proxy=None,
        )
    )

    assert connect_kwargs["additional_headers"] == {"X-API-Key": "ak_secret"}
    assert connection.sent[0] == {
        "type": "auth",
        "apiKey": "ak_secret",
        "version": "2.0",
    }
    assert connection.sent[1]["type"] == "send"
    assert connection.sent[1]["to"] == "ak_secret"
    assert connection.sent[1]["content"] == "测试通知"
    assert message_ids == (connection.sent[1]["messageId"],)


def test_send_splits_long_text(monkeypatch) -> None:
    connection = _Connection([{"type": "auth_ok"}])
    monkeypatch.setattr(
        cmcc_newmsg.websockets,
        "connect",
        lambda *args, **kwargs: _ConnectionContext(connection),
    )

    message_ids = asyncio.run(
        cmcc_newmsg.send_cmcc_newmsg(
            api_key="app_secret",
            content="x" * (cmcc_newmsg.TEXT_CHUNK_LIMIT + 1),
        )
    )

    assert len(message_ids) == 2
    assert [len(message["content"]) for message in connection.sent[1:]] == [2000, 1]


def test_auth_failure_redacts_api_key(monkeypatch) -> None:
    connection = _Connection([{"type": "auth_failed", "message": "invalid ak_secret"}])
    monkeypatch.setattr(
        cmcc_newmsg.websockets,
        "connect",
        lambda *args, **kwargs: _ConnectionContext(connection),
    )

    with pytest.raises(cmcc_newmsg.CMCCNewMsgError) as exc_info:
        asyncio.run(
            cmcc_newmsg.send_cmcc_newmsg(
                api_key="ak_secret",
                content="测试通知",
            )
        )

    assert "ak_secret" not in str(exc_info.value)
    assert "invalid ***" in str(exc_info.value)
