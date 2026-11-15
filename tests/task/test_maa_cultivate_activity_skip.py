"""活动期间只跳过养成材料刷取，保留原生培养任务。"""

import importlib
import json
from copy import deepcopy
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config import MaaUserConfig
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.constants import MAA_TASKS
from app.task.MAA.tools.cultivate import DepotCultivateService, Progression
from app.task.MAA.tools.cultivate.yituliu import normalize_dataset
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "activity_open",
        "skip_activity",
        "resource_open",
        "skip_resource",
        "stock_enabled",
        "auto_raise",
        "skland_failed",
        "farming",
        "raising",
    ),
    [
        (True, True, False, False, True, True, False, False, True),
        (True, False, False, False, True, True, False, True, True),
        (False, True, False, False, True, True, False, True, True),
        (True, True, True, True, True, True, False, False, False),
        (False, True, True, True, True, True, False, False, False),
        (True, True, False, False, False, True, False, False, True),
        (True, False, False, False, False, True, False, True, True),
        (True, True, False, False, True, False, False, False, False),
        (True, True, False, False, True, True, True, False, False),
    ],
    ids=[
        "activity-pauses-farming",
        "activity-skip-off",
        "inactive-activity",
        "resource-pauses-all",
        "resource-pauses-without-activity",
        "activity-pauses-without-stock",
        "farming-without-stock",
        "auto-raise-disabled",
        "skland-unavailable",
    ],
)
async def test_activity_skip_only_suppresses_cultivation_farming(
    monkeypatch,
    tmp_path,
    activity_open,
    skip_activity,
    resource_open,
    skip_resource,
    stock_enabled,
    auto_raise,
    skland_failed,
    farming,
    raising,
):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    service_module = importlib.import_module("app.task.MAA.tools.cultivate.service")
    dataset = normalize_dataset(
        demand_raw={"one": {"allSkill": [{}] * 5 + [{"1": 5}]}},
        matrix_raw={
            "matrix": [{"stageId": "stage", "itemId": "1", "times": 1, "quantity": 1}]
        },
        stage_raw={"data": [{"stageId": "stage", "stageCode": "1-7", "apCost": 6}]},
        recipe_raw=[],
        data_version="test",
    )
    config = await activate_config(
        MaaUserConfig.model_validate(
            {
                "Info": {"Base": "independent"},
                "Task": {
                    "IfCultivate": True,
                    "CultivateTargets": json.dumps(
                        [
                            {
                                "operator_id": "one",
                                "goals": [{"kind": "skill", "to_level": 7}],
                            }
                        ]
                    ),
                    "CultivateAutoRaise": auto_raise,
                    "CultivateSkipDuringActivity": skip_activity,
                    "CultivateSkipDuringResourceCollection": skip_resource,
                    "CultivateSklandAccount": "bound",
                    "CultivateSklandUid": "bound",
                    "IfDepotMaintain": stock_enabled,
                    "IfEventDepotMaintain": False,
                    "DepotMaintainPlans": '[{"Stage":"1-7","DropId":"1","DropCount":10}]',
                },
                "Stage": {"Stage": "1-7"},
            }
        )
    )
    (tmp_path / "DepotData.json").write_text(
        '{"data":{"1":2},"syncTime":1}', encoding="utf-8"
    )
    proxy = SimpleNamespace(
        mode="Routine",
        task_dict={key: True for key in MAA_TASKS},
        cur_user_config=config,
        cur_user_item=SimpleNamespace(name="user"),
        cur_user_uid="user",
        script_info=SimpleNamespace(script_id="script"),
        task_info=SimpleNamespace(task_id="task"),
        maa_root_path=tmp_path,
        config_base="independent",
        _stock_depot_completed=False,
        _event_depot_completed=False,
        _failed_sanity_tasks=frozenset(),
        _failed_extra_tasks=set(),
        _non_sanity_retry=False,
        _missing_task_source_warned=set(),
        _cultivate_archive_dir=lambda: tmp_path,
    )
    proxy._prepare_cultivate_injection = MethodType(
        AutoProxyTask._prepare_cultivate_injection, proxy
    )
    proxy._prepare_auto_cultivate_injection = MethodType(
        AutoProxyTask._prepare_auto_cultivate_injection, proxy
    )
    proxy._set_cultivate_notice = MethodType(AutoProxyTask._set_cultivate_notice, proxy)
    activity = {
        "UtcStartTime": "2000/01/01 00:00:00",
        "UtcExpireTime": "2100/01/01 00:00:00",
        "TimeZone": 8,
    }
    stage_data = {
        "Official": {
            "sideStoryStage": {"event": {"Activity": activity}}
            if activity_open
            else {},
            "resourceCollection": activity if resource_open else {},
        }
    }
    monkeypatch.setattr(
        module,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(
                Data=SimpleNamespace(StageData=json.dumps(stage_data))
            ),
            config_path=tmp_path,
            proxy=None,
        ),
    )
    monkeypatch.setattr(
        module.maa_stage_service,
        "get_stage_info",
        AsyncMock(return_value={"Activity": []}),
    )
    monkeypatch.setattr(
        module.maa_api,
        "get_cultivate_skland_progression",
        AsyncMock(
            return_value=None
            if skland_failed
            else (
                {
                    "one": Progression(
                        elite=2, level=90, skill_level=6, masteries={}, modules={}
                    )
                },
                1,
            )
        ),
    )
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    monkeypatch.setattr(
        module,
        "depot_cultivate_service",
        DepotCultivateService(dataset_loader=AsyncMock(return_value=dataset)),
    )
    monkeypatch.setattr(
        service_module,
        "load_operator_catalog",
        AsyncMock(
            return_value=[
                {"value": "one", "label": "干员", "profession": "warrior", "skills": []}
            ]
        ),
    )
    monkeypatch.setattr(module, "read_installed_release", lambda _: ("v6.21.0", "x64"))
    gui = deepcopy(module.get_maa_base_preset())
    for item in gui["Configurations"]["Default"]["TaskQueue"]:
        if item["TaskType"] == "DepotMaintain":
            item["SkipDuringActivity"] = False
            item["SkipDuringResourceCollection"] = False

    await AutoProxyTask._apply_maa_quick_config(proxy, gui)

    queue = gui["Configurations"]["Default"]["TaskQueue"]
    stock = next((item for item in queue if item["TaskType"] == "DepotMaintain"), None)
    expected_plans = []
    if stock_enabled:
        expected_plans.append(("1-7", "1", 15 if farming else 10))
    if farming:
        expected_plans.insert(0, ("1-7", "1", 5))
    assert [
        (item["Stage"], item["DropId"], item["DropCount"])
        for item in (stock["PlanList"] if stock is not None else [])
    ] == expected_plans
    if not expected_plans:
        assert stock is None
    assert any(item["TaskType"] == "OperProgress" for item in queue) is raising
    if raising:
        auto = next(item for item in queue if item["TaskType"] == "OperProgress")
        assert auto["IsEnable"] is True
        assert auto["Plans"][0]["SkillLevel"] == 7
        task_types = [item["TaskType"] for item in queue]
        assert task_types.index("OperProgress") < task_types.index("UserDataUpdate")
        assert task_types.index("UserDataUpdate") < task_types.index("Fight")
    assert any(item["TaskType"] == "Fight" and item["IsEnable"] for item in queue)
