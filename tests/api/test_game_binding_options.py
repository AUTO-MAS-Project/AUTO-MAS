"""游戏目标候选、保存校验和历史绑定清理共用后端能力。"""

from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from maa_adapter.plugin import Plugin as MaaPlugin
from src_adapter.plugin import Plugin as SrcPlugin
from whimbox_adapter.plugin import Plugin as WhimboxPlugin

from app.api import games_router, scripts_router
from app.config import ConfigCollection, config_manager
from app.core import Config, GameManager, Plugin
from app.core.plugin.adapters import ScriptAdapterRuntime
from app.models.config import GeneralConfig, GeneralUserConfig, PluginRecord
from app.models.config.game import GameEntry
from app.models.task import TaskScriptItem
from app.plugin.base.game import GameControl
from app.plugin.calls import CallGate
from app.task.game import GameSession
from app.task.general.registration import build_config_handler


@pytest_asyncio.fixture
async def binding_host(isolated_app_paths, monkeypatch):
    games = ConfigCollection.build([GameEntry])
    scripts = ConfigCollection.build([GeneralConfig])
    monkeypatch.setitem(config_manager._collections, "games", games)
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", ConfigCollection.build())
    monkeypatch.setattr(
        Config, "_script_config_handlers", {GeneralConfig: build_config_handler()}
    )
    monkeypatch.setattr(Plugin, "script_types", {})
    await games.activate()
    emulator = games.add(GameEntry, payload={"info": {"type": "emulator"}})
    native = games.add(GameEntry, payload={"info": {"type": "client"}})
    await games.commit()
    for game in games.values():
        game._game_control = Mock(spec=GameControl)
    app = FastAPI()
    app.include_router(games_router)
    app.include_router(scripts_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, scripts, str(emulator), str(native)


async def binding_options(client, script_id, *, user_id=None):
    body = {"scriptId": str(script_id)}
    if user_id is not None:
        body["userId"] = str(user_id)
    response = (await client.post("/api/games/binding/options", json=body)).json()
    assert response["code"] == 200, response
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "plugin_type",
        "plugin_name",
        "decl_patch",
        "supported",
        "overrides",
        "native_allowed",
    ),
    [
        (MaaPlugin, "maa_adapter", {}, True, True, False),
        (SrcPlugin, "src_adapter", {}, True, True, False),
        (MaaPlugin, "maa_adapter", {"game_kinds": ()}, True, True, True),
        (WhimboxPlugin, "whimbox_adapter", {}, False, False, False),
        (
            MaaPlugin,
            "maa_adapter",
            {"supports_game_binding": False},
            False,
            False,
            False,
        ),
        (
            MaaPlugin,
            "maa_adapter",
            {"supports_account_game_override": False},
            True,
            False,
            False,
        ),
    ],
)
async def test_plugin_binding_capabilities(
    binding_host,
    monkeypatch,
    plugin_type,
    plugin_name,
    decl_patch,
    supported,
    overrides,
    native_allowed,
):
    client, scripts, emulator, native = binding_host
    if decl_patch:
        monkeypatch.setattr(
            plugin_type, "decl", replace(plugin_type.decl, **decl_patch)
        )
    record = PluginRecord.build(info={"plugin_name": plugin_name})
    plugin = plugin_type(record=record)
    await ScriptAdapterRuntime(plugin).system_enable()
    await scripts.activate()
    script_id = scripts.add(plugin.script_type)
    await scripts.commit()
    script = scripts[script_id]
    user_id = script.users.add(plugin.user_type)
    await script.users.commit()
    account = script.users[user_id]

    for owner in (None, account):
        response = await binding_options(
            client, script_id, user_id=owner.uid if owner is not None else None
        )
        assert response["supported"] is supported
        assert response["accountOverrideSupported"] is overrides
        allowed = supported and (owner is None or overrides)
        options = {item["value"]: item["disabledReason"] for item in response["data"]}
        assert set(options) == ({emulator, native} if allowed else set())
        for target, compatible in ((emulator, True), (native, native_allowed)):
            refusal = await GameManager.validate_binding(
                str(script_id), {"game": {"game_id": target}}, owner=owner
            )
            assert (refusal is None) is (allowed and compatible)
            if allowed:
                assert options[target] == refusal


@pytest.mark.asyncio
async def test_disabling_game_management_keeps_existing_bindings_clearable(
    binding_host,
):
    client, scripts, emulator, native = binding_host
    await scripts.activate()
    script_id = scripts.add(
        GeneralConfig,
        payload={"Game": {"Enabled": True}, "game": {"game_id": emulator}},
    )
    await scripts.commit()
    script = scripts[script_id]
    user_id = script.UserData.add(
        GeneralUserConfig, payload={"game": {"unavailable_reason": "旧目标不可用"}}
    )
    await script.UserData.commit()
    body = {"scriptId": str(script_id), "userId": str(user_id)}
    before = await binding_options(client, script_id, user_id=user_id)
    assert before["supported"] and before["accountOverrideSupported"]
    options = {item["value"]: item["disabledReason"] for item in before["data"]}
    assert options[emulator] is None
    assert options[native]
    assert await GameManager.validate_binding(
        str(script_id), {"Game": {"Enabled": False}, "game": {"game_id": emulator}}
    )
    assert (
        await GameManager.validate_binding(
            str(script_id), {"Game": {"Type": "Client"}, "game": {"game_id": native}}
        )
        is None
    )

    disabled = await client.post(
        "/api/scripts/update",
        json={"scriptId": str(script_id), "data": {"Game": {"Enabled": False}}},
    )
    assert disabled.json()["code"] == 200, disabled.json()
    for owner_id in (None, user_id):
        response = await binding_options(client, script_id, user_id=owner_id)
        assert not response["supported"] and not response["accountOverrideSupported"]
        assert response["data"] == []
    assert await GameManager.validate_binding(
        str(script_id), {"game": {"game_id": emulator}}
    )

    session = GameSession(TaskScriptItem.build(), script)
    await session.select()
    assert session.game_uid is None
    assert str(script.game.game_id) == emulator

    reset = {"game": {"game_id": "-", "device_id": "-"}}
    for endpoint, ids in (
        ("/api/scripts/user/update", body),
        ("/api/scripts/update", {"scriptId": str(script_id)}),
    ):
        saved = await client.post(endpoint, json={**ids, "data": reset})
        assert saved.json()["code"] == 200, saved.json()
    assert script.game.game_id == "-"
    assert script.UserData[user_id].game.unavailable_reason == ""


@pytest.mark.asyncio
async def test_plugin_game_kind_narrows_binding_targets(binding_host, monkeypatch):
    """插件按当前配置判定的游戏类型（ScriptTypeDecl.game_kind）收窄候选与保存校验。"""
    client, scripts, emulator, native = binding_host
    monkeypatch.setattr(
        MaaPlugin,
        "decl",
        replace(
            MaaPlugin.decl,
            game_kinds=("emulator", "client"),
            game_kind=lambda script, patch: "emulator",
        ),
    )
    record = PluginRecord.build(info={"plugin_name": "maa_adapter"})
    plugin = MaaPlugin(record=record)
    await ScriptAdapterRuntime(plugin).system_enable()
    monkeypatch.setitem(Plugin._calls, record.uid, CallGate())
    await scripts.activate()
    script_id = scripts.add(plugin.script_type)
    await scripts.commit()

    response = await binding_options(client, script_id)
    options = {item["value"]: item["disabledReason"] for item in response["data"]}
    assert options[emulator] is None
    assert options[native]
    assert await GameManager.validate_binding(
        str(script_id), {"game": {"game_id": native}}
    )
    assert (
        await GameManager.validate_binding(
            str(script_id), {"game": {"game_id": emulator}}
        )
        is None
    )
