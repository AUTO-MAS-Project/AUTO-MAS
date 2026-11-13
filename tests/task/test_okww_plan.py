"""日常计划按日下发，保留账号固定配置及原生额外参数。"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.config import OkwwPlanConfig, OkwwUserConfig
from app.task.Okww.tools.plan import task_config


def test_fixed_mode_respects_quick_config():
    user = OkwwUserConfig()
    assert task_config(user)["Which to Farm"] == user.Task.WhichToFarm
    user.Info.IfQuickConfig = False
    assert task_config(user) == {}


@pytest.mark.parametrize(
    "mode,group", [("ALL", "ALL"), ("Weekly", "Monday"), ("Rotate", "Day31")]
)
def test_plan_overrides_without_mutating_account(monkeypatch, mode, group):
    from app.task.Okww.tools import plan as module

    plan = OkwwPlanConfig()
    plan.Info.Mode = mode
    plan.Info.RotateDays = 31
    monkeypatch.setattr(type(plan), "current_group", lambda self, now: group)
    getattr(plan, group).Key.WhichToFarm = "Forgery Challenge"
    user = OkwwUserConfig()
    uid = uuid4()
    user.Info.PlanMode = uid
    user.Info.IfQuickConfig = False
    monkeypatch.setattr(module, "Config", SimpleNamespace(PlanConfig={str(uid): plan}))
    before = user.Task.model_dump()
    assert task_config(user)["Which to Farm"] == "Forgery Challenge"
    assert user.Task.model_dump() == before


def test_single_runtime_preserves_unrelated_native_settings(monkeypatch, tmp_path):
    from app.task.Okww.AutoProxy import AutoProxyTask
    from app.task.Okww.tools import plan as module

    plan = OkwwPlanConfig()
    plan.Info.Mode = "ALL"
    plan.ALL.Key.WhichToFarm = "Simulation Challenge"
    user = OkwwUserConfig()
    uid = uuid4()
    user.Info.PlanMode = uid
    user.Info.IfQuickConfig = False
    monkeypatch.setattr(module, "Config", SimpleNamespace(PlanConfig={str(uid): plan}))
    target = tmp_path / "DailyTask.json"
    target.write_text(json.dumps({"extra": "preserved"}))
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_config = user
    proxy.script_config_path = tmp_path
    proxy._apply_mas_overrides()
    values = json.loads(target.read_text(encoding="utf-8"))
    assert values["Which to Farm"] == "Simulation Challenge"
    assert values["extra"] == "preserved"


@pytest.mark.asyncio
async def test_plan_api_saves_only_selected_day(isolated_app_paths, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from app.api.plan import router
    from app.config import ConfigCollection

    plans = ConfigCollection.build([OkwwPlanConfig])
    await plans.activate()
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = (
            await client.post("/api/plan/add", json={"type": "OkwwPlan"})
        ).json()
        assert response["code"] == 200
        uid = response["planId"]
        saved = (
            await client.post(
                "/api/plan/update",
                json={
                    "planId": uid,
                    "data": {
                        "Monday": {"Key": {"WhichToFarm": "Simulation Challenge"}}
                    },
                },
            )
        ).json()
        assert saved["code"] == 200
        assert plans[uid].Monday.Key.WhichToFarm == "Simulation Challenge"
        assert plans[uid].Tuesday.Key.WhichToFarm == "Tacet Suppression"
        invalid = await client.post(
            "/api/plan/update",
            json={
                "planId": uid,
                "data": {"Monday": {"Key": {"WhichForgeryChallengeToFarm": 100}}},
            },
        )
        assert invalid.status_code == 422


def test_plan_inherits_account_values_and_can_override_false_and_empty(monkeypatch):
    from app.task.Okww.tools import plan as module

    plan = OkwwPlanConfig()
    plan.Info.Mode = "ALL"
    plan.ALL.Key.FarmNightmareNestForDailyEcho = False
    plan.ALL.Key.AdditionalTasks = []
    user = OkwwUserConfig()
    uid = uuid4()
    user.Info.PlanMode = uid
    user.Task.WhichToFarm = "Simulation Challenge"
    user.Task.MaterialSelection = "Weapon EXP"
    plan.ALL.Key.WhichToFarm = None
    plan.ALL.Key.MaterialSelection = None
    monkeypatch.setattr(module, "Config", SimpleNamespace(PlanConfig={str(uid): plan}))
    values = task_config(user)
    assert values["Which to Farm"] == "Simulation Challenge"
    assert values["Material Selection"] == "Weapon EXP"
    assert values["Farm Nightmare Nest for Daily Echo"] is False
    assert values["Additional Tasks to Run After Daily Task"] == []
    user.Info.IfQuickConfig = False
    values = task_config(user)
    assert "Which to Farm" not in values
    assert "Material Selection" not in values
    assert values["Farm Nightmare Nest for Daily Echo"] is False


def test_numeric_inheritance_is_not_coerced_to_default():
    plan = OkwwPlanConfig.model_validate(
        {
            "Monday": {
                "Key": {
                    "WhichTacetSuppressionToFarm": None,
                    "WhichForgeryChallengeToFarm": None,
                }
            }
        }
    )
    assert plan.Monday.Key.WhichTacetSuppressionToFarm is None
    assert plan.Monday.Key.WhichForgeryChallengeToFarm is None


def test_custom_start_arguments_are_not_daily_plan_fields():
    from app.models.config.plan import OkwwPlanKey

    user = OkwwUserConfig()
    user.Task.IfCustomArguments = True
    user.Task.CustomArguments = "-t FarmEchoTask"
    values = task_config(user)
    assert values["Which to Farm"] == user.Task.WhichToFarm
    assert "IfCustomArguments" not in OkwwPlanKey.model_fields
    assert "CustomArguments" not in OkwwPlanKey.model_fields
    assert "IfCustomArguments" not in values
    assert "CustomArguments" not in values
