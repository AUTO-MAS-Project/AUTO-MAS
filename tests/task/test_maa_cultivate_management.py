"""全部已有干员托管：保留手工目标、首次注入与后续增量检查。"""

import asyncio
import importlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core.config.manager import AppConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.tools.cultivate import (
    Progression,
    append_owned_cultivate_targets,
)
from app.task.MAA.user_update import prepare_user_update
from tests.config_support import activate_config


def progression(elite=0, skill=1):
    return Progression(
        elite=elite, level=1, skill_level=skill, masteries={}, modules={}
    )


def catalog(*ids):
    return [{"value": key, "maxElite": 2, "maxSkillLevel": 7} for key in ids]


def test_owned_defaults_preserve_existing_rows_and_respect_reachable_goals():
    original = [
        {
            "operator_id": "custom",
            "goals": [{"kind": "elite", "to_level": 1, "state": "in_progress"}],
            "extra": 1,
        },
        {"operator_id": "empty", "goals": []},
    ]
    before = deepcopy(original)
    operators = catalog("custom", "empty", "new", "done", "unowned", "low", "unknown")
    operators[-2].update(maxElite=0, maxSkillLevel=4)
    result = append_owned_cultivate_targets(
        original,
        catalog=operators,
        progressions={
            "custom": progression(),
            "empty": progression(),
            "new": progression(),
            "done": progression(2, 7),
            "low": progression(),
            "unknown": progression(2, None),
        },
    )
    assert original == before
    assert result[:2] == before
    added = {item["operator_id"]: item["goals"] for item in result[2:]}
    assert set(added) == {"new", "low"}
    assert [(g["kind"], g["to_level"]) for g in added["new"]] == [
        ("elite", 2),
        ("skill", 7),
    ]
    assert [(g["kind"], g["to_level"]) for g in added["low"]] == [("skill", 4)]


@pytest.mark.asyncio
async def test_enabling_fails_without_a_reliable_owned_snapshot(monkeypatch):
    api = importlib.import_module("app.task.MAA.api_service")
    monkeypatch.setattr(
        api, "get_cultivate_skland_progression", AsyncMock(return_value=None)
    )
    user = MaaUserConfig()
    with pytest.raises(ValueError):
        await prepare_user_update(
            MaaConfig(), user, data={"Task": {"CultivateAllOwned": True}}
        )
    assert user.Task.CultivateAllOwned is False
    assert user.Task.CultivateTargets == "[]"


@pytest.mark.asyncio
async def test_every_run_discovers_new_owned_operators_from_empty_targets(
    monkeypatch, tmp_path
):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    task = SimpleNamespace(
        IfCultivate=True,
        CultivateAllOwned=True,
        CultivateTargets="[]",
        CultivateSklandAccount="bound",
        CultivateSklandUid="bound",
        CultivateAutoRaise=False,
    )
    config = SimpleNamespace(
        Task=task, Info=SimpleNamespace(Server="Official"), commit=AsyncMock()
    )
    proxy = SimpleNamespace(
        cur_user_config=config,
        cur_user_item=SimpleNamespace(name="user"),
        cur_user_uid="user",
        script_info=SimpleNamespace(script_id="script"),
        task_info=SimpleNamespace(task_id="task"),
        _missing_task_source_warned=set(),
        _cultivate_archive_dir=lambda: tmp_path,
        _set_cultivate_notice=AsyncMock(),
    )
    snapshot = AsyncMock(
        side_effect=[
            ({"one": progression()}, 1),
            ({"one": progression(), "two": progression()}, 2),
            None,
        ]
    )
    monkeypatch.setattr(module.maa_api, "get_cultivate_skland_progression", snapshot)
    monkeypatch.setattr(
        module, "Config", SimpleNamespace(config_path=tmp_path, proxy=None)
    )
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(return_value=catalog("one", "two", "unowned")),
    )

    async def prepare(**kwargs):
        return kwargs["targets"], None, True, ()

    monkeypatch.setattr(module.depot_cultivate_service, "prepare_cultivate", prepare)
    await AutoProxyTask._prepare_cultivate_injection(proxy, [])
    first = json.loads(task.CultivateTargets)
    assert [item["operator_id"] for item in first] == ["one"]
    await AutoProxyTask._prepare_cultivate_injection(proxy, [])
    second = json.loads(task.CultivateTargets)
    assert [item["operator_id"] for item in second] == ["one", "two"]
    assert second[0] == first[0]
    await AutoProxyTask._prepare_cultivate_injection(proxy, [])
    assert json.loads(task.CultivateTargets) == second
    assert proxy._cultivate_round_paused is True
    assert config.commit.await_count == 2
    assert snapshot.await_count == 3
    assert all(call.kwargs["force"] for call in snapshot.await_args_list)
    task.CultivateAllOwned = False
    task.CultivateTargets = "[]"
    await AutoProxyTask._prepare_cultivate_injection(proxy, [])
    assert snapshot.await_count == 3


@pytest_asyncio.fixture
async def managed_host():
    config = AppConfig.__new__(AppConfig)
    config._script_config_handlers = {
        MaaConfig: ScriptConfigHandler(
            user_config_class=MaaUserConfig, prepare_user_update=prepare_user_update
        )
    }
    config.ScriptConfig = ConfigCollection.build([MaaConfig])
    await config.ScriptConfig.activate()
    script_uid = config.ScriptConfig.add(MaaConfig)
    await config.ScriptConfig.commit()
    script = config.ScriptConfig[script_uid]
    user_uid = script.UserData.add(
        MaaUserConfig,
        payload={
            "Task": {
                "CultivateSklandAccount": "old-account",
                "CultivateSklandUid": "old-role",
                "CultivateTargets": '[{"operator_id":"custom","goals":[{"kind":"elite","to_level":1}]}]',
            }
        },
    )
    await script.UserData.commit()
    return config, script, script.UserData[user_uid]


@pytest.mark.asyncio
async def test_enabling_rejects_binding_changed_during_sync(
    monkeypatch, managed_host, isolated_app_paths
):
    config, script, user = managed_host
    before = user.Task.CultivateTargets
    started, complete = asyncio.Event(), asyncio.Event()

    async def fetch(*args, **kwargs):
        started.set()
        await complete.wait()
        return {"old-owned": progression()}, 1

    api = importlib.import_module("app.task.MAA.api_service")
    module = importlib.import_module("app.task.MAA.user_update")
    monkeypatch.setattr(api, "get_cultivate_skland_progression", fetch)
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(return_value=catalog("old-owned")),
    )
    pending = asyncio.create_task(
        config.update_user(
            str(script.uid), str(user.uid), {"Task": {"CultivateAllOwned": True}}
        )
    )
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(
        config.update_user(
            str(script.uid), str(user.uid), {"Task": {"CultivateSklandUid": "new-role"}}
        ),
        1,
    )
    complete.set()
    with pytest.raises(ValueError):
        await pending
    assert user.Task.CultivateSklandUid == "new-role"
    assert user.Task.CultivateAllOwned is False
    assert user.Task.CultivateTargets == before


@pytest.mark.asyncio
async def test_binding_is_checked_after_waiting_for_the_commit_gate(
    monkeypatch, managed_host, isolated_app_paths
):
    config, script, user = managed_host
    before = user.Task.CultivateTargets
    prepared = asyncio.Event()

    async def prepare(script, user, *, data):
        guard = await prepare_user_update(script, user, data=data)
        prepared.set()
        return guard

    config._script_config_handlers[MaaConfig] = ScriptConfigHandler(
        prepare_user_update=prepare
    )
    api = importlib.import_module("app.task.MAA.api_service")
    module = importlib.import_module("app.task.MAA.user_update")
    monkeypatch.setattr(
        api,
        "get_cultivate_skland_progression",
        AsyncMock(return_value=({"old-owned": progression()}, 1)),
    )
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(return_value=catalog("old-owned")),
    )
    async with config_manager.execution_gate():
        pending = asyncio.create_task(
            config.update_user(
                str(script.uid), str(user.uid), {"Task": {"CultivateAllOwned": True}}
            )
        )
        await asyncio.wait_for(prepared.wait(), 1)
        await user.update(
            MaaUserConfig.model_validate({"Task": {"CultivateSklandUid": "new-role"}})
        )
    with pytest.raises(ValueError):
        await pending
    assert user.Task.CultivateAllOwned is False
    assert user.Task.CultivateTargets == before


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_flag", [None, False, True])
async def test_restore_preserves_explicit_management_and_disables_missing_old_field(
    monkeypatch, tmp_path, saved_flag
):
    module = importlib.import_module("app.task.MAA.tools.restore_service")
    user = await activate_config(
        MaaUserConfig.model_validate(
            {"Task": {"IfCultivate": True, "CultivateAllOwned": True}}
        )
    )
    targets = '[{"operator_id":"custom","goals":[{"kind":"elite","to_level":1}]}]'
    overlay = {
        "IfCultivate": True,
        "CultivateTargets": targets,
        "StaminaPipelineVersion": 1,
    }
    if saved_flag is not None:
        overlay["CultivateAllOwned"] = saved_flag
    monkeypatch.setattr(module, "restore_mas_backup", lambda *args, **kwargs: overlay)
    monkeypatch.setattr(module, "_mas_dir_for_owner", lambda *args: tmp_path)
    ctx = SimpleNamespace(
        script_id="script",
        user_id=str(user.uid),
        script_config=SimpleNamespace(UserData={user.uid: user}),
    )
    await module._restore_mas(ctx, "snapshot")
    assert user.Task.CultivateAllOwned is (saved_flag is True)
    assert user.Task.IfCultivate is True
    assert user.Task.CultivateTargets == targets

    # 恢复后实际准备下一轮；旧侧车不会再扩充名单，新侧车的显式开启仍有效。
    proxy_module = importlib.import_module("app.task.MAA.AutoProxy")
    monkeypatch.setattr(
        proxy_module, "Config", SimpleNamespace(config_path=tmp_path, proxy=None)
    )
    monkeypatch.setattr(
        proxy_module.maa_api,
        "get_cultivate_skland_progression",
        AsyncMock(return_value=({"custom": progression(), "new": progression()}, 1)),
    )
    load_catalog = AsyncMock(return_value=catalog("custom", "new"))
    monkeypatch.setattr(
        proxy_module.depot_cultivate_service, "operator_catalog", load_catalog
    )

    async def prepare(**kwargs):
        return kwargs["targets"], None, True, ()

    monkeypatch.setattr(
        proxy_module.depot_cultivate_service, "prepare_cultivate", prepare
    )
    proxy = SimpleNamespace(
        cur_user_config=user,
        cur_user_item=SimpleNamespace(name="user"),
        cur_user_uid=user.uid,
        script_info=SimpleNamespace(script_id="script"),
        _cultivate_archive_dir=lambda: tmp_path,
        _set_cultivate_notice=AsyncMock(),
    )
    await AutoProxyTask._prepare_cultivate_injection(proxy, [])
    ids = [item["operator_id"] for item in json.loads(user.Task.CultivateTargets)]
    assert ids == (["custom", "new"] if saved_flag is True else ["custom"])
    assert load_catalog.await_count == (1 if saved_flag is True else 0)
