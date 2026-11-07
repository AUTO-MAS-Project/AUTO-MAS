from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.plan import router
from app.config import ConfigCollection
from app.core.config.universal_plan import plan_directory, save_plan_config
from app.models.config import GeneralConfig, GeneralUserConfig, UniversalPlanConfig


@pytest.mark.asyncio
async def test_create_and_query_saved_dates(isolated_app_paths, monkeypatch):
    from app.task.general.registration import build_config_handler

    config = isolated_app_paths
    monkeypatch.setattr(
        config, "_script_config_handlers", {GeneralConfig: build_config_handler()}
    )
    working = config.work_path / "app"
    working.mkdir()
    monkeypatch.chdir(working)
    native = config.data_path / "settings.json"
    native.write_text("base")
    script = GeneralConfig.build(
        payload={"Script": {"ConfigPath": str(native), "ConfigPathMode": "File"}}
    )
    await script.activate()
    user_id = script.UserData.add(GeneralUserConfig)
    await script.UserData.commit()
    plans = ConfigCollection.build([UniversalPlanConfig])
    await plans.activate()
    monkeypatch.setattr(config, "ScriptConfig", {script.uid: script})
    monkeypatch.setattr(config, "PlanConfig", plans)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = (
            await client.post("/api/plan/add", json={"type": "UniversalPlan"})
        ).json()
        assert invalid["code"] != 200
        created = (
            await client.post(
                "/api/plan/add",
                json={
                    "type": "UniversalPlan",
                    "scriptId": str(script.uid),
                },
            )
        ).json()
        assert created["code"] == 200
        plan_id = created["planId"]
        assert created["data"]["Info"]["ResetHour"] == 4
        assert "UserId" not in created["data"]["Info"]
        state = (
            await client.post("/api/plan/universal-state", json={"planId": plan_id})
        ).json()
        assert state["configuredDays"] == []
        wrong_plan_id = plans.add(
            UniversalPlanConfig,
            payload={"Info": {"ScriptId": str(uuid4())}},
        )
        await plans.commit()
        with pytest.raises(ValueError):
            await config.update_user(
                str(script.uid),
                str(user_id),
                {"Info": {"PlanMode": str(wrong_plan_id)}},
            )
        assert script.UserData[user_id].Info.PlanMode == "Fixed"
        plan = plans[plan_id]
        target = plan_directory(
            data_path=config.data_path,
            plan=plan,
            script_id=str(script.uid),
            user_id=str(user_id),
            day="Monday",
        )
        save_plan_config(source=native, destination=target, mode="File")
        state = (
            await client.post("/api/plan/universal-state", json={"planId": plan_id})
        ).json()
        assert state["configuredDays"] == ["Monday"]
        result = (
            await client.post(
                "/api/plan/update",
                json={
                    "planId": plan_id,
                    "data": {"Info": {"ResetHour": 6, "ResetMinute": 30}},
                },
            )
        ).json()
        assert result["code"] == 200
        assert plan.Info.ResetHour == 6
        assert plan.Info.ResetMinute == 30
        changed_owner = (
            await client.post(
                "/api/plan/update",
                json={"planId": plan_id, "data": {"Info": {"ScriptId": str(uuid4())}}},
            )
        ).json()
        assert changed_owner.get("code", 422) != 200
        ticket = await plan.lock_s()
        try:
            locked = (
                await client.post(
                    "/api/plan/update",
                    json={"planId": plan_id, "data": {"Info": {"ResetHour": 7}}},
                )
            ).json()
            assert locked["code"] != 200
            assert plan.Info.ResetHour == 6
        finally:
            await plan.unlock(ticket)

        # 删除计划时同时清掉按计划 ID 归档在脚本数据目录下的模板与备份
        deleted = (
            await client.post("/api/plan/delete", json={"planId": plan_id})
        ).json()
        assert deleted["code"] == 200
        assert not (config.data_path / str(script.uid) / "Plans" / plan_id).exists()
