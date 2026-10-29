from copy import deepcopy

import pytest

from app.models.config import MaaUserConfig
from app.task.MAA.AutoProxy import (
    _MAA_DEPOT_QUOTA_KEYS,
    _apply_depot_quota_override,
    _build_cultivate_task,
    _build_depot_maintain_task,
    _build_stock_cultivate_task,
    _should_retry_maa,
)
from app.task.MAA.tools.backup_archive import group_overlay, read_overlay_values
from app.task.MAA.tools.cultivate.types import CultivatePlan, FarmEntry, Requirement

_QUOTA_IDS = [f"{gate}/{count_key}" for gate, count_key in _MAA_DEPOT_QUOTA_KEYS]


def _cultivate_plan() -> CultivatePlan:
    return CultivatePlan(
        entries=(FarmEntry(item_id="1", amount=1, stage_code="1-7"),),
        reservations=(Requirement(item_id="1", amount=1),),
    )


def _source_task(
    *,
    use_expiring: bool,
    plan_medicine: tuple[bool, int] | None = None,
    plan_stone: tuple[bool, int] | None = None,
) -> dict:
    plan = {
        "Stage": "1-7",
        "DropId": "1",
        "DropCount": 1,
    }
    for (gate, count_key), value in zip(
        _MAA_DEPOT_QUOTA_KEYS, (plan_medicine, plan_stone), strict=True
    ):
        if value is not None:
            plan.update({gate: value[0], count_key: value[1]})
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


def _expected_quota(
    count: int | None, source_plan: dict, gate: str, count_key: str
) -> tuple[bool, int]:
    """留空沿用来源计划自身的设置，填数字则整组改写成该数字。"""

    if count is None:
        return (source_plan[gate], source_plan[count_key])
    return (count > 0, count)


@pytest.mark.parametrize("use_expiring", [True, False])
def test_cultivate_tasks_preserve_expiring_medicine_settings(use_expiring: bool):
    source = _source_task(use_expiring=use_expiring)

    cultivate = _cultivate(source)

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

    task = _cultivate(source)

    assert all(
        key not in task
        for key in (
            "UseExpiringMedicine",
            "MedicineExpireDays",
            "UseExpireMedicineForActivity",
        )
    )


def test_cultivate_task_inherits_maa_quota_settings():
    source = _source_task(
        use_expiring=True, plan_medicine=(True, 6), plan_stone=(True, 7)
    )

    cultivate = _cultivate(source)

    plan = cultivate["PlanList"][0]
    assert (cultivate["UseMedicine"], cultivate["UseStone"]) == (True, True)
    assert (plan["UseMedicine"], plan["MedicineCount"]) == (True, 6)
    assert (plan["UseStone"], plan["StoneCount"]) == (True, 7)


@pytest.mark.parametrize(
    ("use_medicine", "use_stone"),
    [(False, True), (True, False), (False, False)],
)
def test_cultivate_task_inherits_closed_maa_gates(use_medicine: bool, use_stone: bool):
    source = _source_task(
        use_expiring=True, plan_medicine=(True, 6), plan_stone=(True, 7)
    )
    source["UseMedicine"] = use_medicine
    source["UseStone"] = use_stone

    cultivate = _cultivate(source)

    assert cultivate["UseMedicine"] is use_medicine
    assert cultivate["UseStone"] is use_stone


def test_cultivate_task_does_not_invent_quota_defaults():
    source = _source_task(use_expiring=True)

    plan = _cultivate(source)["PlanList"][0]

    for gate, count_key in _MAA_DEPOT_QUOTA_KEYS:
        assert gate not in plan
        assert count_key not in plan


def test_blank_quota_setting_changes_nothing():
    source = _source_task(
        use_expiring=True, plan_medicine=(True, 5), plan_stone=(True, 9)
    )
    stock_task = _stock_task(source)
    before = deepcopy(stock_task)

    _apply_depot_quota_override(stock_task, medicine=None, stone=None)

    assert stock_task == before


@pytest.mark.parametrize(("gate", "count_key"), _MAA_DEPOT_QUOTA_KEYS, ids=_QUOTA_IDS)
@pytest.mark.parametrize("count", [0, 3])
def test_quota_override_writes_plan_values(gate: str, count_key: str, count: int):
    source = _source_task(
        use_expiring=True, plan_medicine=(True, 5), plan_stone=(True, 9)
    )
    stock_task = _stock_task(source)
    source_count = source["PlanList"][0][count_key]

    _apply_depot_quota_override(
        stock_task,
        medicine=count if gate == "UseMedicine" else None,
        stone=count if gate == "UseStone" else None,
    )

    # MAA 的 DepotMaintainTask 没有任务级数量字段，数量只落在计划上。
    assert count_key not in stock_task
    assert stock_task[gate] is True
    assert (stock_task["PlanList"][0][gate], stock_task["PlanList"][0][count_key]) == (
        count > 0,
        count,
    )
    assert source["PlanList"][0][count_key] == source_count


@pytest.mark.parametrize("stock_count", [None, 0, 2])
@pytest.mark.parametrize("cultivate_count", [None, 0, 3])
def test_stock_and_cultivate_quota_settings_stay_independent(
    stock_count: int | None, cultivate_count: int | None
):
    stock_source = _source_task(
        use_expiring=True, plan_medicine=(True, 5), plan_stone=(True, 9)
    )
    cultivate_source = _source_task(
        use_expiring=True, plan_medicine=(True, 6), plan_stone=(True, 7)
    )
    stock_task = _stock_task(stock_source)
    cultivate_task = _cultivate(cultivate_source)

    _apply_depot_quota_override(stock_task, medicine=stock_count, stone=stock_count)
    _apply_depot_quota_override(
        cultivate_task, medicine=cultivate_count, stone=cultivate_count
    )
    merged = _build_stock_cultivate_task(stock_task, cultivate_task, _cultivate_plan())

    assert merged is not None
    cultivate_plan, stock_plan = merged["PlanList"]
    for gate, count_key in _MAA_DEPOT_QUOTA_KEYS:
        assert (cultivate_plan[gate], cultivate_plan[count_key]) == _expected_quota(
            cultivate_count, cultivate_source["PlanList"][0], gate, count_key
        )
        assert (stock_plan[gate], stock_plan[count_key]) == _expected_quota(
            stock_count, stock_source["PlanList"][0], gate, count_key
        )
        # 总开关只由来源任务与合并并集决定；两组都填 0 时额度已写进计划，无需关总开关。
        assert merged[gate] is True


@pytest.mark.parametrize(("gate", "count_key"), _MAA_DEPOT_QUOTA_KEYS, ids=_QUOTA_IDS)
def test_merge_without_cultivate_group_keeps_stock_gate(gate: str, count_key: str):
    stock_source = _source_task(
        use_expiring=True, plan_medicine=(True, 5), plan_stone=(True, 9)
    )
    stock_source[gate] = False

    merged = _build_stock_cultivate_task(
        _stock_task(stock_source), None, _cultivate_plan()
    )

    assert merged is not None
    assert merged[gate] is False
    assert (merged["PlanList"][0][gate], merged["PlanList"][0][count_key]) == (False, 0)


@pytest.mark.parametrize(("gate", "count_key"), _MAA_DEPOT_QUOTA_KEYS, ids=_QUOTA_IDS)
def test_merge_keeps_closed_group_quota_closed(gate: str, count_key: str):
    """MAA 关掉库存组药石总开关后，计划里残留的旧额度不能借合并后的总开关复活。"""

    stock_source = _source_task(
        use_expiring=True, plan_medicine=(True, 5), plan_stone=(True, 9)
    )
    stock_source[gate] = False
    cultivate_source = _source_task(
        use_expiring=True, plan_medicine=(True, 3), plan_stone=(True, 4)
    )

    merged = _build_stock_cultivate_task(
        _stock_task(stock_source), _cultivate(cultivate_source), _cultivate_plan()
    )

    assert merged is not None
    # 另一组仍开着，合并后的总开关取并集；关闭的那组由摊平写回计划。
    assert merged[gate] is True
    cultivate_plan, stock_plan = merged["PlanList"]
    assert cultivate_plan[gate] is True
    assert (stock_plan[gate], stock_plan[count_key]) == (False, 0)


def test_quota_settings_round_trip_through_maa_overlay():
    expected = {
        "DepotMaintainMedicineNumb": 2,
        "DepotMaintainStoneNumb": 3,
        "CultivateMedicineNumb": 4,
        "CultivateStoneNumb": 5,
        "EventDepotMaintainMedicineNumb": 6,
        "EventDepotMaintainStoneNumb": 7,
    }
    user = MaaUserConfig.model_validate({"Task": expected})

    overlay = read_overlay_values(user)
    grouped = group_overlay(overlay)

    assert {key: overlay[key] for key in expected} == expected
    assert {key: grouped["Task"][key] for key in expected} == expected


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
