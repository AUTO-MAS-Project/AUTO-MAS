import json

from app.task.MAA.AutoProxy import (
    _build_activity_priority_fight,
    _build_depot_maintain_task,
    _merge_fight_task,
)
from app.utils.constants import MAA_ANNIHILATION_FIGHT_BASE, MAA_REMAIN_FIGHT_BASE


def test_fight_merge_managed_fields_override_native_options() -> None:
    source_task = {
        "UseStone": True,
        "StoneCount": 3,
        "UseExpiringMedicine": True,
        "UseExpireMedicineForActivity": True,
        "Series": 6,
        "EnableTargetDrop": True,
        "DropId": "2004",
        "Nested": {"value": 1},
    }

    annihilation = _merge_fight_task(source_task, MAA_ANNIHILATION_FIGHT_BASE)
    remain = _merge_fight_task(source_task, MAA_REMAIN_FIGHT_BASE)

    assert annihilation["UseStone"] is False
    assert annihilation["StoneCount"] == 0
    assert annihilation["UseExpiringMedicine"] is True
    assert annihilation["UseExpireMedicineForActivity"] is False
    assert annihilation["Series"] == 0
    assert annihilation["EnableTargetDrop"] is False
    assert annihilation["DropId"] == ""
    assert remain["UseStone"] is False
    assert remain["StoneCount"] == 0
    assert remain["UseExpiringMedicine"] is False
    assert remain["UseExpireMedicineForActivity"] is False
    assert remain["Series"] == 0
    assert remain["EnableTargetDrop"] is False
    assert remain["DropId"] == ""
    assert remain["Nested"] == {"value": 1}
    assert source_task["Nested"] == {"value": 1}


def test_depot_maintain_preserves_native_options() -> None:
    source_task = {
        "$type": "DepotMaintainTask",
        "UpdateDepot": False,
        "IsStageManually": True,
        "SkipDuringActivity": True,
        "SkipDuringResourceCollection": True,
        "UseAutoSeries": False,
        "PlanList": [
            {
                "Stage": "CE-6",
                "DropId": "4001",
                "DropCount": 20,
                "UseMedicine": True,
                "MedicineCount": 3,
                "UseStone": True,
                "StoneCount": 1,
            }
        ],
    }

    result = _build_depot_maintain_task(
        json.dumps([{"Stage": "CE-6", "DropId": "4001", "DropCount": 30}]),
        source_task=source_task,
    )

    assert result["UpdateDepot"] is False
    assert result["IsStageManually"] is True
    assert result["SkipDuringActivity"] is True
    assert result["SkipDuringResourceCollection"] is True
    assert result["UseAutoSeries"] is False
    assert result["PlanList"] == [
        {
            **source_task["PlanList"][0],
            "DropCount": 30,
            "UseMedicine": False,
            "MedicineCount": 0,
            "UseStone": False,
            "StoneCount": 0,
        }
    ]


def test_depot_maintain_handles_null_plan_list_and_unmatched_plan() -> None:
    result = _build_depot_maintain_task(
        json.dumps([{"Stage": "LS-5", "DropId": "2001", "DropCount": 10}]),
        source_task={"PlanList": None},
    )

    assert result["PlanList"] == [
        {
            "Stage": "LS-5",
            "DropId": "2001",
            "DropCount": 10,
            "UseMedicine": False,
            "MedicineCount": 0,
            "UseStone": False,
            "StoneCount": 0,
        }
    ]


def test_activity_fight_preserves_native_options() -> None:
    source_task = {
        "EnableTargetDrop": True,
        "DropId": "4001",
        "DropCount": 20,
        "IsInventoryTarget": True,
        "EnableTimesLimit": True,
        "TimesLimit": 5,
        "IsDrGrandet": True,
        "UseExpiringMedicine": True,
        "UseExpireMedicineForActivity": True,
        "UseStoneAllowSave": True,
        "Nested": {"value": 1},
    }

    result = _build_activity_priority_fight(source_task, "ACT-1", 2)

    assert result["StagePlan"] == ["ACT-1"]
    assert result["IsStageManually"] is True
    assert result["UseOptionalStage"] is False
    assert result["UseWeeklySchedule"] is False
    assert result["UseMedicine"] is True
    assert result["MedicineCount"] == 2
    assert result["EnableTargetDrop"] is False
    assert result["DropId"] == ""
    assert result["DropCount"] == 0
    assert result["IsInventoryTarget"] is False
    assert result["EnableTimesLimit"] is False
    assert result["IsDrGrandet"] is True
    assert result["UseExpiringMedicine"] is True
    assert result["UseExpireMedicineForActivity"] is True
    assert result["UseStoneAllowSave"] is True
    assert result["Nested"] == {"value": 1}
    assert source_task["Nested"] == {"value": 1}
