"""插件声明经 HTTP 到达表单，保存和动作使用同一份字段声明。"""

from typing import Annotated
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import Field, PrivateAttr, ValidationInfo, field_validator

from app.api import config_triggers, plugin
from app.config import (
    ConfigCollection,
    ConfigGroup,
    Trigger,
    ref,
    select,
    trigger_field,
    ui,
)
from app.config.core.manager import ConfigManager
from app.config.fields.hints import hint_for_field
from app.core import Config
from app.core.background_tasks import BackgroundTaskRegistry
from app.models.config import PlanEntry, PluginConfig, PluginRecord


class Settings(PluginConfig):
    class Limits(ConfigGroup):
        ratio: float = 0.125
        lower: int = Field(default=0, ge=0)
        upper: float = Field(default=0, le=0)
        positive: int = Field(default=1, gt=0)
        negative: int = Field(default=-1, lt=0)

        @field_validator("ratio")
        @classmethod
        def check_live_ratio(cls, value: float, info: ValidationInfo) -> float:
            if info.context and value > 1:
                raise ValueError("比例超过当前限额")
            return value

    class Actions(ConfigGroup):
        run: Annotated[
            Trigger, ui(widget="dropdown-button", options=["refresh", False, True])
        ] = None
        plan: Annotated[
            str, select(endpoint="/api/plugin/options/plans", plan_type="FirstPlan")
        ] = "-"

    left: Limits = Field(default_factory=Limits)
    right: Limits = Field(default_factory=Limits)
    actions: Actions = Field(default_factory=Actions)
    _received: list[str | bool] = PrivateAttr(default_factory=list)

    @trigger_field("actions.run")
    def run(self, option: str | bool):
        self._received.append(option)


@pytest_asyncio.fixture
async def form(monkeypatch):
    cfg = Settings.build()
    await cfg.activate()
    record = PluginRecord()
    record._config = cfg
    monkeypatch.setattr(Config, "plugin_registry", {record.uid: record})
    app = FastAPI()
    app.include_router(plugin.router)
    app.include_router(config_triggers.router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, str(record.uid), cfg


@pytest.mark.asyncio
async def test_numeric_and_plan_hints_reach_form(form):
    client, record, _ = form
    result = await client.post("/api/plugin_config/get", json={"recordId": record})
    hints = result.json()["data"]["ui"]["hints"]
    fields = {item["field"]: item for item in hints["left"]}
    assert fields["ratio"]["component"] == "number"
    assert 0 < fields["ratio"]["step"] < 1
    assert "precision" not in fields["ratio"]
    assert fields["lower"]["precision"] == 0 and fields["lower"]["min"] == 0
    assert fields["upper"]["max"] == 0
    assert fields["positive"]["min"] == fields["negative"]["max"] == 0
    actions = {item["field"]: item for item in hints["actions"]}
    assert actions["plan"]["plan_type"] == "FirstPlan"
    assert [item["value"] for item in actions["run"]["options"]] == [
        "refresh",
        False,
        True,
    ]


@pytest.mark.asyncio
async def test_plan_filter_and_unfiltered_post(form, monkeypatch):
    class FirstPlan(PlanEntry):
        pass

    class SecondPlan(PlanEntry):
        pass

    class Picker(ConfigGroup):
        plan: Annotated[
            UUID | str,
            select(endpoint="/api/plugin/options/plans"),
            ref("PlanConfig", entry_types=(FirstPlan,)),
        ] = "-"

    plan_hint = hint_for_field("plan", Picker.model_fields["plan"])
    plans = ConfigCollection[PlanEntry].build([FirstPlan, SecondPlan])
    await plans.activate()
    first = plans.add(FirstPlan)
    second = plans.add(SecondPlan)
    await plans.commit()
    monkeypatch.setattr(Config, "PlanConfig", plans)
    client, _, _ = form
    for body, expected in [
        ({"type": plan_hint["plan_type"]}, [str(first)]),
        ({"type": "PlanEntry"}, [str(first), str(second)]),
        (None, [str(first), str(second)]),
    ]:
        result = (await client.post("/api/plugin/options/plans", json=body)).json()
        assert result["code"] == 200
        assert [item["value"] for item in result["data"]] == expected


@pytest.mark.asyncio
async def test_invalid_patch_identifies_only_rejected_fields(form):
    client, record, _ = form

    async def save(data):
        response = await client.post(
            "/api/plugin_config/update", json={"recordId": record, "data": data}
        )
        payload = response.json()
        assert payload["status"] == "error" and payload["message"]
        return payload["fieldErrors"]

    assert await save({"left": {"lower": -1, "ratio": 0.5}, "right": {"upper": 1}}) == {
        "left.lower": "Input should be greater than or equal to 0",
        "right.upper": "Input should be less than or equal to 0",
    }
    assert await save({"left": {"ratio": 2}, "right": {"ratio": 3}}) == {
        "left.ratio": "Value error, 比例超过当前限额",
        "right.ratio": "Value error, 比例超过当前限额",
    }


@pytest.mark.asyncio
async def test_dropdown_selection_reaches_handler(form, monkeypatch):
    client, _, cfg = form
    manager = ConfigManager()
    monkeypatch.setattr(manager, "iter_persist_roots", lambda: iter((cfg,)))
    background = BackgroundTaskRegistry()
    manager.initialize_triggers(background, max_running=1)
    monkeypatch.setattr(config_triggers, "config_manager", manager)
    body = {
        "configUid": str(cfg.uid),
        "group": "actions",
        "field": "run",
        "value": True,
    }
    try:
        for option in ("refresh", False, True):
            result = (
                await client.post(
                    "/api/config/triggers/write", json=body | {"option": option}
                )
            ).json()
            assert result["data"]
            assert await background.get_group("config-triggers").drain(2)
        rejected = await client.post(
            "/api/config/triggers/write", json=body | {"option": 0}
        )
        assert rejected.json()["status"] == "error"
        assert cfg._received == ["refresh", False, True]
    finally:
        await manager.shutdown_triggers()
