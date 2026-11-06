"""库存合成的整套抵扣、共享消耗与失败回退。"""

from dataclasses import replace
from datetime import date

import pytest

from app.task.MAA.tools.cultivate import (
    Goal,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
    build_plan,
    has_material_gap,
)
from app.task.MAA.tools.cultivate.yituliu import normalize_dataset


@pytest.fixture
def scenario():
    data = normalize_dataset(
        demand_raw={"one": {"allSkill": [{}] * 4 + [{"3302": 2}, {"3303": 2}]}},
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
    snapshot = ProgressionSnapshot(
        source="skland",
        timestamp=0,
        data=Progression(elite=2, level=90, skill_level=6, masteries={}, modules={}),
    )
    return dict(
        targets=[
            OperatorTarget("one", (Goal(kind="skill", target_id="", to_level=7),))
        ],
        snapshots={"one": snapshot},
        data=data,
        today=date(2026, 11, 6),
    )


@pytest.mark.parametrize(
    ("inventory", "remaining", "reserved", "sanity"),
    [
        ({"3302": 2, "3301": 12}, 0, {"3303": 2, "3302": 6, "3301": 12}, 0),
        ({"3302": 5}, 1, {"3303": 2, "3302": 3}, 15),
        ({"3302": 2, "3301": 2}, 2, {"3303": 2}, 30),
    ],
    ids=["two-level-crafting", "partial-whole-books", "incomplete-set"],
)
def test_only_complete_inventory_recipes_reduce_farming(
    scenario, inventory, remaining, reserved, sanity
):
    before = dict(inventory)
    plan = build_plan(**scenario, inventory=inventory)
    assert [(item.item_id, item.amount) for item in plan.entries] == (
        [("3303", remaining)] if remaining else []
    )
    assert has_material_gap(**scenario, inventory=inventory) is bool(remaining)
    assert {item.item_id: item.amount for item in plan.reservations} == reserved
    # CA-5 卷3每本15理智；即使补卷2更省，也不利用不足整套的余料改选路线。
    assert sum(item.expected_sanity for item in plan.entries) == sanity
    assert inventory == before


def test_skill_levels_share_inventory_without_double_counting(scenario):
    snapshot = scenario["snapshots"]["one"]
    scenario["snapshots"]["one"] = replace(
        snapshot, data=replace(snapshot.data, skill_level=5)
    )
    plan = build_plan(**scenario, inventory={"3302": 3})
    # 升6级先用两本卷2，余下一本不能再抵扣升7级所需的两本卷3。
    assert [(item.item_id, item.amount) for item in plan.entries] == [("3303", 2)]
    assert {item.item_id: item.amount for item in plan.reservations} == {
        "3302": 2,
        "3303": 2,
    }


@pytest.mark.parametrize(
    "complete", [False, True], ids=["missing-ingredient", "complete"]
)
def test_recipe_crafting_updates_shared_inventory_only_on_success(scenario, complete):
    scenario["targets"] = [
        OperatorTarget("one", (Goal(kind="mastery", target_id="skill", to_level=1),))
    ]
    scenario["data"] = normalize_dataset(
        demand_raw={
            "one": {
                "allSkill": [{}] * 5 + [{"30023": 2}],
                "skills": [
                    {
                        "skillId": "skill",
                        "skillLevelUpCost": [[{"id": "30024", "count": 1}]],
                    }
                ],
            }
        },
        matrix_raw={
            "matrix": [
                {"stageId": "stage", "itemId": item_id, "times": 1, "quantity": 1}
                for item_id in ("30024", "30023", "30043", "30083")
            ]
        },
        stage_raw={"data": [{"stageId": "stage", "stageCode": "3-4", "apCost": 18}]},
        recipe_raw=[
            {
                "itemId": "30024",
                "pathway": [
                    {"itemId": item_id, "count": count}
                    for item_id, count in {"30023": 2, "30043": 1, "30083": 1}.items()
                ],
            }
        ],
        data_version="test",
    )
    # 缺锰矿时糖组留给技能前置；合成成功时糖组已耗尽，技能前置须补刷。
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
