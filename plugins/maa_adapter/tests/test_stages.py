"""插件关卡缓存、启用预热、标准选项声明及 HTTP 装卸契约。"""

import json

import httpx
import pytest
from fastapi import FastAPI
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.config.plugin import MaaPluginConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.plugin import Plugin as MaaPlugin

from app.config import config_manager
from app.config.fields.hints import Select
from app.core import Plugin
from app.core.background_tasks import BackgroundTaskRegistry
from app.plugin.calls import CallGate
from app.plugin.http import HttpRegistry
from app.plugin.services import ServiceRegistry


@pytest.mark.asyncio
async def test_enable_fetches_owned_cache_and_mounts_stage_endpoints(
    tmp_path, monkeypatch
):
    """启用即获取并保存多区服资源，接口只读插件缓存，卸载路由后不再对外提供关卡。"""
    import maa_adapter.plugin as module

    content = {"Official": {"sideStoryStage": {}}, "YoStarEN": {"sideStoryStage": {}}}
    requests = []

    async def fetch(headers):
        """替代官方 HTTP 边界，记录首次获取和 ETag 条件请求。"""
        requests.append(headers)
        if headers:
            return httpx.Response(304)
        return httpx.Response(200, json=content, headers={"ETag": "stage-v1"})

    monkeypatch.setattr(module, "fetch_stage", fetch)
    path = tmp_path / "maa.yaml"
    config = MaaPluginConfig.build(file=path)
    await config.activate()
    tasks = BackgroundTaskRegistry()
    group = tasks.register_group("maa-stages", max_running=2, max_retained=2)
    plugin = MaaPlugin(config=config)
    plugin.bind_background_tasks(group)
    await plugin.on_enable()
    assert requests == [{}]
    assert json.loads(config.stage_cache.content) == content
    assert config.stage_cache.etag == "stage-v1"
    await config_manager.flush()
    config_manager.unregister_root(config)
    restored = MaaPluginConfig.build(file=path)
    await restored.activate()
    assert restored.stage_cache.content == config.stage_cache.content
    assert restored.stage_cache.checked_at == config.stage_cache.checked_at

    services = ServiceRegistry()
    for name, method in plugin.provides_services.items():
        services.register(name, getattr(plugin, method), owner="maa_adapter")
    monkeypatch.setattr(Plugin, "services", services)
    from app.api.plugin import router as plugin_router

    app = FastAPI()
    app.include_router(plugin_router)
    http = HttpRegistry()
    monkeypatch.setattr(Plugin, "http", http)
    http.bind_app(app)
    http.mount("maa_adapter", [], router=plugin.api_router, gate=CallGate())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/plugin/maa_adapter/stages/options",
            json={"type": "User", "server": "Bilibili"},
        )
        assert response.json()["code"] == 200
        assert any(item["value"] == "1-7" for item in response.json()["data"])
        overview = (await client.post("/api/plugin/maa_adapter/stages/overview")).json()
        assert "YoStarEN" in overview["data"]
        assert requests == [{}]
        await client.post("/api/plugin/maa_adapter/stages/overview?refresh=true")
        assert requests[-1] == {"If-None-Match": "stage-v1"}
        assert json.loads(config.stage_cache.content) == content
        http.unmount("maa_adapter")
        assert (
            await client.post("/api/plugin/maa_adapter/stages/options", json={})
        ).status_code == 404
    await tasks.shutdown(timeout=2)


def test_account_and_all_plan_stage_fields_declare_plugin_endpoint():
    """所有主备关卡均声明同一标准 endpoint，自定义关卡仍能通过配置模型保存。"""
    groups = [MaaUserConfig.StageFields]
    groups.extend(
        field.annotation
        for name, field in MaaPlanConfig.model_fields.items()
        if name == "ALL"
        or name.startswith("Day")
        or name
        in {
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        }
    )
    for group in groups:
        for name in ("Stage", "Stage_1", "Stage_2", "Stage_3"):
            marker = next(
                item
                for item in group.model_fields[name].metadata
                if isinstance(item, Select)
            )
            assert marker.endpoint == "/api/plugin/maa_adapter/stages/options"
        assert group.model_validate({"Stage": "CUSTOM-42"}).Stage == "CUSTOM-42"
