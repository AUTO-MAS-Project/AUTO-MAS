"""通过真实插件生命周期和 ASGI 验证 wheel 界面挂载。"""

import os
import sys
from dataclasses import replace
from pathlib import Path
from shutil import copytree, ignore_patterns
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import config_triggers, plan_router, plugin_router, scripts_router
from app.config import ConfigCollection, config_manager
from app.core import Config, Plugin
from app.models.config import GeneralConfig, PluginRecord, PluginRegistryCollection
from app.plugin.base.plugin import BasePlugin
from app.plugin.errors import PluginOperationError
from app.plugin.frontend import (
    FrontendManifest,
    FrontendPlanCreation,
    FrontendRouteAlias,
    FrontendSurface,
    FrontendTarget,
)
from app.plugin.http import HttpRegistry
from app.plugin.types import PluginState
from app.task.general.registration import build_config_handler

pytestmark = pytest.mark.asyncio
DEMO_SRC = Path(__file__).resolve().parents[2] / "examples/demo15/src/demo15"


@pytest_asyncio.fixture
async def host(monkeypatch, isolated_app_paths):
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


async def register(name, root, plugin=None):
    collection = Config.plugin_registry
    uid = collection.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": name,
                "import_name": name,
                "version": "0.1.0",
                "source": "local",
                "state": "disabled",
            }
        },
    )
    await collection.commit()
    record = collection[uid]
    record._project_dir = root
    if plugin is None:
        await Plugin.load(record)
    else:
        record._plugin_cls = plugin
    return record


async def registry_document(client, record):
    response = await client.post(
        "/api/plugin_registry/get", json={"recordId": str(record.uid)}
    )
    return response.json()["data"][str(record.uid)]


def asset_url(record, revision, asset):
    return f"/api/plugin/{record.info.plugin_name}/ui/{revision}/{asset}"


@pytest.fixture
def demo_package(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "demo15", None)
    return copytree(
        DEMO_SRC,
        tmp_path / "demo15",
        ignore=ignore_patterns("__pycache__"),
    )


@pytest_asyncio.fixture
async def demo(host, demo_package):
    record = await register("demo15", demo_package.parent)
    await Plugin.enable(record)
    return host, record, demo_package / "ui"


async def test_demo_assets_and_csp(host, demo_package):
    client = host
    ui = demo_package / "ui"
    record = await register("demo15", demo_package.parent)
    router = APIRouter(prefix="/api/plugin/demo15")
    router.add_api_route("/{section}/{path:path}", lambda: {"via": "typed"})
    record._plugin_cls.api_router = router
    await Plugin.enable(record)
    assert (await client.get("/api/plugin/demo15/custom/test")).json() == {
        "via": "typed"
    }
    frontend = (await registry_document(client, record))["frontend"]
    assert frontend["protocolVersion"] == 1
    (target,) = frontend["targets"]
    assert target["surfaces"] == {"plan": {"mode": "wheel", "entry": "plan.html"}}
    assert target["planCreation"] == {
        "key": "Demo15PlanConfig",
        "requiresParentScript": False,
    }
    revision = frontend["revision"]
    for asset, mime in {
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
                "script-src": f"{root}plan.js",
                "style-src": f"{root}plan.css",
                "img-src": f"{root}plan.svg",
                "font-src": "'none'",
                "connect-src": " ".join(
                    root + name
                    for name in ("plan.css", "plan.html", "plan.js", "plan.svg")
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


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("symlink", "资源不存在或越界"),
        ("code.py", "资源路径或扩展名"),
        ("run.exe", "资源路径或扩展名"),
        ("undeclared-entry", "入口必须是已声明"),
        ("unsupported-parent", "不支持保存所属托管"),
        ("typed-route", "/ui 路径保留"),
    ],
)
async def test_failed_enable_leaves_no_mount(host, demo_package, case, error):
    package = demo_package
    record = await register("demo15", package.parent)
    plugin = record._plugin_cls
    manifest = plugin.frontend
    if case == "symlink":
        outside = package / "outside"
        outside.mkdir()
        (outside / "external.js").write_bytes(b"outside the static directory")
        link = package / "ui/linked"
        if os.name == "nt":
            from _winapi import CreateJunction

            CreateJunction(str(outside), str(link))
        else:
            link.symlink_to(outside, target_is_directory=True)
        plugin.frontend = replace(
            manifest, assets=(*manifest.assets, "linked/external.js")
        )
    elif case == "undeclared-entry":
        plugin.frontend = replace(manifest, assets=("plan.js",))
    elif case == "unsupported-parent":
        (target,) = manifest.targets
        target = replace(
            target,
            plan_creation=FrontendPlanCreation(
                key="Demo15PlanConfig", requires_parent_script=True
            ),
        )
        plugin.frontend = replace(manifest, targets=(target,))
    elif case == "typed-route":
        router = APIRouter(prefix="/api/plugin/demo15")
        router.add_api_route("/ui/{revision}/plan.html", lambda: {})
        plugin.api_router = router
    else:
        (package / "ui" / case).write_bytes(b"disallowed extension")
        plugin.frontend = replace(manifest, assets=(*manifest.assets, case))
    with pytest.raises(PluginOperationError, match=error):
        await Plugin.enable(record)
    assert Plugin.http.get(record.info.plugin_name) is None
    assert (await registry_document(host, record))["frontend"] is None
    assert (await host.get(asset_url(record, "any", "plan.html"))).status_code == 404


async def test_disable_reenable_and_reload_asset_revision(demo):
    client, record, ui = demo
    before = (await registry_document(client, record))["frontend"]
    old_url = asset_url(record, before["revision"], "plan.js")
    original = (ui / "plan.js").read_bytes()
    assert (await client.get(old_url)).content == original

    await Plugin.disable(record)
    assert (await client.get(old_url)).status_code == 404
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


async def test_ui_only_builtin_claim_and_conflict(host, tmp_path, monkeypatch):
    class BuiltinUi(BasePlugin):
        frontend = FrontendManifest(
            static_dir="ui",
            assets=("script.html",),
            targets=(
                FrontendTarget(
                    script_key="General",
                    script_config_type="GeneralConfig",
                    user_config_type="GeneralUserConfig",
                    surfaces={
                        "script": FrontendSurface(mode="wheel", entry="script.html"),
                        "setup": FrontendSurface(mode="declarative"),
                        "user": FrontendSurface(mode="declarative"),
                    },
                    aliases=(
                        FrontendRouteAlias(surface="script", path="/scripts/:scriptId"),
                    ),
                ),
            ),
        )

    records = []
    for name in ("builtin-ui", "conflicting-ui"):
        ui = tmp_path / name / "ui"
        ui.mkdir(parents=True)
        (ui / "script.html").write_bytes(b"<!doctype html><title>General</title>")
        records.append(await register(name, tmp_path, BuiltinUi))
    owner, conflict = records
    monkeypatch.setitem(
        Config._script_config_handlers, GeneralConfig, build_config_handler()
    )
    script_id, _ = await Config.add_script("General")
    user_id, _ = await Config.add_user(str(script_id))

    async def surfaces(path, **ids):
        response = await host.post(
            f"/api/scripts/{path}", json={"scriptId": str(script_id), **ids}
        )
        return response.json()["ui"]["frontendSurfaces"]

    assert await surfaces("get") == {}
    await Plugin.enable(owner)
    document = await registry_document(host, owner)
    assert document["providedScript"] is None
    frontend = document["frontend"]
    assert frontend["targets"][0]["aliases"] == [
        {"surface": "script", "path": "/scripts/:scriptId"}
    ]
    mount = {
        "pluginName": owner.info.plugin_name,
        "revision": frontend["revision"],
        "activationId": frontend["activationId"],
    }
    assert await surfaces("get") == {
        "script": {**mount, "mode": "wheel", "entry": "script.html"},
        "setup": {**mount, "mode": "declarative", "entry": None},
    }
    assert await surfaces("user/get", userId=str(user_id)) == {
        "user": {**mount, "mode": "declarative", "entry": None}
    }
    assert (
        await host.get(asset_url(owner, frontend["revision"], "script.html"))
    ).status_code == 200
    with pytest.raises(PluginOperationError, match="conflicting-ui 与 builtin-ui"):
        await Plugin.enable(conflict)
    assert (await registry_document(host, conflict))["frontend"] is None
    assert (await surfaces("get"))["script"]["pluginName"] == owner.info.plugin_name
    await Plugin.disable(owner)
    assert await surfaces("get") == {}
    assert (await registry_document(host, owner))["frontend"] is None


async def test_stale_activation_rejects_config_and_trigger_writes(demo):
    client, record, _ = demo
    frontend = (await registry_document(client, record))["frontend"]
    headers = {
        "X-Plugin-Ui-Provider": record.info.plugin_name,
        "X-Plugin-Ui-Activation": frontend["activationId"],
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
            "mode": "wheel",
            "entry": "plan.html",
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
    assert response.status_code == 200
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
