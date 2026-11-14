"""MAA 插件配置、契约和卸载边界的集成回归。"""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.plugin import Plugin as MaaPlugin

from app.config import ConfigCollection, config_manager
from app.core import Config, Plugin
from app.core.config.upgrade import convert_legacy
from app.models.config import PluginRecord
from app.plugin.calls import CallGate
from app.plugin.http import HttpRegistry
from app.plugin.openapi import bind_openapi
from app.plugin.types import PluginState


@pytest_asyncio.fixture
async def maa_host(isolated_app_paths, monkeypatch):
    """只装配当前 MAA 声明与隔离集合，HTTP 仍调用真实公共 CRUD。"""
    # 来源备份文件原语仍按工作目录定位 data，保持它与隔离后的应用路径一致。
    monkeypatch.chdir(isolated_app_paths.work_path)
    scripts = ConfigCollection.build([MaaConfig])
    plans = ConfigCollection.build([MaaPlanConfig])
    monkeypatch.setitem(config_manager._collections, "ScriptConfig", scripts)
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    await plans.activate()
    await scripts.activate()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    record = PluginRecord.build(
        info={"plugin_name": "maa_adapter", "state": PluginState.ENABLED}
    )
    record._plugin_cls = MaaPlugin
    monkeypatch.setattr(Plugin, "script_types", {record.uid: MaaPlugin.decl})
    monkeypatch.setattr(Plugin, "list_plugins", lambda: [record])
    monkeypatch.setattr(Config, "_restore_pool_resolver", None)
    await MaaPlugin().pre_enable()
    MaaConfig.bind_runtime_signals()
    from app.api import plan_router, plugin_router, scripts_router

    app = FastAPI()
    app.include_router(scripts_router)
    app.include_router(plan_router)
    app.include_router(MaaPlugin.api_router)
    app.include_router(plugin_router)
    bind_openapi(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, app


@pytest.mark.asyncio
async def test_maa_public_crud_plan_restore_and_schema(maa_host):
    """经公共接口创建、编辑、复制和引用计划，确认专项字段、身份及恢复池均来自插件。"""
    client, app = maa_host
    capabilities = (await client.get("/api/scripts/types")).json()
    assert capabilities["code"] == 200 and "MAA" in capabilities["types"]
    record = Plugin.list_plugins()[0]
    assert Plugin.disable_impact(record) == ["scripts"]
    record.info.state = PluginState.DISABLING
    assert "MAA" not in (await client.get("/api/scripts/types")).json()["types"]
    record.info.state = PluginState.ENABLED
    created = (await client.post("/api/scripts/add", json={"type": "MAA"})).json()
    assert created["code"] == 200, created
    sid = created["scriptId"]
    user = (await client.post("/api/scripts/user/add", json={"scriptId": sid})).json()
    assert user["code"] == 200, user
    uid = user["userId"]
    plan = (await client.post("/api/plan/add", json={"type": "MaaPlanConfig"})).json()
    assert plan["code"] == 200, plan
    pid = plan["planId"]
    saved = (
        await client.post(
            "/api/scripts/user/update",
            json={
                "scriptId": sid,
                "userId": uid,
                "data": {"Info": {"Name": "插件账号"}, "Stage": {"StageMode": pid}},
            },
        )
    ).json()
    assert saved["code"] == 200, saved
    document = (
        await client.post(
            "/api/scripts/user/get", json={"scriptId": sid, "userId": uid}
        )
    ).json()
    assert document["data"][uid]["Info"]["Name"] == "插件账号"
    assert document["data"][uid]["Stage"]["StageMode"] == pid
    backups = (
        await client.get(
            "/api/plugin/maa_adapter/backup/list",
            params={"scriptId": sid, "userId": uid, "target": "mas"},
        )
    ).json()
    assert backups["code"] == 200 and backups["data"] == []
    copied = (
        await client.post("/api/scripts/add", json={"type": "MAA", "scriptId": sid})
    ).json()
    assert copied["code"] == 200, copied
    assert copied["scriptId"] != sid
    assert len(Config.ScriptConfig[copied["scriptId"]].users) == 1
    schema = app.openapi()["components"]["schemas"]
    assert "MAA" in schema["ScriptCreateIn"]["properties"]["type"]["enum"]
    assert (
        "MaaConfig" in schema
        and "MaaUserConfig" in schema
        and "MaaPlanConfig" in schema
    )
    assert len({key.casefold() for key in schema}) == len(schema)
    removed = (await client.post("/api/plan/delete", json={"planId": pid})).json()
    assert removed["code"] == 200, removed
    assert Config.ScriptConfig[sid].users[uid].Stage.StageMode == "Fixed"


@pytest.mark.asyncio
async def test_plugin_plan_type_filter_and_locked_reference_rollback(maa_host):
    """计划选项按真实类型筛选，锁定引用阻止删除且保持计划和全部引用原值。"""
    from app.models.config import PlanEntry

    class OtherPlan(PlanEntry):
        pass

    client, _ = maa_host
    Config.PlanConfig.add_type(OtherPlan)
    await Config.PlanConfig.commit()
    script = (await client.post("/api/scripts/add", json={"type": "MAA"})).json()[
        "scriptId"
    ]
    user = (
        await client.post("/api/scripts/user/add", json={"scriptId": script})
    ).json()["userId"]
    plan = (await client.post("/api/plan/add", json={"type": "MaaPlanConfig"})).json()[
        "planId"
    ]
    other = (await client.post("/api/plan/add", json={"type": "OtherPlan"})).json()[
        "planId"
    ]
    options = (
        await client.post("/api/plugin/options/plans", json={"type": "MaaPlanConfig"})
    ).json()
    assert [item["value"] for item in options["data"]] == [plan]
    assert other != plan
    account = Config.ScriptConfig[script].users[user]
    account.Stage.StageMode = plan
    account.info.plan_id = plan
    await account.commit()
    ticket = await account.lock_s()
    try:
        deleted = (await client.post("/api/plan/delete", json={"planId": plan})).json()
        assert deleted["code"] != 200
        assert plan in Config.PlanConfig
        assert str(account.Stage.StageMode) == plan
        assert str(account.info.plan_id) == plan
    finally:
        await account.unlock(ticket)
    assert (await client.post("/api/plan/delete", json={"planId": plan})).json()[
        "code"
    ] == 200
    assert account.Stage.StageMode == "Fixed"
    assert account.info.plan_id == "-"


@pytest.mark.asyncio
async def test_maa_backup_api_owns_round_trip_and_guards(maa_host):
    """MAA 自有接口完成归档、预览和恢复，保留运行锁与归档路径检查。"""
    client, _ = maa_host
    sid = (await client.post("/api/scripts/add", json={"type": "MAA"})).json()[
        "scriptId"
    ]
    uid = (await client.post("/api/scripts/user/add", json={"scriptId": sid})).json()[
        "userId"
    ]
    directory = Config.data_path / sid / "Default" / "ConfigFile"
    directory.mkdir(parents=True)
    source = directory / "gui.new.json"
    source.write_text('{"Update":{"VersionType":"Stable"}}', encoding="utf-8")
    context = {"scriptId": sid, "userId": uid, "target": "mas"}
    prefix = "/api/plugin/maa_adapter/backup"
    saved = (await client.post(f"{prefix}/ensure", json=context)).json()
    assert saved["code"] == 200 and saved["created"]
    ts = saved["time"]
    listed = (await client.get(f"{prefix}/list", params=context)).json()
    assert ts in [item["time"] for item in listed["data"]]
    selected = {**context, "time": ts}
    preview = (await client.get(f"{prefix}/preview", params=selected)).json()
    assert preview["code"] == 200 and preview["data"]["fileCards"]
    refused = (
        await client.get(
            f"{prefix}/file", params={**selected, "path": "../outside.json"}
        )
    ).json()
    assert refused["code"] == 400
    source.write_text('{"Update":{"VersionType":"Beta"}}', encoding="utf-8")
    script = Config.ScriptConfig[sid]
    ticket = await script.lock_s()
    try:
        locked = (await client.post(f"{prefix}/restore", json=selected)).json()
        assert locked["code"] != 200
        assert (
            json.loads(source.read_text(encoding="utf-8"))["Update"]["VersionType"]
            == "Beta"
        )
    finally:
        await script.unlock(ticket)
    restored = (await client.post(f"{prefix}/restore", json=selected)).json()
    assert restored["code"] == 200, restored
    assert (
        json.loads(source.read_text(encoding="utf-8"))["Update"]["VersionType"]
        == "Stable"
    )
    # 宿主已不装配 MAA 的恢复池；同一能力只由插件接口提供。
    assert (await client.get("/api/scripts/backup/list", params=context)).json()[
        "code"
    ] != 200


@pytest.mark.asyncio
async def test_maa_owns_source_signal_and_configuration_directory(
    maa_host, tmp_path_factory
):
    """公共 CRUD 无专项处理器时仍保留目录定位；直接配置提交同样执行原生来源互斥。"""
    from app.config.errors import ConfigAggregateError

    client, _ = maa_host
    created = (await client.post("/api/scripts/add", json={"type": "MAA"})).json()
    sid = created["scriptId"]
    first = (await client.post("/api/scripts/user/add", json={"scriptId": sid})).json()[
        "userId"
    ]
    second = (
        await client.post("/api/scripts/user/add", json={"scriptId": sid})
    ).json()["userId"]
    script = Config.ScriptConfig[sid]
    shared = (
        await client.post(
            "/api/scripts/user/config-dir", json={"scriptId": sid, "userId": second}
        )
    ).json()
    assert shared["code"] == 200
    assert shared["path"] == str(Config.data_path / sid / "Default" / "ConfigFile")
    script.users[first].Info.Base = "native"
    await script.users[first].commit()
    # 不经过公共 API/handler 的写入也必须由插件自己的信号阻止冲突。
    script.users[second].Info.Base = "native"
    with pytest.raises(ConfigAggregateError):
        await script.users[second].commit()
    assert script.users[second].Info.Base == "shared"
    absent = (
        await client.post(
            "/api/scripts/user/config-dir", json={"scriptId": sid, "userId": first}
        )
    ).json()
    assert absent["code"] == 500
    install = tmp_path_factory.mktemp("maa-native-config")
    script.Info.Path = install
    await script.commit()
    native = (
        await client.post(
            "/api/scripts/user/config-dir", json={"scriptId": sid, "userId": first}
        )
    ).json()
    assert native["code"] == 200
    assert native["path"] == str(install / "config")


@pytest.mark.asyncio
async def test_maa_legacy_document_preserves_nested_identities():
    """用真实升级管道转换旧集合键和日期槽位，保留托管、账号及计划的历史 UID。"""
    sid, uid, pid = map(str, (uuid4(), uuid4(), uuid4()))
    MaaUserConfig.related_config = {}
    scripts = ConfigCollection.build([MaaConfig])
    old = {
        "instances": [{"uid": sid, "type": "MaaConfig"}],
        sid: {
            "Info": {"Name": "原托管"},
            "SubConfigsInfo": {
                "UserData": {
                    "instances": [{"uid": uid, "type": "MaaUserConfig"}],
                    uid: {"Info": {"Name": "原账号"}},
                }
            },
        },
    }
    converted = convert_legacy(old, scripts)
    scripts = ConfigCollection.build([MaaConfig], payload=converted)
    await scripts.activate()
    assert list(map(str, scripts.keys())) == [sid]
    assert list(map(str, scripts[sid].users.keys())) == [uid]
    assert scripts[sid].users[uid].Info.Name == "原账号"
    plans = ConfigCollection.build([MaaPlanConfig])
    converted = convert_legacy(
        {
            "instances": [{"uid": pid, "type": "MaaPlanConfig"}],
            pid: {"Days": {"Monday": {"Stage": "1-7"}, "8": {"Stage": "CE-6"}}},
        },
        plans,
    )
    plan = converted["data"][pid]
    assert plan["Monday"]["Stage"] == "1-7" and plan["Day8"]["Stage"] == "CE-6"


@pytest.mark.asyncio
async def test_plugin_typed_routes_drain_and_unmount():
    """类型化专项 API 纳入调用门；停用等待在途请求，卸载后路径和 OpenAPI 一并移除。"""
    from fastapi import APIRouter

    app, router = FastAPI(), APIRouter()
    started, release = asyncio.Event(), asyncio.Event()

    @router.post("/plugin-owned")
    async def owned():
        """保持请求在途，供测试确认调用门的真实等待边界。"""
        started.set()
        await release.wait()
        return {"done": True}

    registry, gate = HttpRegistry(), CallGate()
    registry.bind_app(app)
    registry.mount("maa", [], router=router, gate=gate)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        pending = asyncio.create_task(client.post("/plugin-owned"))
        await asyncio.wait_for(started.wait(), 2)
        gate.accepting = False
        drain = asyncio.create_task(gate.drain())
        await asyncio.sleep(0)
        assert not drain.done()
        release.set()
        assert (await pending).json() == {"done": True}
        await asyncio.wait_for(drain, 2)
        assert "/plugin-owned" in app.openapi()["paths"]
        registry.unmount("maa")
        assert (await client.post("/plugin-owned")).status_code == 404
        assert "/plugin-owned" not in app.openapi()["paths"]
