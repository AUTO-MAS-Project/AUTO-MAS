"""活动选关的新选择覆盖旧迁移项，且不污染其他账号的计划。"""

import json
from copy import deepcopy

import pytest

from app.task.MAA.tools.activity_inventory import resolve_activity_inventory_plans

STAGES = [
    {"Value": "TL-9", "Drop": "31113"},
    {"Value": "TL-8", "Drop": "31083"},
    {"Value": "TL-7", "Drop": "31043"},
    {"Value": "TL-4", "Drop": "搓玉效率0.69"},
]
LEGACY = {
    "StageType": "activity",
    "StageIndex": 1,
    "DropCount": 999,
    "OrundumDropCount": 9999,
    "LegacyActivityFirst": True,
}


def _only_orundum() -> list[dict]:
    return [
        deepcopy(LEGACY),
        *[
            {"StageType": "material", "StageIndex": i, "DropCount": 999, "Skip": True}
            for i in range(1, 4)
        ],
        {"StageType": "orundum", "StageIndex": 1, "DropCount": 9999},
    ]


@pytest.mark.parametrize("all_skipped", [False, True])
def test_explicit_skip_overrides_legacy_activity_first(all_skipped):
    rows = _only_orundum()
    if all_skipped:
        rows[-1]["Skip"] = True
    plans, notices = resolve_activity_inventory_plans(json.dumps(rows), STAGES)
    assert [plan["Stage"] for plan in plans] == ([] if all_skipped else ["TL-4"])
    assert not notices


def test_unedited_legacy_selection_and_custom_target_are_preserved():
    saved = json.dumps([LEGACY])
    plans, _ = resolve_activity_inventory_plans(saved, STAGES)
    assert [(plan["Stage"], plan["DropCount"]) for plan in plans] == [("TL-9", 999)]

    custom = {"StageType": "material", "StageIndex": 1, "DropCount": 123}
    plans, _ = resolve_activity_inventory_plans(json.dumps([LEGACY, custom]), STAGES)
    assert [(plan["Stage"], plan["DropCount"]) for plan in plans] == [("TL-9", 123)]


@pytest.mark.parametrize("legacy_index", [2, 99])
def test_skip_matches_resolved_stage_after_activity_changes(legacy_index):
    # 搓玉关排在材料关之前，activity:2 与 material:1 指向同一关。
    stages = [STAGES[-1], *STAGES[:-1]]
    legacy = {**LEGACY, "StageIndex": legacy_index}
    skip_kind = "material" if legacy_index == 2 else "orundum"
    rows = [
        legacy,
        {"StageType": skip_kind, "StageIndex": 1, "DropCount": 999, "Skip": True},
    ]
    plans, _ = resolve_activity_inventory_plans(json.dumps(rows), stages)
    assert plans == []


def test_invalid_skip_does_not_cancel_a_different_stage():
    rows = [
        LEGACY,
        {"StageType": "material", "StageIndex": 99, "DropCount": 999, "Skip": True},
    ]
    plans, _ = resolve_activity_inventory_plans(json.dumps(rows), STAGES)
    assert [plan["Stage"] for plan in plans] == ["TL-9"]


def test_same_index_in_different_categories_does_not_cancel_another_stage():
    rows = [
        LEGACY,
        {"StageType": "material", "StageIndex": 1, "DropCount": 999, "Skip": True},
    ]
    plans, _ = resolve_activity_inventory_plans(
        json.dumps(rows), [STAGES[-1], *STAGES[:-1]]
    )
    assert [plan["Stage"] for plan in plans] == ["TL-4"]


@pytest.mark.parametrize("skip", [False, True])
def test_new_selection_overrides_old_material_index_fallback(skip):
    old = {
        "StageType": "material",
        "StageIndex": 3,
        "DropCount": 123,
        "LegacyIndex": True,
    }
    selected = {
        "StageType": "material",
        "StageIndex": 1,
        "DropCount": 321,
        "Skip": skip,
    }
    plans, _ = resolve_activity_inventory_plans(
        json.dumps([old, LEGACY, selected]), [STAGES[0], STAGES[-1]]
    )
    assert [(plan["Stage"], plan["DropCount"]) for plan in plans] == (
        [] if skip else [("TL-9", 321)]
    )


def test_alternating_accounts_does_not_reuse_previous_selection():
    source = [{"Stage": "TL-9", "DropId": "31113", "UseMedicine": True}]
    original = deepcopy(source)
    for rows, expected in [
        ([LEGACY], ["TL-9"]),
        (_only_orundum(), ["TL-4"]),
        ([LEGACY], ["TL-9"]),
    ]:
        plans, _ = resolve_activity_inventory_plans(
            json.dumps(rows), STAGES, source_plans=source
        )
        assert [plan["Stage"] for plan in plans] == expected
    assert source == original
