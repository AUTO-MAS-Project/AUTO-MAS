"""养成计划优先使用现有库存合成，再安排缺口刷取。"""

from dataclasses import replace
from datetime import date

import pytest

from app.task.MAA.tools.cultivate import (
    DemandEntry,
    DropEntry,
    Goal,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
    Recipe,
    StageMeta,
    build_plan,
    has_material_gap,
)
from app.task.MAA.tools.cultivate.yituliu import normalize_dataset

TODAY = date(2026, 11, 6)  # 周五，CA-5 开放。


@pytest.fixture
def skill_summary_scenario():
    data = normalize_dataset(
        demand_raw={
            operator_id: {"allSkill": [{}, {}, {}, {}, {"3302": 2}, {"3303": 2}]}
            for operator_id in ("one", "two")
        },
        matrix_raw={
            "matrix": [
                {"stageId": "wk_fly_5", "itemId": "3303", "times": 1, "quantity": 2},
                {"stageId": "wk_fly_5", "itemId": "3302", "times": 2, "quantity": 3},
                {"stageId": "wk_fly_5", "itemId": "3301", "times": 2, "quantity": 3},
                {"stageId": "wk_fly_3", "itemId": "3302", "times": 1, "quantity": 3},
            ]
        },
        stage_raw={
            "data": [{"stageId": "wk_fly_3", "stageCode": "CA-3", "apCost": 20}]
        },
        recipe_raw=[],
        data_version="test",
    )
    targets = [
        OperatorTarget(
            operator_id="one", goals=(Goal(kind="skill", target_id="", to_level=7),)
        )
    ]
    snapshots = {
        operator_id: ProgressionSnapshot(
            source="skland",
            timestamp=0,
            data=Progression(
                elite=2, level=90, skill_level=6, masteries={}, modules={}
            ),
        )
        for operator_id in ("one", "two")
    }
    return {"targets": targets, "snapshots": snapshots, "data": data, "today": TODAY}


def test_lower_inventory_covers_skill_summaries_before_direct_farming(
    skill_summary_scenario,
):
    inventory = {"3302": 2, "3301": 12}
    plan = build_plan(**skill_summary_scenario, inventory=inventory)

    assert plan.entries == ()
    assert not has_material_gap(**skill_summary_scenario, inventory=inventory)
    assert {item.item_id: item.amount for item in plan.reservations} == {
        "3303": 2,
        "3302": 6,
        "3301": 12,
    }
    assert inventory == {"3302": 2, "3301": 12}


@pytest.mark.parametrize(
    ("inventory", "remaining", "reserved", "expected_sanity"),
    [
        ({"3303": 1, "3302": 3}, 0, {"3303": 2, "3302": 3}, 0),
        ({"3302": 5}, 1, {"3303": 2, "3302": 3}, 15),
        ({"3302": 2, "3301": 2}, 2, {"3303": 2}, 30),
        ({}, 2, {"3303": 2}, 30),
    ],
    ids=["finished-stock-first", "partial-whole-books", "incomplete-set", "no-stock"],
)
def test_only_whole_books_reduce_the_remaining_farming_gap(
    skill_summary_scenario, inventory, remaining, reserved, expected_sanity
):
    plan = build_plan(**skill_summary_scenario, inventory=inventory)

    assert [(item.item_id, item.amount) for item in plan.entries] == (
        [("3303", remaining)] if remaining else []
    )
    assert has_material_gap(**skill_summary_scenario, inventory=inventory) is bool(
        remaining
    )
    assert {item.item_id: item.amount for item in plan.reservations} == reserved
    # CA-5 每次30理智、平均掉两本卷3；凑不齐整套的低级卷不降低预计理智。
    # 即使 CA-3 补一本卷2只需约6.7理智，也不为利用零散库存而改选该路线。
    assert sum(item.expected_sanity for item in plan.entries) == expected_sanity


def test_shared_inventory_is_not_used_again_for_a_later_goal(skill_summary_scenario):
    scenario = skill_summary_scenario
    scenario["targets"].append(
        OperatorTarget(
            operator_id="two", goals=(Goal(kind="skill", target_id="", to_level=6),)
        )
    )
    scenario["snapshots"]["two"] = replace(
        scenario["snapshots"]["two"],
        data=replace(scenario["snapshots"]["two"].data, skill_level=5),
    )
    inventory = {"3302": 3}
    plan = build_plan(**scenario, inventory=inventory)

    # 卷2先合成一本卷3，后一名干员需要的两本卷2须另补。
    assert [(item.item_id, item.amount, item.held) for item in plan.entries] == [
        ("3303", 1, 0),
        ("3302", 2, 3),
    ]
    assert {item.item_id: item.amount for item in plan.reservations} == {
        "3303": 2,
        "3302": 5,
    }
    assert has_material_gap(**scenario, inventory=inventory)


@pytest.mark.parametrize(
    "complete", [False, True], ids=["missing-ingredient", "complete"]
)
def test_multi_ingredient_crafting_commits_only_complete_sets(
    skill_summary_scenario, complete
):
    scenario = skill_summary_scenario
    scenario["data"] = replace(
        scenario["data"],
        demands={
            "one": (DemandEntry("mastery", "skill", 1, {"30024": 1}),),
            "two": (DemandEntry("skill", "", 7, {"30023": 2}),),
        },
        recipes=(Recipe("30024", {"30023": 2, "30043": 1, "30083": 1}),),
        stages={"stage": StageMeta("stage", "3-4", 18, None)},
        drops=tuple(
            DropEntry("stage", item_id, 1.0, 0, None)
            for item_id in ("30024", "30023", "30043", "30083")
        ),
        material_class={
            item_id: "farmable" for item_id in ("30024", "30023", "30043", "30083")
        },
    )
    scenario["targets"] = [
        OperatorTarget("one", (Goal("mastery", "skill", 1),)),
        OperatorTarget("two", (Goal("skill", "", 7),)),
    ]
    scenario["snapshots"]["one"] = replace(
        scenario["snapshots"]["one"],
        data=replace(scenario["snapshots"]["one"].data, skill_level=7),
    )
    inventory = {"30023": 2, "30043": 1, "30083": int(complete)}
    plan = build_plan(**scenario, inventory=inventory)

    assert [(item.item_id, item.amount) for item in plan.entries] == (
        [("30023", 2)] if complete else [("30024", 1)]
    )
    assert {item.item_id: item.amount for item in plan.reservations} == (
        {"30024": 1, "30023": 4, "30043": 1, "30083": 1}
        if complete
        else {"30024": 1, "30023": 2}
    )
