"""用外部示例通过公共 HTTP 接口编辑托管、账号和计划。"""

from importlib import import_module
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import plan_router, scripts_router
from app.config import UI_MASKED_VALUE, ConfigCollection, config_manager
from app.core import Config, Plugin
from app.models.config import GeneralConfig, PluginRecord, PluginRegistryCollection

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def editors(monkeypatch):
    monkeypatch.syspath_prepend(
        Path(__file__).resolve().parents[2] / "examples/demo15/src"
    )
    from demo15 import PLUGIN

    scripts = ConfigCollection.build([GeneralConfig], keep_unknown_types=True)
    plans = ConfigCollection.build(keep_unknown_types=True)
    registry = PluginRegistryCollection.build()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setattr(Config, "plugin_registry", registry)
    for collection in (scripts, plans, registry):
        await collection.activate()
    uid = registry.add(
        PluginRecord, payload={"info": {"plugin_name": "demo15", "state": "disabled"}}
    )
    await registry.commit()
    record = registry[uid]
    record._plugin_cls = PLUGIN
    await Plugin.enable(record)
    try:
        script_id, script = await Config.add_script("Demo15")
        user_id, user = await Config.add_user(str(script_id))
        plan_id, plan = await Config.add_plan("Demo15PlanConfig")
        app = FastAPI()
        app.include_router(scripts_router)
        app.include_router(plan_router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def post(path, **body):
                response = await client.post(f"/api/{path}", json=body)
                response.raise_for_status()
                return response.json()

            yield (
                post,
                {
                    "scripts": ({"scriptId": str(script_id)}, script),
                    "scripts/user": (
                        {"scriptId": str(script_id), "userId": str(user_id)},
                        user,
                    ),
                    "plan": ({"planId": str(plan_id)}, plan),
                },
            )
    finally:
        await Plugin.disable(record)


async def test_lists_details_and_locks(editors):
    post, targets = editors
    for path, (ids, entry) in targets.items():
        scope = {"scriptId": ids["scriptId"]} if path == "scripts/user" else {}
        listing = await post(f"{path}/get", **scope)
        uid = str(entry.uid)
        assert uid in listing["data"] and "ui" not in listing
        assert "ui" not in listing["data"][uid]

        detail = await post(f"{path}/get", **ids)
        ui = detail["ui"]
        assert ui["configUid"] == uid and ui["i18nNamespace"] == "plugins.demo15.config"
        assert any(
            field["editable"] for fields in ui["hints"].values() for field in fields
        )
        assert isinstance(ui["tables"], list)
        ticket = await entry.lock_s()
        try:
            locked = (await post(f"{path}/get", **ids))["ui"]["hints"]
            assert locked.keys() == ui["hints"].keys()
            assert all(
                not field["editable"] for fields in locked.values() for field in fields
            )
        finally:
            await entry.unlock(ticket)

    builtin_id = Config.ScriptConfig.add(GeneralConfig)
    await Config.ScriptConfig.commit()
    builtin = await post("scripts/get", scriptId=str(builtin_id))
    assert builtin["ui"]["i18nNamespace"] is None


@pytest.mark.parametrize(
    ("path", "group", "secret", "change"),
    [
        ("scripts", "Run", "Token", {"Mode": "repeat", "Retries": 2}),
        ("scripts/user", "Info", "Password", {"Id": "alice"}),
    ],
)
async def test_masked_partial_update(editors, monkeypatch, path, group, secret, change):
    crypto = import_module("app.config.fields.encrypted")
    monkeypatch.setattr(crypto, "dpapi_encrypt", lambda value: value.encode().hex())
    monkeypatch.setattr(
        crypto, "dpapi_decrypt", lambda value: bytes.fromhex(value).decode()
    )
    post, targets = editors
    ids, entry = targets[path]
    saved = await post(f"{path}/update", **ids, data={group: {secret: "original"}})
    assert saved["status"] == "success", saved
    uid = str(entry.uid)
    detail = await post(f"{path}/get", **ids)
    hints = {item["field"]: item for item in detail["ui"]["hints"][group]}
    assert hints[secret]["masked"] and hints[secret]["secret"]
    placeholder = detail["data"][uid][group][secret]
    assert placeholder == UI_MASKED_VALUE
    saved = await post(
        f"{path}/update", **ids, data={group: {secret: placeholder, **change}}
    )
    assert saved["status"] == "success" and saved["fieldErrors"] == {}
    after = (await post(f"{path}/get", **ids))["data"][uid][group]
    assert all(after[key] == value for key, value in change.items())
    assert after[secret] == placeholder
    restored = type(entry).build(payload=await entry.to_dict())
    await restored.activate()
    assert getattr(getattr(restored, group), secret) == "original"
    if path == "scripts":
        assert hints["Retries"]["min"] == 0
        assert [item["value"] for item in hints["Mode"]["options"]] == [
            "once",
            "repeat",
        ]
    else:
        assert hints["UsePassword"]["component"] == "switch"
        plan_hint = next(
            h for h in detail["ui"]["hints"]["info"] if h["field"] == "plan_id"
        )
        assert {"value": str(targets["plan"][1].uid)} in plan_hint["options"]
        await post(f"{path}/update", **ids, data={group: {"UsePassword": False}})
        hidden = await post(f"{path}/get", **ids)
        assert secret not in hidden["data"][uid][group]
        assert secret not in {item["field"] for item in hidden["ui"]["hints"][group]}


async def test_transposed_plan_update(editors):
    post, targets = editors
    ids, plan = targets["plan"]
    before = await post("plan/get", **ids)
    assert before["ui"]["tables"] == [
        {
            "key": "tasks",
            "columns": ["First", "Second"],
            "rows": ["Enabled", "Count"],
            "transpose": True,
        }
    ]
    saved = await post(
        "plan/update", **ids, data={"First": {"Count": 3}, "Second": {"Enabled": False}}
    )
    assert saved["status"] == "success", saved
    document = (await post("plan/get", **ids))["data"][str(plan.uid)]
    assert document["First"] == {"Enabled": True, "Count": 3}
    assert document["Second"] == {"Enabled": False, "Count": 1}


@pytest.mark.parametrize(
    ("path", "patch", "errors"),
    [
        (
            "scripts",
            {"info": {"name": "changed"}, "Run": {"Retries": -1}},
            {"Run.Retries": "Input should be greater than or equal to 0"},
        ),
        (
            "scripts/user",
            {"Info": {"Id": "changed", "UsePassword": "invalid"}},
            {
                "Info.UsePassword": "Input should be a valid boolean, unable to interpret input"
            },
        ),
        (
            "plan",
            {"First": {"Count": -1}, "Second": {"Enabled": False, "Unknown": 0}},
            {
                "First.Count": "Input should be greater than or equal to 0",
                "Second.Unknown": "Extra inputs are not permitted",
            },
        ),
        (
            "scripts",
            {
                "game": {"device_id": "00000000-0000-0000-0000-000000000001"},
                "Run": {"Retries": 4},
            },
            {"game.device_id": "Value error, 选择设备前须先选择游戏目标"},
        ),
    ],
)
async def test_rejected_patch_is_atomic(editors, path, patch, errors):
    post, targets = editors
    ids, _ = targets[path]
    before = (await post(f"{path}/get", **ids))["data"]
    result = await post(f"{path}/update", **ids, data=patch)
    assert result["status"] == "error" and result["message"]
    assert result["fieldErrors"] == errors
    assert (await post(f"{path}/get", **ids))["data"] == before
