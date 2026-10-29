import pytest

from app.task.MAA.AutoProxy import (
    _apply_depot_medicine_override,
    _build_cultivate_task,
    _build_depot_maintain_task,
    _build_stock_cultivate_task,
    _should_retry_maa,
)
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


@pytest.mark.parametrize(
    ("medicine_count", "expected_use"),
    [(None, None), (0, False), (3, True)],
)
def test_depot_medicine_override_applies_to_every_merged_plan(
    medicine_count: int | None, expected_use: bool | None
):
    source = _source_task(use_expiring=True)
    stock_task = _build_depot_maintain_task(
        '[{"Stage":"1-7","DropId":"1","DropCount":1}]',
        source,
    )
    cultivate_task = _build_cultivate_task(
        _cultivate_plan(),
        source,
        skip_during_activity=False,
        skip_during_resource_collection=False,
    )
    task = _build_stock_cultivate_task(stock_task, cultivate_task, _cultivate_plan())
    assert task is not None
    original_plans = [plan.copy() for plan in task["PlanList"]]

    _apply_depot_medicine_override(task, medicine_count)

    if medicine_count is None:
        assert task["UseMedicine"] is True
        assert task["PlanList"] == original_plans
        return
    assert task["UseMedicine"] is expected_use
    assert task["MedicineCount"] == medicine_count
    assert all(plan["UseMedicine"] is expected_use for plan in task["PlanList"])
    assert all(plan["MedicineCount"] == medicine_count for plan in task["PlanList"])
    assert source["UseMedicine"] is True


@pytest.mark.parametrize(
    "failure_summary",
    [
        "任务已完成，但出现错误！",
        "任务已结束，以下任务出现错误:\n理智作战",
    ],
)
def test_maa_final_task_failure_is_not_retried(failure_summary: str):
    log = f"干员培养完成：成功 0，失败 6，跳过 0\n{failure_summary}"

    assert not _should_retry_maa("MAA 部分任务执行失败", log)


@pytest.mark.parametrize(
    "status",
    ["MAA 的 ADB 连接异常", "MAA 进程超时", "MAA 在完成任务前退出"],
)
def test_maa_runtime_failures_remain_retryable(status: str):
    assert _should_retry_maa(status, "连接异常")


def test_maa_partial_result_without_final_failure_marker_remains_retryable():
    assert _should_retry_maa("MAA 部分任务执行失败", "任务出错: 理智作战")
