"""插件网关在进入业务前确定签名，业务异常不能触发二次调用。"""

import pytest
from starlette.requests import Request

from app.api.plugin import dispatch_plugin_http
from app.core.plugin import Plugin
from app.plugin.http import HttpRegistry, RouteDecl


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("exception", [TypeError, ValueError])
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
    assert response.status_code == 500
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
    assert (await dispatch_plugin_http("example", "run", request)).status_code == 200
    registry.seal()
    assert (await dispatch_plugin_http("example", "run", request)).status_code == 503
    assert calls == [True]


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
