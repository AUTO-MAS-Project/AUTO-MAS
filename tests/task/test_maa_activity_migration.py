"""活动旧项在真实用户保存入口逐项迁移并持久化，不改前端契约。"""

import importlib
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.cultivate import Progression

from app.config import ConfigCollection
from app.core.config.manager import AppConfig

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
    stage = importlib.import_module("maa_adapter.stages")
    fetch = AsyncMock(return_value={"Activity": STAGES, "ActivityStatus": "ready"})
    monkeypatch.setattr(stage, "get_stage_info", fetch)
    config = AppConfig.__new__(AppConfig)
    config._script_config_handlers = {}
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
async def test_migration_keeps_the_existing_owned_cultivation_commit_guard(
    migration_host, monkeypatch
):
    api = importlib.import_module("maa_adapter.cultivate.editor")
    module = importlib.import_module("maa_adapter.config.user_update")
    monkeypatch.setattr(
        api,
        "get_cultivate_skland_progression",
        AsyncMock(
            return_value=(
                {
                    "owned": Progression(
                        elite=0, level=1, skill_level=1, masteries={}, modules={}
                    )
                },
                1,
            )
        ),
    )
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(return_value=[{"value": "owned", "maxElite": 2, "maxSkillLevel": 7}]),
    )
    config, script, user, _ = migration_host
    await config.update_user(
        str(script.uid),
        str(user.uid),
        {
            "Task": {
                "CultivateAllOwned": True,
                "EventDepotMaintainPlans": json.dumps([LEGACY]),
            }
        },
    )
    assert "owned" in {
        row["operator_id"] for row in json.loads(user.Task.CultivateTargets)
    }
    assert json.loads(user.Task.EventDepotMaintainPlans) == [
        {"StageType": "material", "StageIndex": 1, "DropCount": 999}
    ]
