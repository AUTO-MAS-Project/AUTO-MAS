from copy import deepcopy

import pytest

from app.models.config import MaaUserConfig
from app.task.MAA.AutoProxy import (
    _apply_depot_medicine_override,
    _build_cultivate_task,
    _build_depot_maintain_task,
    _build_stock_cultivate_task,
    _should_retry_maa,
)
from app.task.MAA.tools.backup_archive import group_overlay, read_overlay_values
from app.task.MAA.tools.cultivate.types import CultivatePlan, FarmEntry, Requirement


def _cultivate_plan() -> CultivatePlan:
    return CultivatePlan(
        entries=(FarmEntry(item_id="1", amount=1, stage_code="1-7"),),
        reservations=(Requirement(item_id="1", amount=1),),
    )


def _source_task(
    *, use_expiring: bool, plan_medicine: tuple[bool, int] | None = None
) -> dict:
    plan = {
        "Stage": "1-7",
        "DropId": "1",
        "DropCount": 1,
    }
    if plan_medicine is not None:
        plan.update(
            UseMedicine=plan_medicine[0],
            MedicineCount=plan_medicine[1],
            UseStone=True,
            StoneCount=plan_medicine[1],
        )
    return {
        "$type": "DepotMaintainTask",
        "UseExpiringMedicine": use_expiring,
        # 刻意用非 MAA 默认值，硬编码默认值时下面的透传断言才会失败。
        "MedicineExpireDays": 3,
        "UseExpireMedicineForActivity": True,
        "UseMedicine": True,
        "UseStone": True,
        "PlanList": [plan],
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
    assert cultivate["MedicineExpireDays"] == 3
    assert cultivate["UseExpireMedicineForActivity"] is True

    task = _build_stock_cultivate_task(source, cultivate, _cultivate_plan())

    assert task is not None
    assert task["UseExpiringMedicine"] is use_expiring
    assert task["MedicineExpireDays"] == 3
    assert task["UseExpireMedicineForActivity"] is True
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


def _stock_task(source: dict) -> dict:
    return _build_depot_maintain_task(
        '[{"Stage":"1-7","DropId":"1","DropCount":1}]',
        source,
    )


def _cultivate(source: dict) -> dict:
    task = _build_cultivate_task(
        _cultivate_plan(),
        source,
        skip_during_activity=False,
        skip_during_resource_collection=False,
    )
    assert task is not None
    return task


def test_cultivate_task_inherits_maa_medicine_settings():
    source = _source_task(use_expiring=True, plan_medicine=(True, 6))

    cultivate = _cultivate(source)

    assert cultivate["UseMedicine"] is True
    assert cultivate["UseStone"] is True
    assert cultivate["PlanList"][0]["UseMedicine"] is True
    assert cultivate["PlanList"][0]["MedicineCount"] == 6


@pytest.mark.parametrize(
    ("use_medicine", "use_stone"),
    [(False, True), (True, False), (False, False)],
)
def test_cultivate_task_inherits_closed_maa_gates(use_medicine: bool, use_stone: bool):
    source = _source_task(use_expiring=True, plan_medicine=(True, 6))
    source["UseMedicine"] = use_medicine
    source["UseStone"] = use_stone

    cultivate = _cultivate(source)

    assert cultivate["UseMedicine"] is use_medicine
    assert cultivate["UseStone"] is use_stone


def test_cultivate_task_does_not_invent_medicine_defaults():
    source = _source_task(use_expiring=True)

    cultivate = _cultivate(source)

    assert "UseMedicine" not in cultivate["PlanList"][0]
    assert "MedicineCount" not in cultivate["PlanList"][0]


def test_blank_medicine_setting_changes_nothing():
    source = _source_task(use_expiring=True, plan_medicine=(True, 5))
    stock_task = _stock_task(source)
    before = deepcopy(stock_task)

    _apply_depot_medicine_override(stock_task, None)

    assert stock_task == before


@pytest.mark.parametrize(
    ("medicine_count", "expected_use"),
    [(0, False), (3, True)],
)
def test_medicine_override_writes_plan_values(medicine_count: int, expected_use: bool):
    source = _source_task(use_expiring=True, plan_medicine=(True, 5))
    stock_task = _stock_task(source)

    _apply_depot_medicine_override(stock_task, medicine_count)

    # MAA 的 DepotMaintainTask 没有任务级 MedicineCount，数量只落在计划上。
    assert "MedicineCount" not in stock_task
    assert stock_task["UseMedicine"] is True
    assert stock_task["PlanList"][0]["UseMedicine"] is expected_use
    assert stock_task["PlanList"][0]["MedicineCount"] == medicine_count
    assert source["PlanList"][0]["MedicineCount"] == 5


def _expected_medicine(
    medicine_count: int | None, source_plan: dict
) -> tuple[bool, int]:
    """留空沿用来源计划自身的设置，填数字则整组改写成该数字。"""

    if medicine_count is None:
        return (source_plan["UseMedicine"], source_plan["MedicineCount"])
    return (medicine_count > 0, medicine_count)


@pytest.mark.parametrize("stock_count", [None, 0, 2])
@pytest.mark.parametrize("cultivate_count", [None, 0, 3])
def test_stock_and_cultivate_medicine_settings_stay_independent(
    stock_count: int | None, cultivate_count: int | None
):
    stock_source = _source_task(use_expiring=True, plan_medicine=(True, 5))
    cultivate_source = _source_task(use_expiring=True, plan_medicine=(True, 6))
    stock_task = _stock_task(stock_source)
    cultivate_task = _cultivate(cultivate_source)

    _apply_depot_medicine_override(stock_task, stock_count)
    _apply_depot_medicine_override(cultivate_task, cultivate_count)
    merged = _build_stock_cultivate_task(stock_task, cultivate_task, _cultivate_plan())

    assert merged is not None
    stock_expected = _expected_medicine(stock_count, stock_source["PlanList"][0])
    cultivate_expected = _expected_medicine(
        cultivate_count, cultivate_source["PlanList"][0]
    )
    cultivate_plan, stock_plan = merged["PlanList"]
    assert (
        cultivate_plan["UseMedicine"],
        cultivate_plan["MedicineCount"],
    ) == cultivate_expected
    assert (stock_plan["UseMedicine"], stock_plan["MedicineCount"]) == stock_expected
    # 总开关只由来源任务与合并并集决定；两组都填 0 时额度已写进计划，无需关总开关。
    assert merged["UseMedicine"] is True


def test_merge_without_cultivate_group_keeps_stock_gate():
    stock_source = _source_task(use_expiring=True, plan_medicine=(True, 5))
    stock_source["UseMedicine"] = False

    merged = _build_stock_cultivate_task(
        _stock_task(stock_source), None, _cultivate_plan()
    )

    assert merged is not None
    assert merged["UseMedicine"] is False
    assert merged["PlanList"][0]["UseMedicine"] is False
    assert merged["PlanList"][0]["MedicineCount"] == 0


@pytest.mark.parametrize(
    ("gate", "count_key", "residual"),
    [("UseMedicine", "MedicineCount", 5), ("UseStone", "StoneCount", 9)],
)
def test_merge_keeps_closed_group_quota_closed(
    gate: str, count_key: str, residual: int
):
    """MAA 关掉库存组药石总开关后，计划里残留的旧额度不能借合并后的总开关复活。"""

    stock_source = _source_task(use_expiring=True, plan_medicine=(True, residual))
    stock_source[gate] = False
    cultivate_source = _source_task(use_expiring=True, plan_medicine=(True, 3))

    merged = _build_stock_cultivate_task(
        _stock_task(stock_source), _cultivate(cultivate_source), _cultivate_plan()
    )

    assert merged is not None
    # 另一组仍开着，合并后的总开关取并集；关闭的那组由摊平写回计划。
    assert merged[gate] is True
    cultivate_plan, stock_plan = merged["PlanList"]
    assert (cultivate_plan[gate], cultivate_plan[count_key]) == (True, 3)
    assert (stock_plan[gate], stock_plan[count_key]) == (False, 0)


def test_medicine_settings_round_trip_through_maa_overlay():
    user = MaaUserConfig.model_validate(
        {
            "Task": {
                "DepotMaintainMedicineNumb": 2,
                "CultivateMedicineNumb": 3,
                "EventDepotMaintainMedicineNumb": 4,
            }
        }
    )

    overlay = read_overlay_values(user)
    keys = (
        "DepotMaintainMedicineNumb",
        "CultivateMedicineNumb",
        "EventDepotMaintainMedicineNumb",
    )
    expected = {key: index for index, key in enumerate(keys, start=2)}

    assert {key: overlay[key] for key in keys} == expected
    grouped = group_overlay(overlay)
    assert {key: grouped["Task"][key] for key in keys} == expected


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
