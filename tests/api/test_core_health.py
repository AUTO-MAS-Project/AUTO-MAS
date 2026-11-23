import httpx
import pytest
from fastapi import FastAPI

import app.api.core as core_api
from app.core.startup import StartupActivation


@pytest.fixture(autouse=True)
def startup(monkeypatch: pytest.MonkeyPatch) -> StartupActivation:
    activation = StartupActivation(deferred=False)
    monkeypatch.setattr(core_api, "Startup", activation)
    return activation


@pytest.mark.asyncio
async def test_runtime_activation_is_idempotent_and_not_an_mcp_tool(
    startup: StartupActivation,
) -> None:
    app = FastAPI()
    app.include_router(core_api.router)
    app.state.background_status = "starting"
    app.state.background_error = None
    app.state.background_warnings = []
    startup.prepare(deferred=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/core/startup/activate")).status_code == 409
        health = (await client.get("/api/core/health")).json()
        assert health["backgroundStatus"] == "ready"
        assert health["businessStatus"] == "starting"
        assert (await client.get("/api/core/health")).json()[
            "startupActivation"
        ] == "pending"
        app.state.background_status = "ready"
        for _ in range(2):
            response = await client.post("/api/core/startup/activate")
            assert response.status_code == 200
            assert response.json()["startupActivation"] == "active"
        startup.close()
        assert (await client.post("/api/core/startup/activate")).status_code == 409
    assert "/api/core/startup/activate" not in app.openapi()["paths"]
