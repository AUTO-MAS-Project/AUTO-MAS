"""用外部示例通过公共 HTTP 接口编辑托管、账号和计划。"""

import asyncio
import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Annotated, Literal

import pytest
import pytest_asyncio
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import Field

from app.api import config_triggers, plan_router, plugin_router, scripts_router
from app.config import (
    UI_MASKED_VALUE,
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigManager,
    DeclarativeBlock,
    HostBlock,
    PluginBlock,
    Trigger,
    UiSection,
    UiStep,
    config_manager,
    select,
    trigger_field,
    ui,
)
from app.core import Config, Plugin
from app.core.background_tasks import BackgroundTaskRegistry
from app.models.config import (
    GeneralConfig,
    GeneralUserConfig,
    PluginRecord,
    PluginRegistryCollection,
)
from app.utils.common.config import archive
from app.utils.common.config.restore import ConfigRestorePool

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def editor_client():
    app = FastAPI()
    for router in (scripts_router, plan_router, plugin_router, config_triggers.router):
        app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def editors(monkeypatch, editor_client, isolated_app_paths):
    monkeypatch.syspath_prepend(Config.source_path / "examples/demo15/src")
    from demo15 import PLUGIN

    scripts = ConfigCollection.build(
        [GeneralConfig],
        keep_unknown_types=True,
        file=Config.config_path / "scripts.yaml",
    )
    plans = ConfigCollection.build(keep_unknown_types=True)
    registry = PluginRegistryCollection.build()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setattr(Config, "plugin_registry", registry)
    monkeypatch.setattr(Plugin, "script_types", {})
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

        async def post(path, **body):
            response = await editor_client.post(path, json=body)
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
        assert ui["blocks"] is None
        assert ui["pluginName"] == "demo15"
        if path != "scripts":
            assert ui["backupTargets"] == [] and ui["nativeSession"] is None
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
    assert builtin["ui"]["pluginName"] is None


@pytest.fixture
def local_crypto(monkeypatch):
    crypto = import_module("app.config.fields.encrypted")
    monkeypatch.setattr(crypto, "dpapi_encrypt", lambda value: value.encode().hex())
    monkeypatch.setattr(
        crypto, "dpapi_decrypt", lambda value: bytes.fromhex(value).decode()
    )


@pytest.mark.parametrize(
    ("path", "group", "secret", "change"),
    [
        ("scripts", "Run", "Token", {"Mode": "repeat", "Retries": 2}),
        ("scripts/user", "Info", "Password", {"Id": "alice"}),
    ],
)
async def test_masked_partial_update(
    editors, local_crypto, path, group, secret, change
):
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


async def test_flow_detail_registry_and_options(editors, editor_client):
    post, targets = editors
    ids, script = targets["scripts"]
    detail = (await post("scripts/get", **ids))["ui"]
    assert detail["steps"] == [
        {"key": "env", "title": "环境"},
        {"key": "run", "title": "运行"},
    ]
    env = {"step": "env", "collapsible": False, "default_collapsed": False}
    assert detail["sections"] == {
        "group:Info": env,
        "group:Setup": env,
        "group:Run": {"step": "run", "collapsible": True, "default_collapsed": True},
    }
    path_hint = next(h for h in detail["hints"]["Info"] if h["field"] == "Path")
    assert (
        path_hint["component"] == "path"
        and path_hint["action_ref"] == "Info.DiscoverPath"
    )
    setup = {h["field"]: h for h in detail["hints"]["Setup"]}
    profile = setup["Profile"]
    assert profile["option_source"] == "profiles" and profile["depends_on"] == {
        "region": "Setup.Region"
    }
    assert profile["component"] == "select" and "options" not in profile
    assert detail["nativeSession"] == "view"
    assert detail["backupTargets"] == [{"key": "run", "kind": "script"}]

    record_id = str(Plugin.trigger_owner(script))
    registry = await post("plugin/registry/get", recordId=record_id)
    assert registry["data"][record_id]["providedScript"]["firstAccountMode"] == "wizard"
    choices = []
    for region in setup["Region"]["options"]:
        url = f"plugin/{detail['pluginName']}/options/{profile['option_source']}"
        response = (
            await editor_client.get(url, params={"region": region["value"]})
        ).json()
        options = response.pop("data")
        assert response == {"code": 200, "status": "success", "message": "ok"}
        assert options and all(option["label"] for option in options)
        choices.append({option["value"] for option in options})
    assert len(choices) == 2 and choices[0].isdisjoint(choices[1])

    await Config.flush()
    persisted = yaml.safe_load(
        (Config.config_path / "scripts.yaml").read_text(encoding="utf-8")
    )
    listing = await post("scripts/get")
    for document in (persisted, await script.to_dict(), listing["data"]):
        keys = json.dumps(document)
        assert all(
            f'"{key}"' not in keys
            for key in (
                "ui",
                "steps",
                "sections",
                "action_ref",
                "depends_on",
                "option_source",
                "nativeSession",
                "pluginName",
                "backupTargets",
                "firstAccountMode",
            )
        )


async def test_editor_capabilities_follow_scope_and_supported_modes(
    editors, monkeypatch
):
    post, targets = editors
    _, script = targets["scripts"]
    user_ids, user = targets["scripts/user"]
    owner = Plugin.trigger_owner(script)
    decl = Plugin.script_types[owner]
    (pool,) = decl.restore_pools
    monkeypatch.setitem(
        Plugin.script_types,
        owner,
        replace(
            decl,
            restore_pools=(
                replace(pool, key="second", editor_scope="user"),
                pool,
                replace(pool, key="first", kind="user", editor_scope="user"),
                replace(pool, key="legacy", editor_scope=None),
            ),
        ),
    )
    monkeypatch.setattr(type(user), "ui_native_session", "config")
    detail = (await post("scripts/user/get", **user_ids))["ui"]
    assert detail["nativeSession"] is None
    assert detail["backupTargets"] == [
        {"key": "second", "kind": "script"},
        {"key": "first", "kind": "user"},
    ]
    monkeypatch.setattr(type(user), "ui_native_session", "view")
    assert (await post("scripts/user/get", **user_ids))["ui"]["nativeSession"] == "view"
    assert (await post("plan/get", **targets["plan"][0]))["ui"]["backupTargets"] == []


async def test_discover_path_uses_the_lock_and_only_updates_path(editors, monkeypatch):
    import demo15

    post, targets = editors
    ids, entry = targets["scripts"]
    manager = ConfigManager()
    monkeypatch.setattr(
        manager, "iter_persist_roots", config_manager.iter_persist_roots
    )
    background = BackgroundTaskRegistry()
    manager.initialize_triggers(
        background, max_running=1, resolve_owner=Plugin.trigger_owner
    )
    monkeypatch.setattr(config_triggers, "config_manager", manager)
    command = {
        "configUid": ids["scriptId"],
        "group": "Info",
        "field": "DiscoverPath",
        "value": True,
    }
    before = await entry.to_dict()
    try:
        ticket = await entry.lock_s()
        try:
            rejected = await post("config/triggers/write", **command)
            assert (rejected["code"], rejected["message"]) == (
                409,
                "trigger_target_locked",
            )
            assert await entry.to_dict() == before
        finally:
            await entry.unlock(ticket)
        accepted = await post("config/triggers/write", **command)
        assert accepted["code"] == 200 and accepted["data"]
        assert await background.get_group("config-triggers").drain(2)
        outcome = await post("config/triggers/result", taskId=accepted["data"])
        assert outcome["data"]["state"] == "succeeded", outcome
        before["Info"]["Path"] = str(Path(demo15.__file__).resolve().parent)
        assert await entry.to_dict() == before
    finally:
        await manager.shutdown_triggers()


async def test_first_account_concurrent_and_ordered(editors, monkeypatch):
    from demo15 import PLUGIN

    post, _ = editors
    script_id, script = await Config.add_script("Demo15")
    ids = {"scriptId": str(script_id)}
    release_hook = asyncio.Event()
    initialized = []

    async def on_user_added(_plugin, _script, user):
        initialized.append(str(user.uid))
        await release_hook.wait()

    monkeypatch.setattr(PLUGIN, "on_user_added", on_user_added)
    async with config_manager.execution_gate():
        requests = [
            asyncio.create_task(post("scripts/user/add", **ids, firstOnly=True))
            for _ in range(2)
        ]
        await asyncio.sleep(0)
    try:
        # 重试在首个请求的提交后钩子仍在等待时就能取回账号。
        done, _ = await asyncio.wait(
            requests, timeout=2, return_when=asyncio.FIRST_COMPLETED
        )
        assert done
    finally:
        release_hook.set()
        responses = await asyncio.gather(*requests)
    first = initialized[0]
    assert all(r["code"] == 200 and r["userId"] == first for r in responses)
    assert initialized == [first] and list(map(str, script.users.keys())) == [first]
    second = (await post("scripts/user/add", **ids, firstOnly=False))["userId"]
    assert first != second and initialized == [first, second]
    await post("scripts/user/order", **ids, indexList=[second, first])
    assert (await post("scripts/user/add", **ids, firstOnly=True))["userId"] == second


async def test_first_account_retry_after_post_commit_failure(editors, monkeypatch):
    from demo15 import PLUGIN

    post, _ = editors
    script_id, script = await Config.add_script("Demo15")
    ids = {"scriptId": str(script_id), "firstOnly": True}

    async def fail(_plugin, _script, _user):
        raise RuntimeError("初始化账号失败")

    monkeypatch.setattr(PLUGIN, "on_user_added", fail)
    failed = await post("scripts/user/add", **ids)
    assert failed["status"] == "error" and "初始化账号失败" in failed["message"]
    (uid,) = script.users.keys()
    retry = await post("scripts/user/add", **ids)
    assert retry["code"] == 200 and retry["userId"] == str(uid)
    assert list(script.users.keys()) == [uid]


async def test_script_backup_lifecycle(editors, editor_client, local_crypto):
    post, targets = editors
    ids, script = targets["scripts"]
    scope = dict(**ids, target="run")
    saved = {"Mode": "repeat", "Retries": 3}
    current = {"Mode": "once", "Retries": 7}
    assert (
        await post("scripts/update", **ids, data={"Run": {**saved, "Token": "old"}})
    )["code"] == 200
    ensured = await post("scripts/backup/ensure", **scope)
    assert ensured["code"] == 200 and ensured["created"]
    selected = dict(**scope, time=ensured["time"])
    listing = (await editor_client.get("scripts/backup/list", params=scope)).json()
    assert listing["data"] == [{"time": selected["time"], "base": None}]
    assert not (await post("scripts/backup/ensure", **scope))["created"]
    assert (
        await post("scripts/update", **ids, data={"Run": {**current, "Token": "keep"}})
    )["code"] == 200
    before = await script.to_dict()
    preview = (
        await editor_client.get("scripts/backup/preview", params=selected)
    ).json()
    file = (
        await editor_client.get(
            "scripts/backup/file", params={**selected, "path": "run.json"}
        )
    ).json()
    assert file["code"] == preview["code"] == 200
    assert preview["data"]["files"] == [{"path": "run.json", "size": file["size"]}]
    assert json.loads(file["content"]) == saved
    assert await script.to_dict() == before

    (snapshot,) = Config.data_path.rglob("run.json")
    for invalid in (
        "{",
        json.dumps({**saved, "Token": "overwrite"}),
        json.dumps({**saved, "Retries": -1}),
    ):
        snapshot.write_text(invalid, encoding="utf-8")
        failed = await post("scripts/backup/restore", **selected)
        assert failed["code"] == 400 and failed["message"]
        assert await script.to_dict() == before
    snapshot.write_text(file["content"], encoding="utf-8")
    assert (await post("scripts/backup/restore", **selected))["code"] == 200
    after = (await post("scripts/get", **ids))["data"][ids["scriptId"]]["Run"]
    assert after == {**saved, "Token": UI_MASKED_VALUE}
    assert script.Run.Token == "keep"


@pytest.mark.parametrize(
    ("scope", "user", "expected"),
    [
        ("user", None, 400),
        (None, None, 400),
        ("user", "other", 400),
        ("script", "other", 400),
        ("user", "own", 200),
        ("script", None, 200),
    ],
)
async def test_backup_account_scope(
    editors, editor_client, monkeypatch, scope, user, expected
):
    post, targets = editors
    ids, script = targets["scripts"]
    owner = Plugin.trigger_owner(script)
    decl = Plugin.script_types[owner]
    (pool,) = decl.restore_pools
    monkeypatch.setitem(
        Plugin.script_types,
        owner,
        replace(decl, restore_pools=(replace(pool, editor_scope=scope),)),
    )
    params = dict(**ids, target=pool.key)
    if user == "other":
        other_id, _ = await Config.add_script("Demo15")
        params["userId"] = (await post("scripts/user/add", scriptId=str(other_id)))[
            "userId"
        ]
    elif user == "own":
        params["userId"] = targets["scripts/user"][0]["userId"]
    response = (await editor_client.get("scripts/backup/list", params=params)).json()
    assert response["code"] == expected, response
    if expected == 400:
        assert ("不属于" if user else "userId") in response["message"]


@pytest.mark.parametrize("failure", ["copy", "after_files", None])
async def test_cross_base_restore_keeps_original_files_on_failure(
    editors, monkeypatch, tmp_path, failure
):
    post, _ = editors
    script_uid = Config.ScriptConfig.add(GeneralConfig)
    await Config.ScriptConfig.commit()
    users = Config.ScriptConfig[script_uid].UserData
    user_uid = users.add(GeneralUserConfig, payload={"Info": {"Base": "independent"}})
    await users.commit()
    user = users[user_uid]
    root, live = tmp_path / "snapshots", tmp_path / "live"
    snapshot = archive.archive_files(
        {"engine/settings/run": "saved", "root.txt": "saved"}, root
    )
    archive.write_backup_base(snapshot, "shared")
    original = {
        "engine/settings/old": b"old",
        "engine/unmanaged": b"keep",
        "whole/old": b"old",
        "root.txt": b"old",
    }
    for rel, data in original.items():
        path = live / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def backup_root(ctx):
        return root

    async def set_base(ctx, base):
        user.Info.Base = base
        await user.commit()

    async def restore(ctx, ts):
        assert user.Info.Base == "shared"
        archive.restore_dir(root, ts, live / "whole")
        if failure == "copy":
            copyfile = archive.shutil.copyfile

            def fail_last(source, dest):
                if source == snapshot / "root.txt":
                    raise PermissionError("文件正在使用")
                return copyfile(source, dest)

            monkeypatch.setattr(archive.shutil, "copyfile", fail_last)
        archive.restore_files(snapshot, live, dir_map={"engine": live / "engine"})
        if failure == "after_files":
            raise ValueError("回填失败")

    pool = ConfigRestorePool(
        key="mas",
        kind="user",
        mas_base="tri_state",
        backup_root=backup_root,
        set_base=set_base,
        restore=restore,
    )
    monkeypatch.setattr(Config, "_restore_pool_resolver", lambda _: [pool])
    response = await post(
        "scripts/backup/restore",
        scriptId=str(script_uid),
        userId=str(user_uid),
        target="mas",
        time=snapshot.name,
    )
    files = {key: path.read_bytes() for key, path in archive.dir_files(live).items()}
    if failure:
        assert response["status"] == "error" and user.Info.Base == "independent"
        assert files == original
    else:
        assert response["code"] == 200 and user.Info.Base == "shared"
        assert files == {
            "engine/settings/run": b"saved",
            "engine/unmanaged": b"keep",
            "root.txt": b"saved",
            "whole/engine/settings/run": b"saved",
            "whole/root.txt": b"saved",
        }


async def test_overlapping_restores_to_shared_directory(editors, monkeypatch, tmp_path):
    post, targets = editors
    ids, script = targets["scripts"]
    other_id, _ = await Config.add_script("Demo15")
    root, live = tmp_path / "backups", tmp_path / "shared"
    first = archive.archive_files({"config": "first"}, root)
    second = archive.archive_files({"config": "second"}, root)
    started, finish = asyncio.Event(), asyncio.Event()

    async def restore(ctx, ts):
        archive.restore_dir(root, ts, live)
        if ts == first.name:
            started.set()
            await finish.wait()
            raise ValueError("回填失败")

    owner = Plugin.trigger_owner(script)
    decl = Plugin.script_types[owner]
    (pool,) = decl.restore_pools
    monkeypatch.setitem(
        Plugin.script_types,
        owner,
        replace(decl, restore_pools=(replace(pool, restore=restore),)),
    )
    endpoint = "scripts/backup/restore"
    failing = asyncio.create_task(
        post(endpoint, **ids, target=pool.key, time=first.name)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        following = asyncio.create_task(
            post(endpoint, scriptId=str(other_id), target=pool.key, time=second.name)
        )
        await asyncio.sleep(0)
    finally:
        finish.set()
        failed = await failing
    assert failed["status"] == "error" and (await following)["status"] == "success"
    assert (live / "config").read_text() == "second"


@pytest.mark.parametrize(
    ("steps", "sections", "marker", "error"),
    [
        ((UiStep("a"), UiStep("a")), {}, ui(), "ui_steps"),
        ((), {"group:Setup": UiSection(step="missing")}, ui(), "未知步骤"),
        ((), {"Setup": UiSection()}, ui(), "分区"),
        ((), {"table:": UiSection()}, ui(), "分区"),
        ((), {}, select(depends_on={"x": "Region"}), "字段"),
        ((), {}, select(depends_on={"x": "Setup.Missing"}), "字段"),
        ((), {}, ui(action_ref="Setup.Region"), "Trigger"),
    ],
)
async def test_invalid_editor_declarations_fail_at_definition(
    steps, sections, marker, error
):
    class Options(ConfigGroup):
        Region: str = ""
        Profile: Annotated[str, marker] = ""

    with pytest.raises(ValueError, match=error):

        class Entry(ConfigEntry):
            ui_steps = steps
            ui_sections = sections
            Setup: Options = Field(default_factory=Options)


@pytest.mark.parametrize(
    ("blocks", "steps", "sections", "error"),
    [
        ((), (), {}, "非空序列"),
        (("unexpected",), (), {}, "ui_blocks 区块"),
        ((HostBlock("unknown"),), (), {}, "HostBlock"),
        ((HostBlock("webhooks"), HostBlock("webhooks")), (), {}, "HostBlock"),
        ((PluginBlock(" "),), (), {}, "page_id"),
        ((PluginBlock("stage"), PluginBlock("stage")), (), {}, "page_id"),
        ((DeclarativeBlock(()),), (), {}, "DeclarativeBlock"),
        ((DeclarativeBlock(("Unknown",)),), (), {}, "区块分组"),
        (
            (DeclarativeBlock(("Options",)), PluginBlock("stage", ("Options",))),
            (),
            {},
            "区块分组",
        ),
        ((HostBlock("webhooks"),), (UiStep("setup"),), {}, "ui_steps"),
        (
            (HostBlock("webhooks"),),
            (),
            {"group:Options": UiSection(step="setup")},
            "分区步骤",
        ),
        (
            (DeclarativeBlock(("Options",)), PluginBlock("stage", ("Actions",))),
            (),
            {},
            "action_ref.*同一区块",
        ),
    ],
)
async def test_invalid_block_declarations_fail_at_definition(
    blocks, steps, sections, error
):
    class OptionFields(ConfigGroup):
        Path: Annotated[str, ui(action_ref="Actions.Discover")] = ""

    class ActionFields(ConfigGroup):
        Discover: Trigger = None

    with pytest.raises(ValueError, match=error):

        class Entry(ConfigEntry):
            ui_blocks = blocks
            ui_steps = steps
            ui_sections = sections
            Options: OptionFields = Field(default_factory=OptionFields)
            Actions: ActionFields = Field(default_factory=ActionFields)

            @trigger_field("Actions.Discover")
            async def discover(self):
                return None


async def test_option_source_is_one_segment_and_replaces_literal_inference():
    from app.config.fields.hints import hint_for_field

    for invalid in ("", ".", "../profiles", "nested/profiles", "a..b"):
        with pytest.raises(ValueError, match="option_source"):
            select(option_source=invalid)

    class Options(ConfigGroup):
        Profile: Annotated[Literal["a", "b"], select(option_source="profiles")] = "a"

    hint = hint_for_field("Profile", Options.model_fields["Profile"])
    assert hint["component"] == "select" and "options" not in hint
