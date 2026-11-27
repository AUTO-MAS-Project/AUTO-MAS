"""通过真实插件生命周期和 ASGI 验证 wheel 界面挂载。"""

import importlib.metadata
import json
import os
import sys
from shutil import copytree, ignore_patterns
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import config_triggers, plan_router, plugin_router, scripts_router
from app.config import ConfigCollection, config_manager
from app.core import Config, Plugin
from app.core.i18n import I18n
from app.models.config import GeneralConfig, PluginRegistryCollection
from app.plugin.errors import PluginOperationError
from app.plugin.http import HttpRegistry
from app.plugin.runtime import discover
from app.plugin.types import PluginState
from app.task.general.registration import build_config_handler

pytestmark = pytest.mark.asyncio
DEMO_SRC = Config.source_path / "examples/demo15/src/demo15"


@pytest_asyncio.fixture
async def host(monkeypatch, isolated_app_paths):
    monkeypatch.setattr(I18n, "_plugin_sources", {})
    monkeypatch.setattr(I18n, "_package_roots", {})
    monkeypatch.setattr(I18n, "_snapshot", None)
    scripts = ConfigCollection.build(
        [GeneralConfig],
        keep_unknown_types=True,
        file=Config.config_path / "scripts.yaml",
    )
    plans = ConfigCollection.build(keep_unknown_types=True)
    registry = PluginRegistryCollection.build()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setattr(Config, "plugin_registry", registry)
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setattr(Plugin, "script_types", {})
    monkeypatch.setattr(Plugin, "http", HttpRegistry())
    for collection in (scripts, plans, registry):
        await collection.activate()
    app = FastAPI()
    for router in (scripts_router, plan_router, plugin_router, config_triggers.router):
        app.include_router(router)
    Plugin.http.bind_app(app)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        try:
            yield client
        finally:
            for record in registry.values():
                if record.info.state == PluginState.ENABLED:
                    await Plugin.disable(record)


async def registry_document(client, record):
    response = await client.post(
        "/api/plugin_registry/get", json={"recordId": str(record.uid)}
    )
    return response.json()["data"][str(record.uid)]


def asset_url(record, revision, asset):
    return f"/api/plugin/{record.info.plugin_name}/ui/{revision}/{asset}"


@pytest_asyncio.fixture
async def demo_package(host, monkeypatch):
    project = copytree(
        DEMO_SRC.parents[1],
        Config.plugins_path / "demo15",
        ignore=ignore_patterns("__pycache__"),
    )
    package = project / "src/demo15"
    locales = package / "i18n"
    locales.mkdir()
    (locales / "en.json").write_text(
        '{"plugins.demo15.name": "Demo 15"}', encoding="utf8"
    )
    monkeypatch.setitem(sys.modules, "demo15", None)
    monkeypatch.setattr(discover, "_source_projects", lambda: {project})
    monkeypatch.setattr(discover.importlib_metadata, "distributions", lambda **kw: [])
    await discover.refresh()
    record = Config.plugin_registry.by_name("demo15")
    await Plugin.load(record)
    return record, package / "ui"


@pytest_asyncio.fixture
async def demo(host, demo_package):
    record, ui = demo_package
    await Plugin.enable(record)
    return host, record, ui


async def test_demo_assets_and_csp(host, demo_package):
    client = host
    record, ui = demo_package
    router = APIRouter(prefix="/api/plugin/demo15")
    router.add_api_route("/{section}/{path:path}", lambda: {"via": "typed"})
    record._plugin_cls.api_router = router
    await Plugin.enable(record)
    assert (await client.get("/api/plugin/demo15/custom/test")).json() == {
        "via": "typed"
    }
    frontend = (await registry_document(client, record))["frontend"]
    assert frontend["manifestVersion"] == 1
    assert frontend["pages"] == {"plan": {"web": {"entry": "plan.html", "panelApi": 1}}}
    assert frontend["diagnostics"] == []
    (binding,) = frontend["bindings"]
    assert (binding["surface"], binding["planType"], binding["page"]) == (
        "plan",
        "Demo15PlanConfig",
        "plan",
    )
    revision = frontend["revision"]
    for asset, mime in {
        "panel-sdk.js": "text/javascript; charset=utf-8",
        "plan.html": "text/html; charset=utf-8",
        "plan.js": "text/javascript; charset=utf-8",
        "plan.css": "text/css; charset=utf-8",
        "plan.svg": "image/svg+xml",
    }.items():
        response = await client.get(asset_url(record, revision, asset))
        assert response.status_code == 200
        assert response.content == (ui / asset).read_bytes()
        assert response.headers["content-type"] == mime
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        if asset == "plan.html":
            csp = dict(
                directive.split(" ", 1)
                for directive in response.headers["content-security-policy"].split("; ")
            )
            root = f"http://test{asset_url(record, revision, '')}"
            assert csp == {
                "sandbox": "allow-scripts",
                "default-src": "'none'",
                "base-uri": "'none'",
                "form-action": "'none'",
                "object-src": "'none'",
                "frame-src": "'none'",
                "worker-src": "'none'",
                "script-src": f"{root}panel-sdk.js {root}plan.js",
                "style-src": f"{root}plan.css",
                "img-src": f"{root}plan.svg",
                "font-src": "'none'",
                "connect-src": " ".join(
                    root + name
                    for name in (
                        "panel-sdk.js",
                        "plan.css",
                        "plan.html",
                        "plan.js",
                        "plan.svg",
                    )
                ),
            }
        elif asset == "plan.svg":
            assert (
                response.headers["content-security-policy"]
                == "sandbox; default-src 'none'"
            )


@pytest.mark.parametrize(
    ("revision", "asset"),
    [
        (None, "extra.js"),
        (None, "../plan.html"),
        (None, r"..\plan.html"),
        (None, "%2e%2e/plan.html"),
        (None, "%70lan.html"),
        (None, "plan.html/"),
        ("wrong", "plan.html"),
    ],
)
async def test_asset_requires_declared_canonical_path(demo, revision, asset):
    client, record, ui = demo
    (ui / "extra.js").write_text("undeclared")
    revision = (
        revision or (await registry_document(client, record))["frontend"]["revision"]
    )
    assert (await client.get(asset_url(record, revision, asset))).status_code == 404


async def test_typed_route_cannot_shadow_static_resources(host, demo_package):
    record, _ = demo_package
    router = APIRouter(prefix="/api/plugin/demo15")
    router.add_api_route("/ui/{revision}/plan.html", lambda: {})
    record._plugin_cls.api_router = router
    with pytest.raises(PluginOperationError, match="/ui 路径保留"):
        await Plugin.enable(record)
    assert (await registry_document(host, record))["frontend"] is None


async def test_partial_manifest_and_ownership(host, demo_package):
    record, ui = demo_package
    manifest = ui / "manifest.json"
    data = json.loads(manifest.read_bytes())
    (ui / "Plan.qml").write_text("Item {}", encoding="utf8")
    outside = ui.parent / "outside"
    outside.mkdir()
    (outside / "external.js").write_bytes(b"external")
    link = ui / "linked"
    if os.name == "nt":
        from _winapi import CreateJunction

        CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    data["pages"]["plan"]["qt-quick"] = {"entry": "Plan.qml", "panelApi": 2}
    data["bindings"][0].pop("page")
    data["pages"]["plan"]["invalid"] = {"entry": "plan.html", "panelApi": True}
    data["pages"]["lost"] = {"web": {"entry": "../outside/plan.html", "panelApi": 1}}
    data["pages"]["missing"] = {"web": {"entry": "missing.html", "panelApi": 1}}
    data["bindings"] += [
        {"surface": "settings", "page": "plan"},
        {"surface": "notification", "channel": "demo15", "page": "plan"},
        {"surface": "plan", "planType": "ForeignPlanConfig", "page": "plan"},
        {"surface": "script", "scriptType": "General", "page": "plan"},
        {"surface": "setup", "scriptType": "Demo15", "page": "lost"},
    ]
    (ui / "private.py").write_bytes(b"private")
    manifest.write_text(json.dumps(data), encoding="utf8")
    await Plugin.enable(record)
    frontend = (await registry_document(host, record))["frontend"]
    assert frontend["pages"] == {
        "plan": {
            "web": {"entry": "plan.html", "panelApi": 1},
            "qt-quick": {"entry": "Plan.qml", "panelApi": 2},
        }
    }
    assert [binding["surface"] for binding in frontend["bindings"]] == [
        "plan",
        "settings",
        "notification",
    ]
    diagnostics = "\n".join(frontend["diagnostics"])
    for target in (
        "pages.plan.invalid",
        "pages.lost",
        "pages.missing",
        "bindings[3]",
        "bindings[4]",
        "bindings[5]",
    ):
        assert target in diagnostics
    assert (
        await host.get(asset_url(record, frontend["revision"], "Plan.qml"))
    ).content == b"Item {}"
    for asset in ("linked/external.js", "private.py", "manifest.json"):
        assert (
            await host.get(asset_url(record, frontend["revision"], asset))
        ).status_code == 404


async def test_disable_reenable_and_reload_asset_revision(demo):
    client, record, ui = demo
    before = (await registry_document(client, record))["frontend"]
    old_url = asset_url(record, before["revision"], "plan.js")
    original = (ui / "plan.js").read_bytes()
    assert (await client.get(old_url)).content == original

    await Plugin.disable(record)
    assert (await client.get(old_url)).status_code == 404
    assert (await registry_document(client, record))["frontend"] is None
    messages, _ = await I18n.get_messages("en-US")
    assert messages["plugins"]["demo15"]["name"] == "Demo 15"
    await Plugin.enable(record)
    current = (await registry_document(client, record))["frontend"]
    assert current["revision"] == before["revision"]
    assert current["activationId"] != before["activationId"]
    assert (await client.get(old_url)).status_code == 200

    updated = original + b"\n// Updated wheel\n"
    (ui / "plan.js").write_bytes(updated)
    assert (await client.get(old_url)).content == original
    await Plugin.reload(record)
    reloaded = (await registry_document(client, record))["frontend"]
    assert reloaded["revision"] != current["revision"]
    assert reloaded["activationId"] != current["activationId"]
    assert (await client.get(old_url)).status_code == 404
    response = await client.get(asset_url(record, reloaded["revision"], "plan.js"))
    assert response.status_code == 200
    assert response.content == updated


async def test_stale_activation_rejects_config_and_trigger_writes(demo):
    client, record, _ = demo
    frontend = (await registry_document(client, record))["frontend"]
    headers = {
        "X-Plugin-Ui-Provider": record.info.plugin_name,
        "X-Plugin-Ui-Activation": frontend["activationId"],
        "X-Plugin-Ui-Page": "plan",
    }
    # 业务体使用合法形状，陈旧请求在定位配置或派发触发器之前即被拒绝。
    uid = str(uuid4())
    writes = {
        "/api/scripts/update": {"scriptId": uid, "data": {}},
        "/api/scripts/user/update": {"scriptId": uid, "userId": uid, "data": {}},
        "/api/plan/update": {"planId": uid, "data": {}},
        "/api/config/triggers/write": {
            "configUid": uid,
            "group": "Info",
            "field": "DiscoverPath",
            "value": True,
        },
    }
    script_id, _ = await Config.add_script("Demo15")
    plan_id, _ = await Config.add_plan("Demo15PlanConfig")
    detail = (await client.post("/api/plan/get", json={"planId": str(plan_id)})).json()
    assert detail["ui"]["frontendSurfaces"] == {
        "plan": {
            "pageId": "plan",
            "artifacts": {"web": {"entry": "plan.html", "panelApi": 1}},
            "pluginName": record.info.plugin_name,
            "revision": frontend["revision"],
            "activationId": frontend["activationId"],
        }
    }
    response = await client.post(
        "/api/config/triggers/write",
        json={
            "configUid": str(script_id),
            "group": "Info",
            "field": "DiscoverPath",
            "value": None,
        },
        headers=headers,
    )
    assert response.status_code == 403
    user_id, _ = await Config.add_user(str(script_id))
    for path, ids in (
        ("/api/scripts/update", {"scriptId": str(script_id)}),
        (
            "/api/scripts/user/update",
            {"scriptId": str(script_id), "userId": str(user_id)},
        ),
    ):
        assert (
            await client.post(path, json={**ids, "data": {}}, headers=headers)
        ).status_code == 403
    assert (
        await client.post(
            "/api/plan/update",
            json={"planId": str(plan_id), "data": {}},
            headers={**headers, "X-Plugin-Ui-Page": "other"},
        )
    ).status_code == 403
    await Plugin.disable(record)
    assert (
        await client.post(
            "/api/plan/update", json=writes["/api/plan/update"], headers=headers
        )
    ).status_code == 409
    await Plugin.enable(record)
    plan_id, plan = await Config.add_plan("Demo15PlanConfig")
    writes["/api/plan/update"] = {
        "planId": str(plan_id),
        "data": {"First": {"Count": 3}},
    }
    for path, data in writes.items():
        assert (await client.post(path, json=data, headers=headers)).status_code == 409
    assert plan.First.Count == 1
    partial = {"X-Plugin-Ui-Provider": record.info.plugin_name}
    assert (
        await client.post(
            "/api/plan/update", json=writes["/api/plan/update"], headers=partial
        )
    ).status_code == 403
    current = (await registry_document(client, record))["frontend"]
    headers["X-Plugin-Ui-Activation"] = current["activationId"]
    response = await client.post(
        "/api/plan/update", json=writes["/api/plan/update"], headers=headers
    )
    assert response.status_code == 200 and response.json()["code"] == 200
    assert plan.First.Count == 3


async def test_script_and_user_bindings_authorize_actual_targets(
    host, demo_package, monkeypatch
):
    record, ui = demo_package
    manifest = ui / "manifest.json"
    data = json.loads(manifest.read_bytes())
    data["pages"]["editor"] = data["pages"]["plan"]
    data["bindings"].extend(
        {"surface": surface, "scriptType": "Demo15", "page": "editor"}
        for surface in ("script", "setup", "user", "extra")
    )
    manifest.write_text(json.dumps(data), encoding="utf8")
    await Plugin.enable(record)
    frontend = (await registry_document(host, record))["frontend"]
    headers = {
        "X-Plugin-Ui-Provider": "demo15",
        "X-Plugin-Ui-Activation": frontend["activationId"],
        "X-Plugin-Ui-Page": "editor",
    }
    script_id, script = await Config.add_script("Demo15")
    user_id, user = await Config.add_user(str(script_id))
    ids = {"scriptId": str(script_id)}
    user_ids = {**ids, "userId": str(user_id)}
    for route, target, expected in (
        ("get", ids, {"script", "setup"}),
        ("user/get", user_ids, {"user"}),
    ):
        mounts = (await host.post(f"/api/scripts/{route}", json=target)).json()["ui"][
            "frontendSurfaces"
        ]
        assert set(mounts) == expected
        assert all(mount["pageId"] == "editor" for mount in mounts.values())
    for path, body in (
        ("/api/scripts/update", {**ids, "data": {"Run": {"Retries": 4}}}),
        ("/api/scripts/user/update", {**user_ids, "data": {"Info": {"Id": "demo"}}}),
        (
            "/api/config/triggers/write",
            {
                "configUid": str(script_id),
                "group": "Info",
                "field": "DiscoverPath",
                "value": None,
            },
        ),
    ):
        response = await host.post(path, json=body, headers=headers)
        assert response.status_code == 200 and response.json()["code"] == 200
    assert script.Run.Retries == 4 and user.Info.Id == "demo"

    monkeypatch.setitem(
        Config._script_config_handlers, GeneralConfig, build_config_handler()
    )
    foreign_id, _ = await Config.add_script("General")
    foreign_user, _ = await Config.add_user(str(foreign_id))
    for path, target in (
        ("update", {"scriptId": str(foreign_id)}),
        ("user/update", {"scriptId": str(foreign_id), "userId": str(foreign_user)}),
    ):
        response = await host.post(
            f"/api/scripts/{path}", json={**target, "data": {}}, headers=headers
        )
        assert response.status_code == 403


async def test_manifest_only_reload_revokes_session(demo):
    client, record, ui = demo
    before = (await registry_document(client, record))["frontend"]
    path = ui / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["pages"]["plan"]["web"]["panelApi"] = 2
    path.write_text(json.dumps(manifest), encoding="utf8")
    await Plugin.reload(record)
    after = (await registry_document(client, record))["frontend"]
    assert after["revision"] != before["revision"]
    assert after["pages"]["plan"]["web"]["panelApi"] == 2
    assert (
        await client.get(asset_url(record, before["revision"], "plan.html"))
    ).status_code == 404
    plan_id, plan = await Config.add_plan("Demo15PlanConfig")
    response = await client.post(
        "/api/plan/update",
        json={"planId": str(plan_id), "data": {"First": {"Count": 8}}},
        headers={
            "X-Plugin-Ui-Provider": "demo15",
            "X-Plugin-Ui-Page": "plan",
            "X-Plugin-Ui-Activation": before["activationId"],
        },
    )
    assert response.status_code == 409 and plan.First.Count == 1


async def test_installed_plugin_cannot_take_demo_plan_and_releases_resources(
    host, demo, tmp_path, monkeypatch
):
    """用另一个已安装发行包认领正在运行的计划，仅隔离实际的 uv 卸包操作。"""
    _, owner, _ = demo
    package = tmp_path / "panel_probe"
    ui = package / "ui"
    ui.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from auto_mas_core import BasePlugin, PluginConfig\nclass Probe(BasePlugin): config_class = PluginConfig\nPLUGIN = Probe\n",
        encoding="utf8",
    )
    (ui / "settings.html").write_bytes(b"settings")
    (ui / "manifest.json").write_text(
        json.dumps(
            {
                "manifestVersion": 1,
                "pages": {
                    "settings": {"web": {"entry": "settings.html", "panelApi": 1}}
                },
                "bindings": [
                    {"surface": "settings", "page": "settings"},
                    {
                        "surface": "plan",
                        "page": "settings",
                        "planType": "Demo15PlanConfig",
                    },
                ],
            }
        ),
        encoding="utf8",
    )
    (package / "i18n").mkdir()
    (package / "i18n/en.json").write_text(
        '{"plugins.panel_probe.name":"Probe"}', encoding="utf8"
    )
    info = tmp_path / "panel_probe-1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.2\nName: panel-probe\nVersion: 1\nKeywords: auto-mas-plugin,auto-mas-id:panel_probe\n",
        encoding="utf8",
    )
    (info / "RECORD").write_text("panel_probe/__init__.py,,\n", encoding="utf8")
    dist = importlib.metadata.Distribution.at(info)
    monkeypatch.setattr(
        discover.importlib_metadata, "distributions", lambda **kw: [dist]
    )
    await discover.refresh()
    record = Config.plugin_registry.by_name("panel_probe")
    await Plugin.load(record)
    await Plugin.enable(record)
    frontend = (await registry_document(host, record))["frontend"]
    assert [binding["surface"] for binding in frontend["bindings"]] == ["settings"]
    assert any("bindings[1]" in message for message in frontend["diagnostics"])
    plan_id, plan = await Config.add_plan("Demo15PlanConfig")
    response = await host.post(
        "/api/plan/update",
        json={"planId": str(plan_id), "data": {"First": {"Count": 9}}},
        headers={
            "X-Plugin-Ui-Page": "settings",
            "X-Plugin-Ui-Activation": frontend["activationId"],
            "X-Plugin-Ui-Provider": "panel_probe",
        },
    )
    assert response.status_code == 403 and plan.First.Count == 1
    settings = {"recordId": str(record.uid), "data": {}}
    headers = {
        "X-Plugin-Ui-Provider": "panel_probe",
        "X-Plugin-Ui-Page": "settings",
        "X-Plugin-Ui-Activation": frontend["activationId"],
    }
    assert (
        await host.post("/api/plugin_config/update", json=settings, headers=headers)
    ).json()["code"] == 200
    other_ui = (await registry_document(host, owner))["frontend"]
    headers = {
        "X-Plugin-Ui-Provider": "demo15",
        "X-Plugin-Ui-Page": "plan",
        "X-Plugin-Ui-Activation": other_ui["activationId"],
    }
    assert (
        await host.post("/api/plugin_config/update", json=settings, headers=headers)
    ).status_code == 403
    url = asset_url(record, frontend["revision"], "settings.html")
    assert (await host.get(url)).content == b"settings"

    from app.plugin import uv as uv_tool

    monkeypatch.setattr(uv_tool, "uninstall", AsyncMock())
    monkeypatch.setattr(Config, "setting", type(Config.setting).build())
    await Plugin.uninstall(record)
    assert (await host.get(url)).status_code == 404
    messages, _ = await I18n.get_messages("en-US")
    assert "panel_probe" not in messages["plugins"]
    assert (await registry_document(host, owner))["frontend"]["pages"]["plan"]
