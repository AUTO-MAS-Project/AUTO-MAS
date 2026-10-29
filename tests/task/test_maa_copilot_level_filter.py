"""作业分析可忽略已达精英阶段的等级差距，保留其它培养要求。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.task.MAA.tools.cultivate.copilot import analyze_copilots
from app.task.MAA.tools.cultivate.types import Progression


@pytest.fixture
def catalog():
    return [
        {
            "value": "operator",
            "label": "Operator",
            "profession": "WARRIOR",
            "rarity": 6,
            "maxElite": 2,
            "skills": [{"value": "skill", "skillIndex": 1, "maxLevel": 3}],
            "modules": [{"value": "module", "label": "Module (X)", "maxLevel": 3}],
        }
    ]


def assignment(**requirements):
    return {
        "id": 1,
        "title": "Synthetic job",
        "stage": "stage",
        "author": "Synthetic author",
        "opers": [{"name": "Operator", "requirements": requirements}],
        "groups": [],
    }


def test_level_only_gap_is_omitted_only_when_enabled(catalog):
    jobs = [assignment(elite=2, level=60, skill_level=7)]
    progressions = {"operator": Progression(2, 30, {}, {}, 7)}
    original_jobs = deepcopy(jobs)
    strict = analyze_copilots(jobs, catalog, progressions)
    assert strict["ready"] == 0
    assert strict["operators"][0]["manualLevel"]
    assert strict["operators"][0]["goals"] == []

    filtered = analyze_copilots(jobs, catalog, progressions, ignore_level_gaps=True)
    assert filtered["ready"] == filtered["projectedReady"] == 1
    assert filtered["trainable"] == 0
    assert filtered["operators"] == []
    assert filtered["assignments"][0]["state"] == "ready"
    assert filtered["assignments"][0]["gaps"] == []
    assert jobs == original_jobs
    assert progressions["operator"].level == 30


@pytest.mark.parametrize("require_modules", [True, False])
def test_other_training_requirements_are_preserved(catalog, require_modules):
    result = analyze_copilots(
        [assignment(elite=2, level=60, skill_level=10, module=1, module_level=3)],
        catalog,
        {"operator": Progression(2, 30, {}, {}, 6)},
        ignore_level_gaps=True,
        require_modules=require_modules,
    )
    assert result["ready"] == 0
    assert result["projectedReady"] == 1
    operator = result["operators"][0]
    assert operator["currentLevel"] == operator["targetLevel"] == 30
    assert not operator["manualLevel"]
    goals = {(g["kind"], g["target_id"], g["to_level"]) for g in operator["goals"]}
    expected = {("skill", "", 7), ("mastery", "skill", 3)}
    if require_modules:
        expected.add(("module", "module", 3))
    assert goals == expected


def test_unmet_elite_requirement_still_needs_training(catalog):
    result = analyze_copilots(
        [assignment(elite=2, level=60)],
        catalog,
        {"operator": Progression(1, 80, {}, {}, 7)},
        ignore_level_gaps=True,
    )
    assert result["ready"] == 0
    operator = result["operators"][0]
    assert operator["targetElite"] == 2
    assert operator["targetLevel"] == 60
    assert operator["manualLevel"]
    assert operator["goals"] == [{"kind": "elite", "target_id": "", "to_level": 2}]


def test_missing_operator_is_not_treated_as_ready(catalog):
    result = analyze_copilots(
        [assignment(elite=2, level=60)], catalog, {}, ignore_level_gaps=True
    )
    assert result["ready"] == result["projectedReady"] == 0
    assert result["missing"] == 1
    assert not result["operators"][0]["owned"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ignore_level_gaps", [None, True])
async def test_http_analysis_option_reaches_planner(
    catalog, monkeypatch, ignore_level_gaps
):
    from app.task.MAA import api, api_service
    from app.task.MAA.tools.cultivate import depot_cultivate_service

    monkeypatch.setattr(api_service, "_maa_script_config", lambda _: object())
    monkeypatch.setattr(
        api_service, "_cultivate_skland_ref", lambda *_: ("account", "role")
    )
    monkeypatch.setattr(
        api_service,
        "_get_copilot_repository",
        lambda: SimpleNamespace(
            cached=lambda *_: {
                "assignments": [assignment(elite=2, level=60, skill_level=7)],
                "updatedAt": 100,
            }
        ),
    )
    monkeypatch.setattr(
        api_service,
        "get_cultivate_skland_progression",
        AsyncMock(return_value=({"operator": Progression(2, 30, {}, {}, 7)}, 200)),
    )
    monkeypatch.setattr(
        depot_cultivate_service, "operator_catalog", AsyncMock(return_value=catalog)
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/api/scripts")
    body = {"scriptId": "script", "userId": "user", "bindingKey": "account|role"}
    if ignore_level_gaps is not None:
        body["ignoreLevelGaps"] = ignore_level_gaps
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/scripts/maa/copilot/analyze", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["code"] == 200, result
    assert result["ready"] == int(bool(ignore_level_gaps))
    assert len(result["operators"]) == int(not ignore_level_gaps)
    assert result["bindingKey"] == "account|role"
