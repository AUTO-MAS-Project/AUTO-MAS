"""全部查询接口未携带请求体时按查询全部处理，避免 MCP 空参数返回 422。"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

import app.api.plan as plan_api
import app.api.queue as queue_api
import app.api.scripts.management as script_api


def _config_stub(method: str) -> MagicMock:
    stub = MagicMock()
    setattr(stub, method, AsyncMock(return_value=([], {})))
    for name in ("QueueConfig", "PlanConfig", "ScriptConfig"):
        getattr(stub, name).uid = uuid.uuid4()
    return stub


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "method", "path"),
    [
        (queue_api, "get_queue", "/api/queue/get"),
        (plan_api, "get_plan", "/api/plan/get"),
        (script_api, "get_script", "/api/scripts/get"),
    ],
)
async def test_get_all_without_body(monkeypatch, module, method, path) -> None:
    stub = _config_stub(method)
    monkeypatch.setattr(module, "Config", stub)
    app = FastAPI()
    if module is script_api:
        app.include_router(module.router, prefix="/api/scripts")
    else:
        app.include_router(module.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for kwargs in ({}, {"json": {}}):
            response = await client.post(path, **kwargs)
            assert response.status_code == 200, response.text
            assert response.json()["code"] == 200, response.text
    getattr(stub, method).assert_awaited_with(None)
