import json

from app.task.MAA.AutoProxy import (
    _build_activity_priority_fight,
    _build_depot_maintain_task,
)


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
    assert result["EnableTargetDrop"] is True
    assert result["DropId"] == "4001"
    assert result["IsInventoryTarget"] is True
    assert result["EnableTimesLimit"] is True
    assert result["IsDrGrandet"] is True
    assert result["UseExpiringMedicine"] is True
    assert result["UseExpireMedicineForActivity"] is True
    assert result["UseStoneAllowSave"] is True
    assert result["Nested"] == {"value": 1}
    assert source_task["Nested"] == {"value": 1}
