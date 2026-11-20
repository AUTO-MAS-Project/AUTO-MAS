"""OK-WW 计划按游戏日选择设置，详表保存不会复制账号默认值。"""

from datetime import datetime

import pytest

from app.config import ConfigCollection
from app.core import Config
from app.models.config import OkwwPlanConfig, OkwwUserConfig
from app.models.config import plan as plan_model
from app.task.Okww.api_service import describe_plan_configs, save_plan_configs
from app.task.Okww.tools.config_fields import runtime_panels
from app.utils.common.constants import UTC8


@pytest.mark.asyncio
async def test_detailed_plan_overrides_switch_at_0400(monkeypatch):
    plans = ConfigCollection.build([OkwwPlanConfig])
    await plans.activate()
    pid = plans.add(
        OkwwPlanConfig,
        payload={
            "Monday": {
                "Key": {
                    "WhichToFarm": "Tacet Suppression",
                    "WhichTacetSuppressionToFarm": 3,
                }
            }
        },
    )
    await plans.commit()
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setattr(Config, "ScriptConfig", {})

    await save_plan_configs(
        str(pid),
        "Tuesday",
        {
            "DailyTask.json": {
                "Which to Farm": "Tacet Suppression",
                "Which Tacet Suppression to Farm": 5,
            },
            "FarmEchoTask.json": {"Repeat Farm Count": 12},
        },
    )
    assert plans[pid].Tuesday.Key.WhichTacetSuppressionToFarm == 5
    assert plans[pid].Monday.Key.WhichTacetSuppressionToFarm == 3
    assert describe_plan_configs(str(pid), "Tuesday", "zh_CN")[1]["overrides"] == {
        "Repeat Farm Count": 12
    }

    user = OkwwUserConfig.model_validate(
        {
            "Info": {"PlanMode": pid},
            "Task": {"FarmEchoConfig": {"Repeat Farm Count": 7, "Boss": "Lorelei"}},
        }
    )

    class Clock(datetime):
        hour = 3
        minute = 59

        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 17, cls.hour, cls.minute, tzinfo=UTC8).astimezone(
                tz
            )

    monkeypatch.setattr(plan_model, "datetime", Clock)
    before = runtime_panels(user)
    assert before["DailyTask.json"]["Which Tacet Suppression to Farm"] == 3
    assert before["FarmEchoTask.json"]["Repeat Farm Count"] == 7
    Clock.hour, Clock.minute = 4, 0
    after = runtime_panels(user)
    assert after["DailyTask.json"]["Which Tacet Suppression to Farm"] == 5
    assert after["FarmEchoTask.json"] == {"Repeat Farm Count": 12, "Boss": "Lorelei"}

    await save_plan_configs(str(pid), "Tuesday", {})
    assert runtime_panels(user)["FarmEchoTask.json"]["Repeat Farm Count"] == 7


def test_legacy_partial_boss_override_does_not_mix_with_account_teleport():
    user = OkwwUserConfig.model_validate(
        {
            "Task": {
                "FarmEchoConfig": {
                    "Teleport to Boss": "Boss Challenge",
                    "Which Boss Challenge to Teleport": 2,
                }
            }
        }
    )
    with pytest.raises(ValueError, match="4C 首领目标"):
        runtime_panels(user, planned={"FarmEchoTask.json": {"Boss": "Lorelei"}})
