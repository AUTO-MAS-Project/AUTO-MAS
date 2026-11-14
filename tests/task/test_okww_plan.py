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
