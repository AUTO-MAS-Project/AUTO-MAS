import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import openclaw_weixin as weixin


class FakeConfig:
    proxy = None
    VERSION = "v-test"

    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, group, name):
        assert group == "Notify"
        return self.values.get(name, "")

    async def update(self, data):
        self.values.update(data["Notify"])


def _session(manager):
    manager._sessions["session"] = weixin._QrSession(
        session_id="session",
        qrcode="qrcode",
        qr_url="qr-url",
        created_at=weixin.monotonic(),
    )


@pytest.mark.parametrize(
    ("values", "state"),
    [
        (
            {
                "OpenClawWeixinBotToken": "token",
                "OpenClawWeixinAccountId": "account",
                "OpenClawWeixinTargetUserId": "user",
            },
            "connected",
        ),
        (
            {
                "OpenClawWeixinBotToken": "token",
                "OpenClawWeixinAccountId": "account",
            },
            "error",
        ),
    ],
)
def test_binded_redirect_uses_the_same_complete_credential_definition(
    monkeypatch, values, state
):
    config = FakeConfig(values)
    monkeypatch.setattr(weixin, "Config", config)
    manager = weixin.OpenClawWeixinManager()
    _session(manager)
    manager._request_json = AsyncMock(return_value={"status": "binded_redirect"})

    result = asyncio.run(manager.check_login("session"))

    assert result.state == state
    assert result.connected == (state == "connected")


def test_incomplete_token_is_not_sent_to_a_new_qr_session(monkeypatch):
    monkeypatch.setattr(
        weixin,
        "Config",
        FakeConfig({"OpenClawWeixinBotToken": "stale-token"}),
    )
    manager = weixin.OpenClawWeixinManager()
    manager._request_json = AsyncMock(
        return_value={"qrcode": "qrcode", "qrcode_img_content": "qr-url"}
    )

    asyncio.run(manager.start_login())

    assert manager._request_json.await_args.kwargs["body"] == {"local_token_list": []}


def test_saving_credentials_does_not_change_notification_enable_state(monkeypatch):
    config = FakeConfig({"IfOpenClawWeixin": False})
    monkeypatch.setattr(weixin, "Config", config)
    manager = weixin.OpenClawWeixinManager()
    manager._secret_storage_available = False

    asyncio.run(
        manager._save_credentials(
            token="token",
            account_id="account",
            user_id="user",
            base_url=None,
        )
    )

    assert config.values["IfOpenClawWeixin"] is False


@pytest.mark.parametrize(
    ("status_code", "state"),
    [(503, "waiting"), (404, "error")],
)
def test_qr_http_errors_have_retryable_states(monkeypatch, status_code, state):
    monkeypatch.setattr(weixin, "Config", FakeConfig())
    manager = weixin.OpenClawWeixinManager()
    _session(manager)
    manager._request_json = AsyncMock(
        side_effect=weixin.RemoteHTTPError(status_code, f"HTTP {status_code}")
    )

    result = asyncio.run(manager.check_login("session"))

    assert result.state == state
