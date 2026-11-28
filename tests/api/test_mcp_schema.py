"""完整 MCP 输入保留递归任务信息树的校验契约。"""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import jsonschema
import pytest
from fastapi import FastAPI

import app.core.mcp as module
from app.core import Publisher


@pytest.mark.asyncio
async def test_full_application_recursive_schema_guards(monkeypatch):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    import app.api as api

    monkeypatch.setenv("AUTO_MAS_ENABLE_MCP", "1")
    monkeypatch.setattr(Publisher, "send", AsyncMock(return_value=False))
    service = module.McpService()
    app = FastAPI()
    for name in api.__all__:
        app.include_router(getattr(api, name))
    try:
        service.start(app)
        await asyncio.wait_for(asyncio.shield(service._task), timeout=10)
        assert service.status().state == "ready"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as http:
            async with streamable_http_client(
                "http://localhost/mcp", http_client=http
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = {
                        tool.name: tool for tool in (await session.list_tools()).tools
                    }
        assert set(tools) == set(module.MCP_INCLUDED_OPERATIONS)
        assert set(service._instance.operation_map) == set(tools)
        assert "get_mcp_status_api_core_mcp_status_get" not in tools
        assert "retry_mcp_api_core_mcp_retry_post" not in tools
        assert (
            "taskId"
            in tools["get_task_status_api_dispatch_task__task_id__get"].description
        )
        arguments = {
            "mode": "AutoProxy",
            "tasks": {
                "0": {
                    "uid": "queue",
                    "children": {
                        "0": {
                            "uid": "script",
                            "children": {
                                "0": {
                                    "uid": "account",
                                    "params": {"values": [[None, True, {"count": 1}]]},
                                }
                            },
                        }
                    },
                }
            },
        }
        schema = tools["add_task_api_dispatch_start_post"].inputSchema
        jsonschema.validate(instance=arguments, schema=schema)
        invalid = deepcopy(arguments)
        invalid["tasks"]["0"]["children"]["0"]["children"]["0"]["uid"] = 1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=invalid, schema=schema)
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_plugin_tools_follow_enable_and_disable_in_same_session(monkeypatch):
    from fastapi import APIRouter
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from app.plugin.calls import CallGate
    from app.plugin.http import HttpRegistry

    monkeypatch.setenv("AUTO_MAS_ENABLE_MCP", "1")
    monkeypatch.setenv("AUTO_MAS_MCP_WAIT_FOR_HOME", "0")
    monkeypatch.setattr(Publisher, "send", AsyncMock(return_value=False))
    monkeypatch.setattr(module, "MCP_INCLUDED_OPERATIONS", ("get_profile",))
    service = module.McpService()
    app = FastAPI()

    @app.get("/profile", operation_id="get_profile")
    async def get_profile() -> dict[str, bool]:
        return {"ready": True}

    router = APIRouter()

    @router.get(
        "/adapter/options",
        operation_id="get_adapter_options",
        openapi_extra={"x-auto-mas-mcp": True},
    )
    async def get_adapter_options() -> dict[str, list[str]]:
        return {"available": ["Win32"]}

    registry = HttpRegistry()
    registry.bind_app(app)
    try:
        service.start(app)
        await asyncio.wait_for(asyncio.shield(service._task), timeout=10)
        assert service.status().state == "ready"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as http:
            async with streamable_http_client(
                "http://localhost/mcp", http_client=http
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    assert {
                        tool.name for tool in (await session.list_tools()).tools
                    } == {"get_profile"}
                    registry.mount("adapter", [], router=router, gate=CallGate())
                    result = await session.call_tool("get_adapter_options")
                    assert not result.isError and "Win32" in result.content[0].text
                    assert {
                        tool.name for tool in (await session.list_tools()).tools
                    } == {
                        "get_profile",
                        "get_adapter_options",
                    }
                    registry.unmount("adapter")
                    assert {
                        tool.name for tool in (await session.list_tools()).tools
                    } == {"get_profile"}
    finally:
        await service.shutdown()
