"""插件网关在进入业务前确定签名，业务异常不能触发二次调用。"""

import asyncio
import json
import threading

import pytest
from starlette.requests import Request

from app.api.plugin import dispatch_plugin_http
from app.core.plugin import Plugin
from app.plugin.calls import CallGate
from app.plugin.errors import PluginBusyError
from app.plugin.http import HttpRegistry, RouteDecl


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("exception", [TypeError, ValueError, PluginBusyError])
async def test_handler_error_is_never_retried(monkeypatch, asynchronous, exception):
    """验证插件处理器抛出业务异常后只执行一次，网关返回错误而不会尝试其他调用签名。"""
    calls = []

    def run(request):
        """记录实际调用并抛出指定业务异常，供同步与异步网关测试共用。"""
        calls.append(request)
        raise exception("business error")

    async def async_run(request):
        """以异步处理器入口复用抛错行为，验证网关不会重试异步业务。"""
        return run(request)

    registry = HttpRegistry()
    registry.mount(
        "example", [RouteDecl("/run", ("POST",), async_run if asynchronous else run)]
    )
    monkeypatch.setattr(Plugin, "http", registry)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/plugin/example/run",
            "headers": [],
        }
    )
    response = await dispatch_plugin_http("example", "run", request)
    status = 503 if exception is PluginBusyError else 500
    assert response.status_code == status
    payload = json.loads(response.body)
    assert payload["code"] == status
    assert payload["status"] == "error"
    assert isinstance(payload["message"], str) and payload["message"]
    assert "detail" not in payload
    assert "business error" not in payload["message"]
    assert calls == [request]


@pytest.mark.asyncio
async def test_no_argument_handler_and_sealed_admission(monkeypatch):
    """验证无参数插件处理器可执行，HTTP 注册表关闭后拒绝再次进入业务。"""
    calls = []

    def run():
        """记录无参数路由的调用次数并返回成功内容，供准入断言使用。"""
        calls.append(True)
        return {"ok": True}

    registry = HttpRegistry()
    registry.mount("example", [RouteDecl("/run", ("GET",), run)])
    monkeypatch.setattr(Plugin, "http", registry)
    request = Request({"type": "http", "method": "GET", "path": "/run", "headers": []})
    response = await dispatch_plugin_http("example", "run", request)
    assert response.status_code == 200
    assert json.loads(response.body) == {"ok": True}
    registry.seal()
    sealed = await dispatch_plugin_http("example", "run", request)
    assert sealed.status_code == 503
    assert json.loads(sealed.body)["code"] == 503
    assert json.loads(sealed.body)["status"] == "error"
    assert calls == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("mounted", [False, True])
async def test_missing_gateway_returns_standard_error(monkeypatch, mounted):
    """未挂载插件和不存在的路由都返回稳定信封，不将宿主挂载路径带给调用方。"""
    registry = HttpRegistry()
    if mounted:
        registry.mount("example", [])
    monkeypatch.setattr(Plugin, "http", registry)
    request = Request(
        {"type": "http", "method": "GET", "path": "/missing", "headers": []}
    )
    result = await dispatch_plugin_http("example", "missing", request)
    assert result.status_code == 404
    payload = json.loads(result.body)
    assert payload["code"] == 404 and payload["status"] == "error"
    assert set(payload) == {"code", "status", "message"}


@pytest.mark.asyncio
async def test_registry_payload_uses_config_wire_projection(monkeypatch):
    """验证插件注册记录按配置 API 投影输出，包含公开名称而不泄露内部多语言映射字段。"""
    from app.api.plugin import PluginRegistryGetIn, get_plugin_registry
    from app.config import ConfigCollection
    from app.core import Config
    from app.models.config import PluginRecord

    records = ConfigCollection[PluginRecord].build([PluginRecord])
    await records.activate()
    uid = records.add(
        PluginRecord, payload={"info": {"plugin_name": "example", "version": "1.0"}}
    )
    await records.commit()
    monkeypatch.setattr(Config, "plugin_registry", records)
    result = await get_plugin_registry(PluginRegistryGetIn())
    assert result.code == 200
    payload = result.model_dump(mode="json")
    assert payload["data"][str(uid)]["info"]["plugin_name"] == "example"
    assert "display_name_i18n" not in payload["data"][str(uid)]["info"]
    assert payload["data"][str(uid)]["uid"] == str(uid)
    hints = payload["data"][str(uid)]["ui"]["hints"]["info"]
    enable = next(hint for hint in hints if hint["field"] == "enable")
    # 未加载插件不能启用；UI 属性必须真实穿过响应模型供前端禁用按钮。
    assert enable["editable"] is False


@pytest.mark.asyncio
async def test_catalog_updates_only_submit_install(monkeypatch):
    """原始 HTTP 补丁无法改写市场身份或展示字段，但安装触发器仍通过真实配置更新提交。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.plugin import router
    from app.config import ConfigCollection
    from app.core import Config
    from app.core.plugin.operations import Operations
    from app.models.config import PluginMeta

    catalog = ConfigCollection[PluginMeta].build([PluginMeta])
    await catalog.activate()
    uid = catalog.add(
        PluginMeta,
        payload={
            "info": {
                "package_name": "auto-mas-example",
                "plugin_name": "example",
                "version": "1.0",
            }
        },
    )
    await catalog.commit()
    monkeypatch.setattr(Config, "plugin_catalog", catalog)
    submitted = []
    monkeypatch.setattr(
        Operations, "submit", lambda entry, **kwargs: submitted.append((entry, kwargs))
    )
    app = FastAPI()
    app.include_router(router)
    before = catalog[uid].info.model_dump()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post(
            "/api/plugin_catalog/update",
            json={
                "metaId": str(uid),
                "data": {
                    "info": {
                        "package_name": "changed",
                        "plugin_name": "changed",
                        "version": "9",
                        "homepage": "https://changed.test",
                        "install": True,
                    }
                },
            },
        )
    assert result.json()["code"] == 200
    assert catalog[uid].info.model_dump() == before
    assert submitted == [
        (catalog[uid], {"group": "info", "field": "install", "value": True})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_typed_sync_endpoint_runs_in_worker_and_releases_admission(failed):
    """标准同步端点保留查询参数和契约，在线程执行业务，成功或报错后都释放在途登记。"""
    from fastapi import APIRouter, FastAPI
    from httpx import ASGITransport, AsyncClient

    app = FastAPI()
    router = APIRouter()
    threads = []

    @router.get("/probe")
    def endpoint(value: int):
        """从真实参数绑定接收整数，并按场景返回或抛出业务异常。"""
        threads.append(threading.get_ident())
        if failed:
            raise ValueError("business failed")
        return {"value": value}

    gate = CallGate()
    registry = HttpRegistry()
    registry.bind_app(app)
    registry.mount("example", [], router=router, gate=gate)
    assert app.openapi()["paths"]["/probe"]["get"]["parameters"][0]["name"] == "value"
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        result = await client.get("/probe?value=7")
    assert result.status_code == (500 if failed else 200)
    if not failed:
        assert result.json() == {"value": 7}
    assert len(threads) == 1 and threads[0] != threading.get_ident()
    await asyncio.wait_for(gate.drain(), 1)


@pytest.mark.asyncio
async def test_cancelled_sync_http_keeps_admission_until_worker_exits():
    """请求取消后同步工作仍可能使用插件资源，必须等工作线程真正退出再完成调用排空。"""
    from fastapi import APIRouter, FastAPI
    from httpx import ASGITransport, AsyncClient

    app, router = FastAPI(), APIRouter()
    started, release = threading.Event(), threading.Event()

    @router.get("/probe")
    def endpoint():
        """保持一个实际线程调用在途，直到测试释放模拟外部同步工作。"""
        started.set()
        release.wait(5)
        return {"done": True}

    gate, registry = CallGate(), HttpRegistry()
    registry.bind_app(app)
    registry.mount("example", [], router=router, gate=gate)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        request = asyncio.create_task(client.get("/probe"))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            request.cancel()
            gate.accepting = False
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(gate.drain(), 0.05)
            assert not request.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await request
            await asyncio.wait_for(gate.drain(), 1)
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
