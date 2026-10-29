"""专项声明迁移后，配置的游戏日、旧计划与原字段透传保持兼容。"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain import maa
from app.domain.mss import MSS_TRIBULATION_STAGES
from app.models.config import MaaEndUserConfig, MaaPlanConfig, MaaUserConfig
from app.models.config.shared import normalize_maaend_plan_key, normalize_mss_plan_key
from app.models.schema import MSSPlanKey


@pytest.mark.parametrize(
    ("server", "offset", "day"),
    [
        ("Official", 4, 29),
        ("Bilibili", 4, 29),
        ("txwy", 4, 29),
        ("YoStarEN", -11, 28),
        ("YoStarJP", 5, 29),
        ("YoStarKR", 5, 29),
    ],
)
def test_maa_game_day_reads_preserve_utc_export(server, offset, day):
    config = MaaUserConfig.model_validate(
        {
            "Info": {"Server": server},
            "Data": {"LastProxyDate": "2026-10-29T10:59:00Z"},
        }
    )
    assert config.Data.LastProxyDate.day == day
    assert config.Data.LastProxyDate.utcoffset().total_seconds() == offset * 3600
    assert (
        config.model_dump(context={"audience": "export"})["Data"]["LastProxyDate"]
        == "2026-10-29T10:59:00Z"
    )


def test_maa_weekly_plan_uses_server_game_day(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, 10, 59, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(maa, "datetime", Clock)
    plan = MaaPlanConfig.model_validate(
        {
            "Info": {"Mode": "Weekly"},
            "Wednesday": {"Stage": "1-7"},
            "Thursday": {"Stage": "CE-6"},
        }
    )
    assert plan.get_current_info("Stage", server="YoStarEN") == "1-7"
    assert plan.get_current_info("Stage", server="Official") == "CE-6"
    assert plan.get_current_info("Stage", server=None) == "CE-6"
    assert maa.get_game_day_tz("unknown") == maa.get_game_day_tz(None)


def test_maaend_inventory_values_remain_raw_strings():
    config = MaaEndUserConfig()
    limits = json.loads(config.Task.SupplyPlanLimits)
    assert next(iter(limits)) == "SupplyPlanLimit_T_CREDS"
    assert limits["SupplyPlanLimit_T_CREDS"] == "3580000"
    assert limits["SupplyPlanLimit_COGNITIVE_CARRIER_EXP"] == "2100000"
    assert all(isinstance(value, str) for value in limits.values())

    # 未知的上游字段也原样透传，不按固定默认值表重建用户数据。
    raw = '{"future_upstream_field": "0007", "SupplyPlanLimit_T_CREDS": "42"}'
    restored = MaaEndUserConfig.model_validate({"Task": {"SupplyPlanLimits": raw}})
    assert (
        restored.model_dump(context={"audience": "export"})["Task"]["SupplyPlanLimits"]
        == raw
    )


def test_maaend_legacy_plan_keeps_defaults_and_essence_shape():
    key = normalize_maaend_plan_key(
        {
            "Key": {
                "SanityTaskType": "ProtocolSpace",
                "ProtocolSpaceTab": "WeaponProgression",
            }
        }
    )
    assert key == {
        "SanityTaskType": "WeaponProgression",
        "OperatorProgression": "OperatorEXP",
        "WeaponProgression": "WeaponEXP",
        "CrisisDrills": "AdvancedProgression1",
        "RewardsSetOption": "RewardsSetA",
    }
    assert normalize_maaend_plan_key({"SanityTaskType": "Matrix"}) == {
        "SanityTaskType": "Essence",
        "AutoEssenceSpecifiedLocation": "",
    }


@pytest.mark.parametrize("stage", MSS_TRIBULATION_STAGES)
def test_mss_plan_stage_survives_normalization_and_serialization(stage):
    key = normalize_mss_plan_key({"Key": {"TribulationStage": stage}})
    assert MSSPlanKey.model_validate_json(json.dumps(key)).TribulationStage == stage


def test_mss_invalid_stage_keeps_legacy_fallback_and_strict_api_validation():
    assert (
        normalize_mss_plan_key({"TribulationStage": "unknown"})["TribulationStage"]
        == "基础试炼"
    )
    with pytest.raises(ValidationError):
        MSSPlanKey(TribulationStage="unknown")
