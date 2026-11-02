"""QQ 普通接口调用与手动凭据更新契约。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import openclaw_qq as api
from app.core.notify.channels.openclaw_qq.transport import Sender, _RuntimeCredentials


@pytest.fixture
def credentials_app(monkeypatch):
    config = SimpleNamespace(update=AsyncMock(), get=lambda _key: None)
    sender = Sender(SimpleNamespace(config=config))
    sender._runtime_credentials = _RuntimeCredentials("app", "secret", "owner")
    sender._secret_storage_available = False
    sender._request_json = AsyncMock(return_value={"access_token": "mock"})
    sender._stop_gateway = AsyncMock()
    sender._start_gateway = AsyncMock()
    monkeypatch.setattr(api.Notify, "channel_sender", lambda _key: sender)
    app = FastAPI()
    app.include_router(api.router)
    return app, sender


@pytest.mark.asyncio
async def test_binding_actions_work_without_desktop_authorization(credentials_app):
    app, sender = credentials_app
    sender.groups = lambda: SimpleNamespace(
        binding_id="binding", target_type="c2c", group_command_whitelist=[], groups=[]
    )
    sender.set_target = AsyncMock()
    sender.start_login = AsyncMock(
        return_value=SimpleNamespace(
            session_id="session", qr_url="https://example.invalid/qr"
        )
    )
    sender.check_login = AsyncMock(
        return_value=SimpleNamespace(
            session_id="session", state="waiting", connected=False, message=""
        )
    )
    sender.unbind = AsyncMock()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        root = "/api/setting/openclaw-qq"
        status = await client.post(f"{root}/status")
        groups = await client.post(f"{root}/groups")
        target = await client.post(
            f"{root}/target",
            json={"bindingId": "binding", "targetType": "c2c"},
        )
        start = await client.post(f"{root}/login/start")
        check = await client.post(f"{root}/login/check", json={"sessionId": "session"})
        unbind = await client.post(f"{root}/unbind")
    assert all(
        response.status_code == 200 and response.json()["code"] == 200
        for response in (status, groups, target, start, check, unbind)
    )
    sender.set_target.assert_awaited_once()
    sender.start_login.assert_awaited_once()
    sender.check_login.assert_awaited_once_with(session_id="session")
    sender.unbind.assert_awaited_once()


@pytest.mark.asyncio
async def test_can_keep_secret_and_change_recipient_without_desktop_authorization(
    credentials_app,
):
    app, sender = credentials_app
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        details = await client.post("/api/setting/openclaw-qq/credentials/get")
        body = details.json()
        assert '"secret"' not in details.text and "test-token" not in details.text
        saved = await client.post(
            "/api/setting/openclaw-qq/credentials/set",
            json={
                "bindingId": body["bindingId"],
                "appId": body["appId"],
                "userOpenId": "other",
            },
        )
    assert saved.status_code == 200 and saved.json()["code"] == 200
    assert sender._credentials() == ("app", "secret", "other")


@pytest.mark.asyncio
async def test_invalid_credentials_preserve_existing_binding(credentials_app):
    _, sender = credentials_app
    original_id = sender._binding_id
    sender._request_json = AsyncMock(return_value={"error": "invalid"})
    with pytest.raises(ValueError, match="invalid_credentials"):
        await sender.set_credentials(
            binding_id=original_id,
            app_id="app",
            client_secret=None,
            user_openid="other",
        )
    assert sender._binding_id == original_id
    assert sender._credentials() == ("app", "secret", "owner")
    sender.dependencies.config.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_validation_does_not_block_sending_and_rechecks_binding(credentials_app):
    _, sender = credentials_app
    started, release = asyncio.Event(), asyncio.Event()

    async def validate(*_args, **_kwargs):
        started.set()
        await release.wait()
        return {"access_token": "mock"}

    sender._request_json = AsyncMock(side_effect=validate)
    task = asyncio.create_task(
        sender.set_credentials(
            binding_id=sender._binding_id,
            app_id="app",
            client_secret=None,
            user_openid="other",
        )
    )
    await asyncio.wait_for(started.wait(), 3)
    assert not sender._send_lock.locked()
    sender._binding_id = "new-binding"
    release.set()
    with pytest.raises(ValueError, match="binding_changed"):
        await task
    assert sender._credentials()[2] == "owner"


@pytest.mark.asyncio
async def test_cancelled_save_finishes_binding_and_gateway_transition(credentials_app):
    _, sender = credentials_app
    original_id = sender._binding_id
    started, release = asyncio.Event(), asyncio.Event()

    async def stop():
        started.set()
        await release.wait()

    sender._stop_gateway = AsyncMock(side_effect=stop)
    task = asyncio.create_task(
        sender.set_credentials(
            binding_id=original_id,
            app_id="app",
            client_secret=None,
            user_openid="other",
        )
    )
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert sender._send_lock.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sender._binding_id != original_id
    assert sender._credentials()[2] == "other"
    sender._start_gateway.assert_awaited_once_with("app", "secret")
