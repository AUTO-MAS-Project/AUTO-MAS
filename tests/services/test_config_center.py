"""配置中心的授权、请求状态和外观上传契约，全部使用替代 HTTP transport。"""

import asyncio
import io
import json
import os
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.services import config_center as service
from app.services.config_center_errors import ConfigCenterError


class UploadStore:
    def __init__(self):
        self.content = "{}"
        self.writes = 0
        self.fail_write = False

    def read(self):
        return self.content

    async def write(self, content):
        self.writes += 1
        if self.fail_write:
            raise OSError("isolated write failure")
        self.content = content


@pytest.fixture
def uploads():
    return UploadStore()


@pytest.fixture
def client(uploads):
    return service.ConfigCenterClient(
        get_proxy=lambda: None, appearance_uploads=uploads
    )


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    options = []

    def install(handler):
        def create(**kwargs):
            options.append(kwargs.copy())
            kwargs.pop("proxy")
            return original(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(service.httpx, "AsyncClient", create)
        return options

    return install


def reply(data):
    return httpx.Response(200, json={"data": data})


def auth_reply(request):
    if request.url.path.endswith("/auth/device/code"):
        return reply({"device_code": "device", "user_code": "TEST", "expires_in": 600})
    if request.url.path.endswith("/auth/device/token"):
        return reply(
            {
                "status": "authorized",
                "access_token": "test-token",
                "expires_in": 1800,
                "username": "author",
            }
        )
    raise AssertionError(request.url)


async def authorize(client):
    await client.start_authorization()
    assert (await client.poll_authorization())["status"] == "authorized"


@pytest.mark.asyncio
async def test_authorization_start_is_serialized(client, transport):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    active = 0
    maximum = 0

    async def handler(request):
        nonlocal calls, active, maximum
        calls += 1
        active += 1
        maximum = max(maximum, active)
        entered.set()
        await release.wait()
        active -= 1
        return reply({"device_code": str(calls), "user_code": str(calls)})

    transport(handler)
    first = asyncio.create_task(client.start_authorization())
    await asyncio.wait_for(entered.wait(), 2)
    second = asyncio.create_task(client.start_authorization())
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert calls == 2
    assert maximum == 1
    assert client.get_status()["userCode"] == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [False, True])
async def test_cancel_discards_inflight_poll_result(client, transport, restart):
    entered = asyncio.Event()
    release = asyncio.Event()
    starts = 0

    async def handler(request):
        nonlocal starts
        if request.url.path.endswith("/auth/device/code"):
            starts += 1
            return reply({"device_code": str(starts), "user_code": str(starts)})
        entered.set()
        await release.wait()
        return auth_reply(request)

    transport(handler)
    await client.start_authorization()
    poll = asyncio.create_task(client.poll_authorization())
    await asyncio.wait_for(entered.wait(), 2)
    await asyncio.wait_for(client.cancel_authorization(), 2)
    if restart:
        await client.start_authorization()
    release.set()
    result = await asyncio.wait_for(poll, 2)
    assert result["status"] == ("pending" if restart else "idle")
    assert client.get_status() == result
    with pytest.raises(ConfigCenterError) as error:
        await client.upload_config(display_name="test", description="test", config={})
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_cancelled_request_releases_authorization_lock(client, transport):
    entered = asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()
        return auth_reply(request)

    transport(handler)
    start = asyncio.create_task(client.start_authorization())
    await asyncio.wait_for(entered.wait(), 2)
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start
    assert client.get_status()["status"] == "idle"
    await asyncio.wait_for(authorize(client), 2)


@pytest.mark.asyncio
async def test_concurrent_polls_share_authorized_state(client, transport):
    entered = asyncio.Event()
    release = asyncio.Event()
    polls = 0

    async def handler(request):
        nonlocal polls
        if request.url.path.endswith("/auth/device/token"):
            polls += 1
            if polls == 2:
                entered.set()
            await release.wait()
        return auth_reply(request)

    transport(handler)
    await client.start_authorization()
    tasks = [asyncio.create_task(client.poll_authorization()) for _ in range(2)]
    await asyncio.wait_for(entered.wait(), 2)
    release.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), 2)
    assert [result["status"] for result in results] == ["authorized", "authorized"]
    assert client.get_status()["username"] == "author"


@pytest.mark.asyncio
async def test_proxy_is_read_for_json_and_both_streaming_paths(uploads, transport):
    proxy = None
    client = service.ConfigCenterClient(
        get_proxy=lambda: proxy, appearance_uploads=uploads
    )

    def handler(request):
        if request.url.path.endswith("/download"):
            return httpx.Response(200, json={"Script": {}})
        if request.url.path.endswith("/cover"):
            assert request.headers["Authorization"] == "Bearer test-token"
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nimage")
        if request.url.path.endswith("/files"):
            return reply({"items": []})
        return auth_reply(request)

    options = transport(handler)
    assert options == []
    await authorize(client)
    proxy = httpx.Proxy("http://127.0.0.1:8123")
    await client.list_templates(page=1, page_size=20, keyword=None)
    proxy = httpx.Proxy("socks5://127.0.0.1:8124")
    assert await client.download_template("test", None) == {"Script": {}}
    proxy = None
    assert (await client.get_my_appearance_cover(1, None))["dataUrl"].startswith(
        "data:image/png;base64,"
    )
    assert [
        str(option["proxy"].url) if option["proxy"] else None for option in options
    ] == [
        None,
        None,
        "http://127.0.0.1:8123",
        "socks5://127.0.0.1:8124",
        None,
    ]


@pytest.mark.asyncio
async def test_redirect_memory_and_token_survive_requests(client, transport):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "data.auto-mas.top":
            return httpx.Response(
                307,
                headers={"Location": str(request.url).replace("data.", "data2.", 1)},
            )
        if request.url.path.endswith("/user/files"):
            assert request.headers["Authorization"] == "Bearer test-token"
            return reply({"id": 1})
        return auth_reply(request)

    transport(handler)
    # 部署环境可覆盖地址；这里固定分享站域名以验证真实跳转钩子。
    client._api_base = "https://data.auto-mas.top/api/v1"
    await authorize(client)
    await client.upload_config(display_name="test", description="test", config={})
    assert [request.url.host for request in seen] == [
        "data.auto-mas.top",
        "data2.auto-mas.top",
        "data2.auto-mas.top",
        "data2.auto-mas.top",
    ]


@pytest.fixture
def appearance(tmp_path):
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    path = tmp_path / "theme.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "theme.json",
            json.dumps(
                {"formatVersion": 1, "id": "test-theme", "preview": "cover.png"}
            ),
        )
        archive.writestr("cover.png", image.getvalue())
    return str(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, 401, 409, 413, "network", "cancel"])
async def test_upload_failure_does_not_write_records(
    client, uploads, transport, appearance, failure
):
    def handler(request):
        if request.url.path.endswith("/user/files"):
            if failure == "network":
                raise httpx.ConnectError("offline", request=request)
            if failure == "cancel":
                raise asyncio.CancelledError()
            if failure is not None:
                return httpx.Response(failure, json={"message": "rejected"})
            assert request.headers["Authorization"] == "Bearer test-token"
            return reply(
                {"id": 7, "file_key": "theme-key", "version": {"version_no": 1}}
            )
        return auth_reply(request)

    transport(handler)
    await authorize(client)
    operation = client.upload_appearance(
        zip_path=appearance,
        display_name="test",
        description="test",
        change_note="test",
        file_id=None,
    )
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await operation
    elif failure is not None:
        with pytest.raises(ConfigCenterError) as error:
            await operation
        assert error.value.status_code == (503 if failure == "network" else failure)
    else:
        assert (await operation)["fileId"] == 7
    assert uploads.writes == (1 if failure is None else 0)
    assert bool(client.list_appearance_uploads()) == (failure is None)
    assert client.get_status()["status"] == ("idle" if failure == 401 else "authorized")


@pytest.mark.asyncio
async def test_remote_success_survives_local_record_failure(
    client, uploads, transport, appearance
):
    def handler(request):
        if request.url.path.endswith("/user/files"):
            return reply({"id": 7, "version": {"version_no": 1}})
        return auth_reply(request)

    transport(handler)
    await authorize(client)
    uploads.fail_write = True
    result = await client.upload_appearance(
        zip_path=appearance,
        display_name="test",
        description="test",
        change_note="test",
        file_id=None,
    )
    assert result["fileId"] == 7
    assert result["versionNo"] == 1
    assert uploads.writes == 1
    assert uploads.content == "{}"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 409])
async def test_missing_remote_file_only_forgets_matching_local_records(
    client, uploads, transport, appearance, status
):
    records = {"old": {"fileId": 7}, "same": {"fileId": "7"}, "keep": {"fileId": 8}}
    uploads.content = json.dumps({"author": records, "other": {"old": {"fileId": 7}}})

    def handler(request):
        if request.url.path.endswith("/user/files/7"):
            return httpx.Response(status, json={})
        return auth_reply(request)

    transport(handler)
    await authorize(client)
    with pytest.raises(ConfigCenterError) as error:
        await client.upload_appearance(
            zip_path=appearance,
            display_name="test",
            description="test",
            change_note="test",
            file_id=7,
            cover_mode="inherit",
        )
    assert error.value.status_code == status
    saved = json.loads(uploads.content)
    assert saved["author"] == (
        {"keep": {"fileId": 8}} if status in (403, 404) else records
    )
    assert saved["other"] == {"old": {"fileId": 7}}


@pytest.mark.asyncio
async def test_corrupt_and_other_account_records_do_not_leak(
    client, uploads, transport
):
    transport(auth_reply)
    await authorize(client)
    for content in ("invalid", "[]", '{"other": {"test": {"fileId": 1}}}'):
        uploads.content = content
        assert client.list_appearance_uploads() == []


def test_service_import_and_injected_operations_never_resolve_host(tmp_path):
    root = str(Path(__file__).resolve().parents[2])
    script = textwrap.dedent(
        """
        import asyncio
        import importlib.abc
        import sys
        attempts = []
        class DenyHost(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "app.core" or fullname.startswith(("app.core.", "app.api", "app.task")):
                    attempts.append(fullname)
                    raise AssertionError("service resolved host: " + fullname)
        sys.meta_path.insert(0, DenyHost())
        import app.services as exports
        from app.services import config_center as service
        class Store:
            def read(self): return "{}"
            async def write(self, content): pass
        async def main():
            client = service.ConfigCenterClient(get_proxy=lambda: None, appearance_uploads=Store())
            async def handler(request):
                return service.httpx.Response(200, json={"data": {"items": []}})
            original = service.httpx.AsyncClient
            service.httpx.AsyncClient = lambda **kwargs: original(
                transport=service.httpx.MockTransport(handler),
                **{key: value for key, value in kwargs.items() if key != "proxy"}
            )
            assert await client.list_templates(page=1, page_size=1, keyword=None) == (
                [], {"page": 1, "pageSize": 1, "total": 0, "hasNext": False}
            )
            await client._save_appearance_upload(
                username="test", appearance_id="test", record={"fileId": 1}
            )
            assert not hasattr(service, "ConfigCenter")
            assert not hasattr(exports, "ConfigCenter")
            assert attempts == [], attempts
        asyncio.run(main())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": root},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
