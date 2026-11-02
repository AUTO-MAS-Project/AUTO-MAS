"""手动 QQ 凭据只允许受信任的本机桌面客户端访问。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import openclaw_qq as api
from app.api import setting
from app.core.notify.channels.openclaw_qq.transport import Sender, _RuntimeCredentials


@pytest.fixture
def credentials_app(monkeypatch):
    monkeypatch.setenv("AUTO_MAS_INSTALL_TOKEN", "test-token")
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
    app.include_router(setting.router)
    return app, sender


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("peer", "host", "headers"),
    [
        ("127.0.0.1", "127.0.0.1", {}),
        ("127.0.0.1", "127.0.0.1", {"Authorization": "Bearer wrong"}),
        ("203.0.113.10", "127.0.0.1", {"Authorization": "Bearer test-token"}),
        ("127.0.0.1", "example.invalid", {"Authorization": "Bearer test-token"}),
        (
            "127.0.0.1",
            "127.0.0.1",
            {"Authorization": "Bearer test-token", "Origin": "https://example.invalid"},
        ),
    ],
)
async def test_untrusted_requests_cannot_read_or_change_credentials(
    credentials_app, peer, host, headers
):
    app, sender = credentials_app
    transport = httpx.ASGITransport(app=app, client=(peer, 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://{host}"
    ) as client:
        details = await client.post(
            "/api/setting/openclaw-qq/credentials/get", headers=headers
        )
        saved = await client.post(
            "/api/setting/openclaw-qq/credentials/set",
            headers=headers,
            json={
                "bindingId": sender._binding_id,
                "appId": "app",
                "userOpenId": "other",
            },
        )
    assert details.status_code == saved.status_code == 403
    assert sender._credentials()[2] == "owner"
    sender._request_json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/groups", "/status", "/target", "/unbind", "/login/start", "/login/check"]
)
async def test_other_binding_routes_reject_unauthorized_clients(credentials_app, path):
    app, _ = credentials_app
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(f"/api/setting/openclaw-qq{path}", json={})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_backup_requires_local_desktop_authority(
    credentials_app, monkeypatch, tmp_path
):
    app, _ = credentials_app
    backup = tmp_path / "backup.zip"
    backup.write_bytes(b"test backup")
    create = AsyncMock(return_value=backup)
    monkeypatch.setattr(setting.Config, "create_data_backup", create)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        assert (await client.get("/api/setting/backup")).status_code == 403
        create.assert_not_awaited()
        response = await client.get(
            "/api/setting/backup", headers={"Authorization": "Bearer test-token"}
        )
    assert response.status_code == 200 and response.content == b"test backup"
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_token_does_not_enable_access(credentials_app, monkeypatch):
    app, _ = credentials_app
    monkeypatch.delenv("AUTO_MAS_INSTALL_TOKEN")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        assert (
            await client.post("/api/setting/openclaw-qq/credentials/get")
        ).status_code == 403
        assert (await client.get("/api/setting/backup")).status_code == 403


@pytest.mark.asyncio
async def test_authorized_desktop_binding_actions_still_work(credentials_app):
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
    headers = {"Authorization": "Bearer test-token"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        root = "/api/setting/openclaw-qq"
        status = await client.post(f"{root}/status", headers=headers)
        groups = await client.post(f"{root}/groups", headers=headers)
        target = await client.post(
            f"{root}/target",
            headers=headers,
            json={"bindingId": "binding", "targetType": "c2c"},
        )
        start = await client.post(f"{root}/login/start", headers=headers)
        check = await client.post(
            f"{root}/login/check", headers=headers, json={"sessionId": "session"}
        )
        unbind = await client.post(f"{root}/unbind", headers=headers)
    assert all(
        response.status_code == 200 and response.json()["code"] == 200
        for response in (status, groups, target, start, check, unbind)
    )
    sender.set_target.assert_awaited_once()
    sender.start_login.assert_awaited_once()
    sender.check_login.assert_awaited_once_with(session_id="session")
    sender.unbind.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorized_desktop_can_keep_secret_and_change_recipient(credentials_app):
    app, sender = credentials_app
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    headers = {"Authorization": "Bearer test-token"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        details = await client.post(
            "/api/setting/openclaw-qq/credentials/get", headers=headers
        )
        body = details.json()
        assert '"secret"' not in details.text and "test-token" not in details.text
        saved = await client.post(
            "/api/setting/openclaw-qq/credentials/set",
            headers=headers,
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
