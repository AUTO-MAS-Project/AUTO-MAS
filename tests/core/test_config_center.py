"""配置中心宿主装配、共享授权状态与配置提交契约。"""

import asyncio
import json

import httpx
import pytest
import pytest_asyncio
import yaml
from fastapi import FastAPI

from app.config import ConfigCollection, ConfigError, config_manager
from app.models.config import GeneralConfig, GlobalConfig
from tests.config_support import activate_config


@pytest_asyncio.fixture
async def host_config(tmp_path, monkeypatch):
    # 首次装配可能创建宿主目录，只允许落到临时目录。
    monkeypatch.chdir(tmp_path)
    from app.core import config_center as host
    from app.core import general_share
    from app.core.config import AppConfig

    config = AppConfig.__new__(AppConfig)
    config.setting = GlobalConfig.build()
    config.ScriptConfig = ConfigCollection.build([GeneralConfig])
    await activate_config(config.setting, tmp_path / "setting.yaml")
    await activate_config(config.ScriptConfig)
    monkeypatch.setattr(host, "Config", config)
    monkeypatch.setattr(general_share, "Config", config)
    # 使用生产装配的对象，测试后还原其原始状态，避免事件循环与授权串用。
    client = host.config_center_client
    monkeypatch.setattr(
        client, "__dict__", {**client.__dict__, "_lock": asyncio.Lock()}
    )
    return host, config


@pytest.mark.asyncio
async def test_record_adapter_obeys_transaction_rollback_and_persistence(host_config):
    host, config = host_config
    store = host._HostAppearanceUploads()
    content = json.dumps({"author": {"theme": {"fileId": 7}}})
    config.setting.Data.Notice = '{"unrelated": true}'
    await config.setting.commit()

    async def read_in_another_task():
        return store.read()

    with pytest.raises(RuntimeError):
        async with config_manager.transaction():
            await store.write(content)
            assert json.loads(store.read())["author"]["theme"]["fileId"] == 7
            assert await asyncio.create_task(read_in_another_task()) == "{}"
            raise RuntimeError("rollback")
    assert store.read() == "{}"
    await store.write(content)
    assert json.loads(store.read())["author"]["theme"]["fileId"] == 7
    assert json.loads(config.setting.Data.Notice) == {"unrelated": True}
    await config_manager.flush()
    saved = yaml.safe_load(config.setting.persist_path.read_text(encoding="utf-8"))
    assert (
        json.loads(saved["Data"]["ShareAppearanceUploads"])["author"]["theme"]["fileId"]
        == 7
    )


@pytest.mark.asyncio
async def test_record_adapter_honors_config_lock(host_config):
    host, config = host_config
    store = host._HostAppearanceUploads()
    ticket = await config.setting.lock_s()
    try:
        with pytest.raises(ConfigError):
            await store.write('{"author": {}}')
        assert store.read() == "{}"
    finally:
        await config.setting.unlock(ticket)
    await store.write('{"author": {}}')
    assert json.loads(store.read()) == {"author": {}}


@pytest.mark.asyncio
async def test_host_reads_current_proxy_and_replaced_settings(host_config, monkeypatch):
    host, config = host_config
    original = httpx.AsyncClient
    proxies = []

    def create(**kwargs):
        proxy = kwargs.pop("proxy")
        proxies.append(str(proxy.url) if proxy else None)
        return original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"data": {}})
            ),
            **kwargs,
        )

    monkeypatch.setattr(httpx, "AsyncClient", create)
    client = host.config_center_client
    await client.list_templates(page=1, page_size=1, keyword=None)
    config.setting.Update.ProxyAddress = "127.0.0.1:8123"
    await config.setting.commit()
    await client.list_templates(page=1, page_size=1, keyword=None)
    replacement = GlobalConfig.build()
    await activate_config(replacement)
    config.setting = replacement
    await client.list_templates(page=1, page_size=1, keyword=None)
    assert proxies == [None, "http://127.0.0.1:8123", None]
    assert host._HostAppearanceUploads().read() == "{}"


@pytest.mark.asyncio
async def test_share_api_and_general_upload_use_one_authorized_client(
    host_config, monkeypatch
):
    host, config = host_config
    from app.api import share
    from app.api.scripts import sharing
    from app.core.general_share import general_share_service

    assert share.config_center_client is host.config_center_client
    assert general_share_service._config_center is host.config_center_client
    script_id = config.ScriptConfig.add(GeneralConfig)
    await config.ScriptConfig.commit()
    original = httpx.AsyncClient
    requests = []
    reject_upload = False

    def handler(request):
        requests.append(request)
        path = request.url.path
        if request.url.host == "data.auto-mas.top":
            return httpx.Response(
                307,
                headers={"Location": str(request.url).replace("data.", "data2.", 1)},
            )
        if path.endswith("/auth/device/code"):
            data = {"device_code": "test-device", "user_code": "TEST"}
        elif path.endswith("/auth/device/token"):
            data = {
                "status": "authorized",
                "access_token": "test-token",
                "expires_in": 1800,
                "username": "author",
            }
        elif path.endswith("/user/files"):
            assert request.headers["Authorization"] == "Bearer test-token"
            assert b"GeneralConfig" in request.content
            if reject_upload:
                return httpx.Response(401, json={})
            data = {"id": 7}
        else:
            raise AssertionError(request.url)
        return httpx.Response(200, json={"data": data})

    def create(**kwargs):
        kwargs.pop("proxy")
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", create)
    host.config_center_client._api_base = "https://data.auto-mas.top/api/v1"
    app = FastAPI()
    app.include_router(share.router)
    app.include_router(sharing.router, prefix="/scripts")
    async with original(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as web:
        assert (await web.post("/api/share/auth/start")).json()[
            "authStatus"
        ] == "pending"
        assert (await web.post("/api/share/auth/poll")).json()[
            "authStatus"
        ] == "authorized"
        payload = {
            "scriptId": str(script_id),
            "config_name": "test",
            "description": "test",
            "acknowledged": True,
        }
        result = await web.post("/scripts/Upload/web", json=payload)
        assert result.json()["status"] == "success"
        assert (await web.post("/api/share/auth/status")).json()["username"] == "author"
        reject_upload = True
        assert (await web.post("/scripts/Upload/web", json=payload)).json()[
            "status"
        ] == "error"
        assert (await web.post("/api/share/auth/status")).json()["authStatus"] == "idle"
    assert [request.url.host for request in requests] == [
        "data.auto-mas.top",
        "data2.auto-mas.top",
        "data2.auto-mas.top",
        "data2.auto-mas.top",
        "data2.auto-mas.top",
    ]
