from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

import app.api.core as api
from app.core.mcp import McpService


@pytest.mark.asyncio
async def test_home_painted_route_notifies_service(monkeypatch):
    service = Mock(spec=McpService)
    monkeypatch.setattr(api, "MCP", service)
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/core/mcp/home-painted")
        assert response.status_code == 200
        assert response.json()["code"] == 200
        service.notify_home_painted.assert_called_once_with()


@pytest.mark.asyncio
async def test_snapshot_and_invalid_retry_are_lightweight(monkeypatch):
    service = McpService()
    monkeypatch.setattr(api, "MCP", service)
    app = FastAPI()
    app.include_router(api.router)
    app.state.background_status = "ready"
    app.state.background_error = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        snapshot = (await client.get("/api/core/mcp/status")).json()
        assert snapshot["data"] == service.status().model_dump(mode="json")
        retry = (await client.post("/api/core/mcp/retry")).json()
        assert retry["code"] == 409
        assert not retry["accepted"]
        assert service._task is None
        service._status.state = "failed"
        service._status.error = "build_failed"
        health = (await client.get("/api/core/health")).json()
        assert health["ready"]
        assert health["backgroundStatus"] == "ready"
        assert health["backgroundError"] is None
        assert health["protocol"] == 1
