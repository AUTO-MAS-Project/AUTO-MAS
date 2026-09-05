import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import openclaw_qq as qq
from app.utils.platform.common.errors import UnsupportedPlatformError


class FakeConfig:
    proxy = None

    def __init__(self):
        self.values = {}
        self.fail_secret = False

    async def update(self, data):
        if self.fail_secret and "OpenClawQQClientSecret" in data["Notify"]:
            raise UnsupportedPlatformError("secret")
        self.values.update(data["Notify"])


@pytest.mark.parametrize(
    "persistent,fail_secret", [(True, False), (False, False), (True, True)]
)
def test_save_credentials_storage_modes(monkeypatch, persistent, fail_secret):
    config = FakeConfig()
    config.fail_secret = fail_secret
    monkeypatch.setattr(qq, "Config", config)
    manager = qq.OpenClawQQManager()
    manager._secret_storage_available = persistent
    manager._access_token = "old-token"
    asyncio.run(
        manager._save_credentials(
            app_id="new-app", client_secret="secret", user_openid="user"
        )
    )
    assert config.values["IfOpenClawQQ"] is True
    assert manager._access_token == ""
    if persistent and not fail_secret:
        assert config.values["OpenClawQQClientSecret"] == "secret"
        assert manager._runtime_credentials is None
    else:
        assert "OpenClawQQClientSecret" not in config.values
        assert manager._credentials() == ("new-app", "secret", "user")


def test_rebind_waits_for_inflight_send_and_discards_old_token(monkeypatch):
    monkeypatch.setattr(qq, "Config", FakeConfig())
    manager = qq.OpenClawQQManager()
    manager._secret_storage_available = False

    async def run():
        async with manager._send_lock:
            saving = asyncio.create_task(
                manager._save_credentials(
                    app_id="new", client_secret="secret", user_openid="user"
                )
            )
            await asyncio.sleep(0)
            assert not saving.done()
            manager._access_token = "old-account-token"
        await asyncio.wait_for(saving, timeout=1)
        assert manager._access_token == ""
        assert manager._credentials()[0] == "new"

    asyncio.run(run())


def test_unbind_waits_for_send(monkeypatch):
    config = FakeConfig()
    monkeypatch.setattr(qq, "Config", config)
    manager = qq.OpenClawQQManager()
    manager._secret_storage_available = False
    manager._runtime_credentials = qq._RuntimeCredentials("app", "secret", "user")

    async def run():
        async with manager._send_lock:
            unbinding = asyncio.create_task(manager.unbind())
            await asyncio.sleep(0)
            assert not unbinding.done()
        await asyncio.wait_for(unbinding, timeout=1)
        assert manager._runtime_credentials is None
        assert config.values["IfOpenClawQQ"] is False

    asyncio.run(run())


def test_token_cache_reused_until_expiry():
    manager = qq.OpenClawQQManager()
    manager._request_json = AsyncMock(
        return_value={"access_token": "token", "expires_in": 7200}
    )

    async def run():
        assert await manager._ensure_access_token("app", "secret") == "token"
        assert await manager._ensure_access_token("app", "secret") == "token"
        assert manager._request_json.await_count == 1
        manager._access_token_expires_at = 0
        await manager._ensure_access_token("app", "secret")
        assert manager._request_json.await_count == 2

    asyncio.run(run())
