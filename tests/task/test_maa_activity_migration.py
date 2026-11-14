"""活动旧项在真实用户保存入口逐项迁移并持久化，不改前端契约。"""

import asyncio
import importlib
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core.config.manager import AppConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.MAA.tools.activity_inventory import resolve_activity_inventory_plans
from app.task.MAA.user_update import prepare_user_update

STAGES = [
    {"Value": "TL-9", "Drop": "31113"},
    {"Value": "TL-8", "Drop": "31083"},
    {"Value": "TL-7", "Drop": "31043"},
    {"Value": "TL-4", "Drop": "30012", "DropName": "搓玉"},
]
LEGACY = {
    "StageType": "activity",
    "StageIndex": 1,
    "DropCount": 999,
    "OrundumDropCount": 9999,
    "LegacyActivityFirst": True,
}


@pytest_asyncio.fixture
async def migration_host(monkeypatch):
    stage = importlib.import_module("app.task.MAA.stage")
    fetch = AsyncMock(return_value={"Activity": STAGES, "ActivityStatus": "ready"})
    monkeypatch.setattr(stage.maa_stage_service, "get_stage_info", fetch)
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
    user_uid = script.UserData.add(MaaUserConfig)
    await script.UserData.commit()
    return config, script, script.UserData[user_uid], fetch


async def save_plans(host, rows):
    config, script, user, _ = host
    patch = {"Task": {"EventDepotMaintainPlans": json.dumps(rows, ensure_ascii=False)}}
    await config.update_user(str(script.uid), str(user.uid), patch)
    return json.loads(user.Task.EventDepotMaintainPlans)


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["shared", "independent"])
async def test_saving_new_cancellation_removes_corresponding_old_item(
    migration_host, base
):
    _, _, user, _ = migration_host
    await user.update(MaaUserConfig.model_validate({"Info": {"Base": base}}))
    rows = [
        deepcopy(LEGACY),
        {"StageType": "material", "StageIndex": 1, "DropCount": 123, "Skip": True},
        {"StageType": "orundum", "StageIndex": 1, "DropCount": 9999},
    ]
    saved = await save_plans(migration_host, rows)
    assert saved == rows[1:]
    assert [
        plan["Stage"]
        for plan in resolve_activity_inventory_plans(
            user.Task.EventDepotMaintainPlans, STAGES
        )[0]
    ] == ["TL-4"]
    # 未刷新的旧编辑器重发混合列表也不能把旧项恢复。
    assert await save_plans(migration_host, rows) == saved


@pytest.mark.asyncio
async def test_each_old_item_is_converted_once_without_fixed_stage_codes(
    migration_host,
):
    rows = [
        {
            **LEGACY,
            "StageIndex": 4,
            "UseMedicine": True,
            "MedicineCount": 2,
            "UseStone": True,
            "StoneCount": 1,
        }
    ]
    saved = await save_plans(migration_host, rows)
    assert saved == [
        {
            "StageType": "orundum",
            "StageIndex": 1,
            "DropCount": 9999,
            "UseMedicine": True,
            "MedicineCount": 2,
            "UseStone": True,
            "StoneCount": 1,
        }
    ]
    migration_host[3].reset_mock()
    assert await save_plans(migration_host, saved) == saved
    migration_host[3].assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_target_wins_over_legacy_default_and_fallback_collision(
    migration_host,
):
    migration_host[3].return_value = {
        "Activity": [STAGES[0], STAGES[-1]],
        "ActivityStatus": "ready",
    }
    rows = [
        LEGACY,
        {
            "StageType": "material",
            "StageIndex": 2,
            "DropCount": 250,
            "LegacyIndex": True,
        },
        {
            "StageType": "material",
            "StageIndex": 3,
            "DropCount": 123,
            "LegacyIndex": True,
        },
    ]
    saved = await save_plans(migration_host, rows)
    assert saved == [{"StageType": "material", "StageIndex": 1, "DropCount": 250}]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["empty", "stale", "unavailable"])
async def test_unreliable_activity_keeps_unresolved_items_but_replaces_exact_old_identity(
    migration_host, status
):
    migration_host[3].return_value = {"Activity": STAGES, "ActivityStatus": status}
    old = {
        "StageType": "material",
        "StageIndex": 2,
        "DropCount": 123,
        "LegacyIndex": True,
    }
    new = {"StageType": "material", "StageIndex": 2, "DropCount": 321, "Skip": True}
    assert await save_plans(migration_host, [LEGACY, old, new]) == [LEGACY, new]
    migration_host[3].return_value = {"Activity": STAGES, "ActivityStatus": "ready"}
    saved = await save_plans(migration_host, [LEGACY, new])
    assert saved == [{"StageType": "material", "StageIndex": 1, "DropCount": 999}, new]


@pytest.mark.asyncio
async def test_server_change_while_waiting_defers_only_ambiguous_mapping(
    migration_host,
):
    config, script, user, fetch = migration_host
    started, complete = asyncio.Event(), asyncio.Event()

    async def load(*args, **kwargs):
        started.set()
        await complete.wait()
        return {"Activity": STAGES, "ActivityStatus": "ready"}

    fetch.side_effect = load
    pending = asyncio.create_task(save_plans(migration_host, [LEGACY]))
    try:
        await asyncio.wait_for(started.wait(), 1)
        await config.update_user(
            str(script.uid), str(user.uid), {"Info": {"Server": "YoStarEN"}}
        )
    finally:
        complete.set()
    assert await pending == [LEGACY]


@pytest.mark.asyncio
@pytest.mark.parametrize("new_first", [False, True])
async def test_replacing_an_item_keeps_missing_quotas_and_respects_explicit_overrides(
    migration_host, new_first
):
    old = {
        **LEGACY,
        "UseMedicine": True,
        "MedicineCount": 2,
        "UseStone": True,
        "StoneCount": 1,
    }
    new = {
        "StageType": "material",
        "StageIndex": 1,
        "DropCount": 123,
        "UseStone": False,
        "StoneCount": 0,
    }
    saved = await save_plans(migration_host, [new, old] if new_first else [old, new])
    assert saved == [{**new, "UseMedicine": True, "MedicineCount": 2}]


@pytest.mark.asyncio
async def test_partial_migration_keeps_only_the_unresolvable_old_item(migration_host):
    migration_host[3].return_value = {
        "Activity": [
            STAGES[0],
            {"Value": "UNSUPPORTED", "Drop": "unknown"},
            STAGES[-1],
        ],
        "ActivityStatus": "ready",
    }
    unresolved = {**LEGACY, "StageIndex": 2}
    saved = await save_plans(migration_host, [LEGACY, unresolved])
    assert saved == [
        {"StageType": "material", "StageIndex": 1, "DropCount": 999},
        unresolved,
    ]
    assert await save_plans(migration_host, saved) == saved


@pytest.mark.asyncio
async def test_same_index_in_different_categories_does_not_delete_another_old_choice(
    migration_host,
):
    migration_host[3].return_value = {
        "Activity": [STAGES[-1], STAGES[0]],
        "ActivityStatus": "ready",
    }
    new = {"StageType": "material", "StageIndex": 1, "DropCount": 123, "Skip": True}
    assert await save_plans(migration_host, [LEGACY, new]) == [
        {"StageType": "orundum", "StageIndex": 1, "DropCount": 9999},
        new,
    ]


@pytest.mark.asyncio
async def test_migrated_items_survive_reload(migration_host, tmp_path):
    config, script, user, fetch = migration_host
    path = tmp_path / "scripts.yaml"
    config_manager.register_root(config.ScriptConfig, path)
    saved = await save_plans(migration_host, [LEGACY])
    await config_manager.flush()
    config_manager.unregister_root(config.ScriptConfig)
    loaded = ConfigCollection.build([MaaConfig], file=path)
    await loaded.activate()
    assert (
        json.loads(loaded[script.uid].UserData[user.uid].Task.EventDepotMaintainPlans)
        == saved
    )


@pytest.mark.asyncio
async def test_cancelling_before_commit_preserves_the_old_saved_value(migration_host):
    _, _, user, fetch = migration_host
    original = json.dumps([LEGACY])
    await user.update(
        MaaUserConfig.model_validate({"Task": {"EventDepotMaintainPlans": original}})
    )
    started, complete = asyncio.Event(), asyncio.Event()

    async def load(*args, **kwargs):
        started.set()
        await complete.wait()
        return {"Activity": STAGES, "ActivityStatus": "ready"}

    fetch.side_effect = load
    pending = asyncio.create_task(save_plans(migration_host, [LEGACY]))
    await asyncio.wait_for(started.wait(), 1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert user.Task.EventDepotMaintainPlans == original
