"""全部已有干员托管：保留手工目标、首次注入与后续增量检查。"""

import importlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config import MaaConfig, MaaUserConfig
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.tools.cultivate import (
    Progression,
    append_owned_cultivate_targets,
)
from app.task.MAA.user_update import prepare_user_update


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
async def test_enabling_injects_now_and_disabling_changes_only_the_flag(
    monkeypatch, isolated_app_paths
):
    api = importlib.import_module("app.task.MAA.api_service")
    user = MaaUserConfig.model_validate({"Task": {"CultivateTargets": "[]"}})
    script = MaaConfig()
    snapshot = AsyncMock(return_value=({"owned": progression()}, 1))
    monkeypatch.setattr(api, "get_cultivate_skland_progression", snapshot)
    module = importlib.import_module("app.task.MAA.user_update")
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(return_value=catalog("owned", "unowned")),
    )
    patch = {"Task": {"CultivateAllOwned": True}}
    await prepare_user_update(script, user, data=patch)
    assert patch["Task"]["CultivateAllOwned"] is True
    assert [
        item["operator_id"] for item in json.loads(patch["Task"]["CultivateTargets"])
    ] == ["owned"]
    assert "CultivateAutoRaise" not in patch["Task"]
    snapshot.assert_awaited_once_with(str(script.uid), str(user.uid), force=True)
    off = {"Task": {"CultivateAllOwned": False}}
    await prepare_user_update(script, user, data=off)
    assert off == {"Task": {"CultivateAllOwned": False}}
    assert snapshot.await_count == 1


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
