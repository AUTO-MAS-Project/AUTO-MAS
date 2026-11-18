"""周本计划在凌晨五点切日，继承的原生配置保持不变。"""

import json
from datetime import datetime

import pytest

from app.models.config.plan import OkNtePlanConfig
from app.models.schema import OkNtePlanKey
from app.task.OkNte.tools.plan import apply_plan
from app.utils.common.constants import UTC8


@pytest.mark.parametrize(
    ("hour", "minute", "second", "inherit", "expected_target", "expected_start_day"),
    [
        (4, 0, 0, False, "Good Boy Stamp", "周一"),
        (4, 59, 59, False, "Good Boy Stamp", "周一"),
        (5, 0, 0, False, "Hollowflower Seeds", "周一"),
        (4, 59, 59, True, "Good Boy Stamp", "周五"),
    ],
)
def test_weekly_plan_five_am_boundary(
    tmp_path,
    monkeypatch,
    hour,
    minute,
    second,
    inherit,
    expected_target,
    expected_start_day,
):
    instant = datetime(2026, 11, 23, hour, minute, second, tzinfo=UTC8)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(instant.timestamp(), tz=tz or UTC8)

        def astimezone(self, tz=None):
            return super().astimezone(tz or UTC8)

    monkeypatch.setattr("app.models.config.plan.datetime", FrozenDateTime)
    monkeypatch.setattr("app.task.OkNte.tools.plan.datetime", FrozenDateTime)
    sunday = {"目标": ["Good Boy Stamp"], "轮换起始日期": ""}
    if not inherit:
        sunday["每周开始运行日"] = "周日"
    plan = OkNtePlanConfig(
        Info={"Mode": "Weekly"},
        Sunday={
            "Key": {
                "Configs": {
                    "DailyRoutineTaskConfigs.json": {
                        "anomaly_pilgrimage": sunday,
                    }
                }
            }
        },
        Monday={
            "Key": {
                "Configs": {
                    "DailyRoutineTaskConfigs.json": {
                        "anomaly_pilgrimage": {
                            "目标": ["Hollowflower Seeds"],
                            "每周开始运行日": "周一",
                            "轮换起始日期": "",
                        },
                    }
                }
            }
        },
    )
    target = tmp_path / "DailyRoutineTaskConfigs.json"
    target.write_text(
        json.dumps(
            {
                "anomaly_pilgrimage": {
                    "每周开始运行日": "周五",
                    "轮换起始日期": "2099-01-01",
                }
            }
        ),
        encoding="utf-8",
    )
    key = OkNtePlanKey.model_validate(plan.get_current_key())
    original = key.model_dump()

    apply_plan(tmp_path, key)

    weekly = json.loads(target.read_text(encoding="utf-8"))["anomaly_pilgrimage"]
    assert weekly["目标"] == [expected_target]
    assert weekly["每周开始运行日"] == expected_start_day
    assert weekly["轮换起始日期"] == ""
    assert key.model_dump() == original
