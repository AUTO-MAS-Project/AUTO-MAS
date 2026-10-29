import pytest

from app.task.MAA.AutoProxy import _build_cultivate_task, _build_stock_cultivate_task
from app.task.MAA.tools.cultivate.types import CultivatePlan, FarmEntry, Requirement


def _cultivate_plan() -> CultivatePlan:
    return CultivatePlan(
        entries=(FarmEntry(item_id="1", amount=1, stage_code="1-7"),),
        reservations=(Requirement(item_id="1", amount=1),),
    )


def _source_task(*, use_expiring: bool) -> dict:
    return {
        "$type": "DepotMaintainTask",
        "UseExpiringMedicine": use_expiring,
        "MedicineExpireDays": 1,
        "UseExpireMedicineForActivity": False,
        "UseMedicine": True,
        "UseStone": True,
        "PlanList": [
            {
                "Stage": "1-7",
                "DropId": "1",
                "DropCount": 1,
            }
        ],
    }


@pytest.mark.parametrize("use_expiring", [True, False])
def test_cultivate_tasks_preserve_expiring_medicine_settings(use_expiring: bool):
    source = _source_task(use_expiring=use_expiring)

    cultivate = _build_cultivate_task(
        _cultivate_plan(),
        source,
        skip_during_activity=False,
        skip_during_resource_collection=False,
    )

    assert cultivate is not None
    assert cultivate["UseExpiringMedicine"] is use_expiring
    assert cultivate["MedicineExpireDays"] == 1
    assert cultivate["UseExpireMedicineForActivity"] is False

    task = _build_stock_cultivate_task(source, cultivate, _cultivate_plan())

    assert task is not None
    assert task["UseExpiringMedicine"] is use_expiring
    assert task["MedicineExpireDays"] == 1
    assert task["UseExpireMedicineForActivity"] is False
    assert source["UseExpiringMedicine"] is use_expiring


def test_cultivate_task_does_not_invent_expiring_medicine_setting():
    source = _source_task(use_expiring=True)
    for key in (
        "UseExpiringMedicine",
        "MedicineExpireDays",
        "UseExpireMedicineForActivity",
    ):
        source.pop(key)

    task = _build_cultivate_task(
        _cultivate_plan(),
        source,
        skip_during_activity=False,
        skip_during_resource_collection=False,
    )

    assert task is not None
    assert all(
        key not in task
        for key in (
            "UseExpiringMedicine",
            "MedicineExpireDays",
            "UseExpireMedicineForActivity",
        )
    )
