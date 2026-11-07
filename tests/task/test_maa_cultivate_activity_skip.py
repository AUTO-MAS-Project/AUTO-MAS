"""活动期间只跳过养成材料刷取，保留原生培养任务。"""

import importlib
import json
from copy import deepcopy
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.constants import MAA_TASKS
from app.task.MAA.tools.cultivate.types import (
    CultivatePlan,
    FarmEntry,
    Goal,
    OperatorTarget,
    Requirement,
)


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
    target = OperatorTarget("one", (Goal("skill", "", 7),))
    plan = CultivatePlan(
        entries=(FarmEntry(item_id="1", amount=3, stage_code="1-7"),),
        reservations=(Requirement(item_id="1", amount=5),),
    )
    config = SimpleNamespace(
        Task=SimpleNamespace(
            IfCultivate=True,
            CultivateAllOwned=False,
            CultivateTargets=json.dumps(
                [{"operator_id": "one", "goals": [{"kind": "skill", "to_level": 7}]}]
            ),
            CultivateAutoRaise=auto_raise,
            CultivateSkipDuringActivity=skip_activity,
            CultivateSkipDuringResourceCollection=skip_resource,
            CultivateSklandAccount="bound" if skland_failed else "",
            CultivateSklandUid="bound" if skland_failed else "",
            IfDepotMaintain=stock_enabled,
            DepotMaintainPlans='[{"Stage":"1-7","DropId":"1","DropCount":10}]',
            CultivateMedicineNumb=None,
            CultivateStoneNumb=None,
            DepotMaintainMedicineNumb=None,
            DepotMaintainStoneNumb=None,
            InfrastMode="Normal",
            IfEventDepotMaintain=False,
        ),
        Info=SimpleNamespace(Server="Official"),
        Stage=SimpleNamespace(
            StageMode="Fixed",
            MedicineNumb=0,
            SeriesNumb="0",
            Stage="1-7",
            Stage_1="-",
            Stage_2="-",
            Stage_3="-",
        ),
        Data=SimpleNamespace(CultivateNotice=""),
        commit=AsyncMock(),
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
        _set_cultivate_notice=AsyncMock(),
        _warn_missing_task_source=AsyncMock(),
    )
    proxy._prepare_cultivate_injection = MethodType(
        AutoProxyTask._prepare_cultivate_injection, proxy
    )
    proxy._prepare_auto_cultivate_injection = MethodType(
        AutoProxyTask._prepare_auto_cultivate_injection, proxy
    )
    monkeypatch.setattr(
        module,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(Data=SimpleNamespace(StageData="{}")),
            config_path=tmp_path,
            proxy=None,
        ),
    )
    monkeypatch.setattr(
        module,
        "_maa_activity_state",
        lambda *args, **kwargs: (activity_open, resource_open),
    )
    monkeypatch.setattr(
        module.maa_stage_service,
        "get_stage_info",
        AsyncMock(return_value={"Activity": []}),
    )
    monkeypatch.setattr(
        module.maa_api, "get_cultivate_skland_progression", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    monkeypatch.setattr(module, "resolve_progression", lambda **kwargs: None)
    monkeypatch.setattr(
        module, "filter_observed_cultivate_targets", lambda *args: ((target,), ())
    )
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "prepare_cultivate",
        AsyncMock(return_value=([target], plan, True, (target,))),
    )
    monkeypatch.setattr(
        module.depot_cultivate_service,
        "operator_catalog",
        AsyncMock(
            return_value=[
                {"value": "one", "label": "干员", "profession": "warrior", "skills": []}
            ]
        ),
    )
    monkeypatch.setattr(module, "read_installed_release", lambda _: ("v6.21.0",))
    gui = deepcopy(module.get_maa_base_preset())
    for item in gui["Configurations"]["Default"]["TaskQueue"]:
        if item["TaskType"] == "DepotMaintain":
            item["SkipDuringActivity"] = False
            item["SkipDuringResourceCollection"] = False

    await AutoProxyTask._apply_maa_quick_config(proxy, gui)

    queue = gui["Configurations"]["Default"]["TaskQueue"]
    stock = next((item for item in queue if item["TaskType"] == "DepotMaintain"), None)
    if stock_enabled:
        assert stock["PlanList"][-1]["DropCount"] == (15 if farming else 10)
        assert len(stock["PlanList"]) == (2 if farming else 1)
    elif farming:
        assert stock["PlanList"][0]["DropCount"] == 3
    else:
        assert stock is None
    assert any(item["TaskType"] == "OperProgress" for item in queue) is raising
    if raising:
        task_types = [item["TaskType"] for item in queue]
        assert task_types.index("OperProgress") < task_types.index("UserDataUpdate")
        assert task_types.index("UserDataUpdate") < task_types.index("Fight")
        assert proxy._cultivate_auto_raise_injected is True
        assert proxy.task_dict["干员培养"] is True
        assert proxy.task_dict["更新数据"] is True

        # 日志已确认完成的非体力附加任务，不随其他任务的重试再次下发。
        proxy.task_dict.update({"干员培养": False, "更新数据": False})
        retried_gui = deepcopy(module.get_maa_base_preset())
        await AutoProxyTask._apply_maa_quick_config(proxy, retried_gui)
        assert not any(
            item["TaskType"] in ("OperProgress", "UserDataUpdate")
            for item in retried_gui["Configurations"]["Default"]["TaskQueue"]
        )
