import json

import httpx
import pytest
from fastapi import FastAPI

from app.config import ConfigCollection
from app.models.config import OkNtePlanConfig
from app.models.schema import OkNtePlanKey
from app.task.OkNte.tools.plan import apply_plan


@pytest.mark.asyncio
async def test_bound_script_discovers_fields_without_copying_values(
    isolated_app_paths, monkeypatch, tmp_path
):
    from app.models.config import OkNteConfig, OkNteUserConfig
    from app.task.OkNte.api_service import plan_configs

    work = tmp_path / "mas"
    work.mkdir()
    monkeypatch.chdir(work)
    tmp_path = tmp_path / "script"
    tmp_path.mkdir()
    from app.config import config_manager

    plans = ConfigCollection.build([OkNtePlanConfig])
    scripts = ConfigCollection.build([OkNteConfig])
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setitem(config_manager._collections, "ScriptConfig", scripts)
    await plans.activate()
    await scripts.activate()
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    monkeypatch.setattr(isolated_app_paths, "ScriptConfig", scripts)
    plan_id = plans.add(OkNtePlanConfig)
    script_id = scripts.add(OkNteConfig)
    await plans.commit()
    await scripts.commit()
    script = scripts[script_id]
    user_id = script.UserData.add(OkNteUserConfig)
    await script.UserData.commit()
    await script.UserData[user_id].update(
        OkNteUserConfig.model_validate({"Info": {"PlanMode": str(plan_id)}}),
        check_visibility=False,
    )
    assert script.UserData[user_id].Info.PlanMode == plan_id
    await script.update(
        OkNteConfig.model_validate(
            {"Script": {"ConfigPath": str(tmp_path), "ConfigPathMode": "Folder"}}
        ),
        check_visibility=False,
    )
    (tmp_path / "DailyRoutineTask.json").write_text(
        json.dumps({"Routine Items": [{"id": "future_task", "enabled": True}]}),
        encoding="utf-8",
    )
    (tmp_path / "DailyRoutineTaskConfigs.json").write_text(
        json.dumps(
            {"future_task": {"toggle": True, "nested": {"count": 12}, "values": [1, 2]}}
        ),
        encoding="utf-8",
    )
    before = plans[plan_id].Monday.Key.model_dump()
    files = plan_configs(str(plan_id), "Monday")
    routine = next(
        file for file in files if file["filename"] == "DailyRoutineTask.json"
    )
    assert any(
        item["id"] == "future_task" for item in routine["fields"][0]["itemDefinitions"]
    )
    detail = next(
        file for file in files if file["filename"] == "DailyRoutineTaskConfigs.json"
    )
    group = next(field for field in detail["fields"] if field["name"] == "future_task")
    children = {field["name"]: field for field in group["children"]}
    assert children["toggle"]["type"] == "bool"
    assert children["nested"]["children"][0]["type"] == "int"
    assert children["values"]["value"] == [1, 2]
    assert plans[plan_id].Monday.Key.model_dump() == before
    # File references must still expose both plan files so replace saves are lossless.
    await script.update(
        OkNteConfig.model_validate(
            {
                "Script": {
                    "ConfigPath": str(tmp_path / "DailyRoutineTask.json"),
                    "ConfigPathMode": "File",
                }
            }
        ),
        check_visibility=False,
    )
    plans[plan_id].Monday.Key = OkNtePlanKey(
        Configs={
            "DailyRoutineTaskConfigs.json": {"daily_anomaly": {"目标消耗体力": 77}},
            "DailyRoutineTask.json": {
                "Routine Items": [{"id": "coffee", "enabled": True}]
            },
        }
    )
    await plans[plan_id].commit()
    files = plan_configs(str(plan_id), "Monday")
    draft = {file["filename"]: file["overrides"] for file in files}
    draft["DailyRoutineTask.json"]["Routine Items"][0]["enabled"] = False
    group, key = plan_configs(str(plan_id), "Monday", draft, replace=True)
    await isolated_app_paths.update_plan(str(plan_id), {group: {"Key": key}})
    assert (
        plans[plan_id].Monday.Key.Configs["DailyRoutineTaskConfigs.json"][
            "daily_anomaly"
        ]["目标消耗体力"]
        == 77
    )
    assert {file["filename"] for file in files} == {
        "DailyRoutineTask.json",
        "DailyRoutineTaskConfigs.json",
    }
    # A new installation can be configured before its native daily files exist.
    (tmp_path / "DailyRoutineTask.json").unlink()
    files = plan_configs(str(plan_id), "Monday")
    assert len(files) == 2


def test_plan_overlay_keeps_other_routine_items_and_account_fields(tmp_path):
    routine = tmp_path / "DailyRoutineTask.json"
    details = tmp_path / "DailyRoutineTaskConfigs.json"
    routine.write_text(
        json.dumps(
            {
                "Routine Items": [
                    {"id": "daily_anomaly", "enabled": False},
                    {"id": "coffee", "enabled": True},
                ],
                "other": 123,
            }
        )
    )
    details.write_text(
        json.dumps(
            {"coffee": {"模式": "领取/补货"}, "daily_anomaly": {"unknown": "keep"}}
        )
    )
    key = OkNtePlanKey()
    key.Configs["DailyRoutineTaskConfigs.json"]["daily_anomaly"]["目标消耗体力"] = 120
    apply_plan(tmp_path, key)
    data = json.loads(routine.read_text(encoding="utf-8"))
    assert data["other"] == 123
    assert {"id": "coffee", "enabled": True} in data["Routine Items"]
    data = json.loads(details.read_text(encoding="utf-8"))
    assert data["coffee"] == {"模式": "领取/补货"}
    assert data["daily_anomaly"]["unknown"] == "keep"
    assert data["daily_anomaly"]["目标消耗体力"] == 120


@pytest.mark.asyncio
async def test_quick_and_detail_share_selected_day(isolated_app_paths, monkeypatch):
    from app.api.plan import router as plans_router
    from app.task.OkNte.api import router as configs_router

    plans = ConfigCollection.build([OkNtePlanConfig])
    await plans.activate()
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    app = FastAPI()
    app.include_router(plans_router)
    app.include_router(configs_router, prefix="/api/scripts")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = (
            await client.post("/api/plan/add", json={"type": "OkNtePlan"})
        ).json()
        assert response["code"] == 200
        uid = response["planId"]
        plan = plans[uid]
        patch = {
            "DailyRoutineTaskConfigs.json": {
                "daily_anomaly": {"目标消耗体力": 90},
                "coffee": {"补货货物": False},
            }
        }
        saved = await client.post(
            "/api/scripts/oknte/plan/save",
            json={"plan_id": uid, "day": "Monday", "configs": patch},
        )
        assert saved.json()["code"] == 200
        assert (
            plan.Monday.Key.Configs["DailyRoutineTaskConfigs.json"]["daily_anomaly"][
                "目标消耗体力"
            ]
            == 90
        )
        assert (
            plan.Tuesday.Key.Configs["DailyRoutineTaskConfigs.json"]["daily_anomaly"][
                "目标消耗体力"
            ]
            == 180
        )
        result = (
            await client.post(
                "/api/scripts/oknte/plan/configs",
                params={"plan_id": uid, "day": "Monday"},
            )
        ).json()
        daily = next(
            x for x in result["data"] if x["filename"] == "DailyRoutineTaskConfigs.json"
        )
        assert daily["currentData"]["coffee"]["补货货物"] is False
        # A quick edit preserves the detailed daily settings.
        key = plan.Monday.Key.model_dump()
        key["Configs"]["DailyRoutineTaskConfigs.json"]["daily_anomaly"][
            "目标消耗体力"
        ] = 60
        updated = (
            await client.post(
                "/api/plan/update",
                json={"planId": uid, "data": {"Monday": {"Key": key}}},
            )
        ).json()
        assert updated["code"] == 200
        assert (
            plan.Monday.Key.Configs["DailyRoutineTaskConfigs.json"]["coffee"][
                "补货货物"
            ]
            is False
        )

        # Restoring inheritance removes the actual override, including explicit False.
        replacement = plan.Monday.Key.model_dump()["Configs"]
        replacement["DailyRoutineTaskConfigs.json"].pop("coffee")
        reset = (
            await client.post(
                "/api/scripts/oknte/plan/save",
                json={
                    "plan_id": uid,
                    "day": "Monday",
                    "configs": replacement,
                    "replace": True,
                },
            )
        ).json()
        assert reset["code"] == 200
        assert "coffee" not in plan.Monday.Key.Configs["DailyRoutineTaskConfigs.json"]
        current = (
            await client.post(
                "/api/scripts/oknte/plan/configs",
                params={"plan_id": uid, "day": "Monday"},
            )
        ).json()
        detail = next(
            item
            for item in current["data"]
            if item["filename"] == "DailyRoutineTaskConfigs.json"
        )
        assert "coffee" not in detail["overrides"]
        invalid = (
            await client.post(
                "/api/scripts/oknte/plan/configs",
                params={"plan_id": uid, "day": "invalid"},
            )
        ).json()
        assert invalid["code"] == 400
        assert invalid["status"] == "error"
        assert invalid["message"] == "无效的计划日期"
        assert invalid["data"] == []
        rejected = (
            await client.post(
                "/api/scripts/oknte/plan/save",
                json={"plan_id": uid, "day": "invalid", "configs": {}},
            )
        ).json()
        assert rejected["code"] == 400
        assert rejected["message"] == "无效的计划日期"


def test_routine_false_and_inheritance_are_distinct(tmp_path):
    routine = tmp_path / "DailyRoutineTask.json"
    base = {"Routine Items": [{"id": "coffee", "enabled": True}]}
    routine.write_text(json.dumps(base), encoding="utf-8")
    apply_plan(
        tmp_path,
        OkNtePlanKey(
            Configs={
                "DailyRoutineTask.json": {
                    "Routine Items": [{"id": "coffee", "enabled": False}]
                }
            }
        ),
    )
    assert (
        json.loads(routine.read_text(encoding="utf-8"))["Routine Items"][0]["enabled"]
        is False
    )
    routine.write_text(json.dumps(base), encoding="utf-8")
    apply_plan(tmp_path, OkNtePlanKey(Configs={}))
    assert (
        json.loads(routine.read_text(encoding="utf-8"))["Routine Items"][0]["enabled"]
        is True
    )
