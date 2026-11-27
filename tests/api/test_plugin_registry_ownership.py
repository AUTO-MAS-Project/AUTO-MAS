"""通过插件注册表 HTTP 接口查询已启用专项的类型归属。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import Field

from app.api.plugin import router
from app.config import ConfigCollection, ConfigGroup, collection
from app.core import Config, Plugin
from app.models.config import (
    PlanEntry,
    PluginRecord,
    PluginRegistryCollection,
    ScriptEntry,
    UserEntry,
)
from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl
from app.task.user_expander import UserExpander


class Demo15UserConfig(UserEntry):
    pass


class Demo15LoginConfig(Demo15UserConfig):
    class Credentials(ConfigGroup):
        Id: str = ""
        Password: str = ""

    Info: Credentials = Field(default_factory=Credentials)


class Demo15PlanConfig(PlanEntry):
    pass


class Demo15Expander(UserExpander):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("with_plan", [True, False], ids=["with-plan", "without-plan"])
async def test_registry_provided_script(monkeypatch, with_plan):
    user_type = Demo15LoginConfig if with_plan else Demo15UserConfig

    class DemoRunnerConfig(ScriptEntry):
        users: ConfigCollection[Demo15UserConfig] = collection(user_type)

    class Demo15Plugin(ScriptAdapterPlugin):
        script_type_key = "Demo15"
        decl = ScriptTypeDecl(
            script_type=DemoRunnerConfig,
            user_type=user_type,
            expander_class=Demo15Expander,
            plan_type=Demo15PlanConfig if with_plan else None,
            supports_game_binding=None if with_plan else False,
            desktop_session_check=None
            if with_plan
            else lambda config, elevated: "admin_required",
        )

    registry = PluginRegistryCollection.build()
    await registry.activate()
    uid = registry.add(
        PluginRecord,
        payload={"info": {"plugin_name": "demo15_adapter", "state": "disabled"}},
    )
    await registry.commit()
    record = registry[uid]
    record._plugin_cls = Demo15Plugin
    monkeypatch.setattr(Config, "plugin_registry", registry)
    monkeypatch.setattr(Config, "ScriptConfig", ConfigCollection[ScriptEntry].build())
    monkeypatch.setattr(Config, "PlanConfig", ConfigCollection[PlanEntry].build())

    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def ownership(path):
            response = await client.post(path, json={"recordId": str(uid)})
            response.raise_for_status()
            body = response.json()
            assert body["code"] == 200, body
            return body["data"][str(uid)]["providedScript"]

        await Plugin.enable(record)
        try:
            provided = await ownership("/api/plugin/registry/get")
            assert provided == {
                "scriptKey": "Demo15",
                "scriptConfigType": "DemoRunnerConfig",
                "userConfigType": "Demo15LoginConfig"
                if with_plan
                else "Demo15UserConfig",
                "planConfigType": "Demo15PlanConfig" if with_plan else None,
                "supportsGameBinding": with_plan,
                "supportsDesktopSession": not with_plan,
                "hasAccountField": with_plan,
                "hasPasswordField": with_plan,
            }
            assert await ownership("/api/plugin_registry/get") == provided
        finally:
            await Plugin.disable(record)
        assert await ownership("/api/plugin/registry/get") is None
