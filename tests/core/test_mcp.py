"""可选 MCP 的生命周期与外部工具契约，不需要账号、网络或游戏。"""

import asyncio
import json
import threading
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import jsonschema
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel

import app.core.mcp as module
from app.core import Publisher


class QueryIn(BaseModel):
    scriptId: str | None = None


class RecursiveNodeIn(BaseModel):
    value: int
    branch: "RecursiveBranchIn | None" = None


class RecursiveBranchIn(BaseModel):
    nodes: list[RecursiveNodeIn]


RecursiveNodeIn.model_rebuild()


@pytest_asyncio.fixture
async def service(monkeypatch):
    monkeypatch.setenv("AUTO_MAS_ENABLE_MCP", "1")
    monkeypatch.setattr(module, "MCP_INCLUDED_OPERATIONS", ("read",))
    monkeypatch.setattr(Publisher, "send", AsyncMock(return_value=False))
    instance = module.McpService()
    yield instance
    await instance.shutdown()


@pytest.fixture
def app():
    application = FastAPI()

    @application.get("/read", operation_id="read")
    async def read():
        return {"value": "ok"}

    @application.get("/private", operation_id="private")
    async def private():
        return {"secret": True}

    return application


async def wait_loaded(service):
    await asyncio.wait_for(asyncio.shield(service._task), timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("paint_first", [False, True])
async def test_desktop_waits_for_both_business_and_home_paint(
    service, app, monkeypatch, paint_first
):
    monkeypatch.setenv("AUTO_MAS_MCP_WAIT_FOR_HOME", "1")
    desktop = module.McpService()
    try:
        if paint_first:
            desktop.notify_home_painted()
            assert desktop._task is None
        started = desktop.start(app)
        assert started is paint_first
        if not paint_first:
            assert desktop.status().state == "pending"
            assert desktop.status().startedAt is None
            assert desktop._task is None
        desktop.notify_home_painted()
        task = desktop._task
        desktop.notify_home_painted()
        assert desktop._task is task
        await wait_loaded(desktop)
        assert desktop.status().state == "ready"
        assert len([route for route in app.routes if route.path == "/mcp"]) == 1
    finally:
        await desktop.shutdown()


@pytest.mark.asyncio
async def test_shutdown_while_waiting_for_home_does_not_start_mcp(
    service, app, monkeypatch
):
    monkeypatch.setenv("AUTO_MAS_MCP_WAIT_FOR_HOME", "1")
    desktop = module.McpService()
    assert not desktop.start(app)
    await desktop.shutdown()
    desktop.notify_home_painted()
    assert not desktop.start(app)
    assert desktop._task is None
    assert desktop.status().state == "cancelled"


@pytest.mark.asyncio
async def test_real_transport_tools_call_stages_and_cleanup(service, app):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    assert service.start(app)
    assert not service.start(app)
    await wait_loaded(service)
    assert service.status().state == "ready"
    assert service.status().toolCount == 1
    assert not service.retry()
    assert not service.start(app)
    assert len([route for route in app.routes if route.path == "/mcp"]) == 1
    messages = [call.kwargs["data"] for call in Publisher.send.await_args_list]
    assert [status.stage for status in messages[:-1]] == [
        "importing",
        "building",
        "validating",
        "mounting",
    ]
    assert messages[-1].state == "ready"
    assert all(a.revision < b.revision for a, b in zip(messages, messages[1:]))
    client = service._client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as http:
        async with streamable_http_client(
            "http://localhost/mcp", http_client=http
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                assert [tool.name for tool in (await session.list_tools()).tools] == [
                    "read"
                ]
                result = await session.call_tool("read", {})
                assert not result.isError
                assert "ok" in result.content[0].text
        transport = service._instance._http_transport
        await service.shutdown()
        assert transport._manager_task.done()
        assert (await http.get("/mcp")).status_code == 404
        assert (await http.get("/private")).status_code == 200
    assert client.is_closed
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments", [{}, {"scriptId": None}, {"scriptId": "script-1"}]
)
async def test_optional_query_body_preserves_omission_and_null(
    service, app, monkeypatch, arguments
):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    @app.post("/query", operation_id="query")
    async def query(body: QueryIn):
        return body.model_dump()

    monkeypatch.setattr(module, "MCP_INCLUDED_OPERATIONS", ("query",))
    service.start(app)
    await wait_loaded(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as http:
        expired = await http.get("/mcp", headers={"Mcp-Session-Id": "expired"})
        assert expired.status_code == 404
        async with streamable_http_client(
            "http://localhost/mcp", http_client=http
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool("query", arguments)
                assert not result.isError, result.content
                assert json.loads(result.content[0].text) == {
                    "scriptId": arguments.get("scriptId")
                }


@pytest.mark.asyncio
async def test_recursive_tool_parameters_keep_validation(service, app, monkeypatch):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    @app.post("/recursive", operation_id="recursive")
    async def recursive(body: RecursiveBranchIn):
        return body.model_dump(exclude_unset=True)

    monkeypatch.setattr(module, "MCP_INCLUDED_OPERATIONS", ("recursive",))
    service.start(app)
    await wait_loaded(service)
    arguments = {
        "nodes": [{"value": 1, "branch": {"nodes": [{"value": 2, "branch": None}]}}]
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as http:
        async with streamable_http_client(
            "http://localhost/mcp", http_client=http
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                await session.list_tools()
                result = await session.call_tool("recursive", arguments)
                assert not result.isError
                assert json.loads(result.content[0].text) == arguments
                invalid = deepcopy(arguments)
                invalid["nodes"][0]["branch"]["nodes"][0]["value"] = "invalid"
                result = await session.call_tool("recursive", invalid)
                assert result.isError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,error",
    [
        ("importing", "import_failed"),
        ("building", "build_failed"),
        ("validating", "validation_failed"),
        ("mounting", "mount_failed"),
    ],
)
async def test_failure_is_safe_and_retry_has_new_run(
    service, app, monkeypatch, stage, error
):
    def fail(*args, **kwargs):
        raise RuntimeError("secret=http://user:password@localhost")

    target = {
        "importing": (module.importlib, "import_module"),
        "building": (module, "_build_mcp"),
        "validating": (module, "_validate_mcp"),
    }
    if stage == "mounting":
        from fastapi_mcp import FastApiMCP

        original = FastApiMCP.mount_http

        def partial(instance, **kwargs):
            original(instance, **kwargs)
            fail()

        owner, name, replacement = FastApiMCP, "mount_http", partial
    else:
        owner, name = target[stage]
        replacement = fail
    with monkeypatch.context() as patch:
        patch.setattr(owner, name, replacement)
        assert service.start(app)
        await wait_loaded(service)
    failed = service.status()
    assert failed.state == "failed"
    assert failed.stage == stage
    assert failed.error == error
    assert "password" not in failed.model_dump_json()
    assert not [route for route in app.routes if route.path == "/mcp"]
    assert service._client is None
    assert service.retry()
    assert not service.retry()
    await wait_loaded(service)
    assert service.status().state == "ready"
    assert service.status().runId != failed.runId
    assert service.status().revision > failed.revision
    assert len([route for route in app.routes if route.path == "/mcp"]) == 1


@pytest.mark.asyncio
async def test_cancel_waits_for_thread_and_cannot_mount_late(service, app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original = module._build_mcp

    def blocked(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(module, "_build_mcp", blocked)
    service.start(app)
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        service._task.cancel()
        await asyncio.sleep(0)
        shutdown = asyncio.create_task(service.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()
        assert not service.retry()
        assert not service.start(app)
    finally:
        release.set()
    await shutdown
    assert service.status().state == "cancelled"
    assert service._client is None
    assert not [route for route in app.routes if route.path == "/mcp"]
    assert not service.retry()
    await service.shutdown()


@pytest.mark.asyncio
async def test_disabled_has_no_import_task_or_mount(app, monkeypatch):
    monkeypatch.setenv("AUTO_MAS_ENABLE_MCP", "0")
    service = module.McpService()
    monkeypatch.setattr(
        module.importlib, "import_module", lambda *args: pytest.fail("heavy import")
    )
    assert service.status().state == "skipped"
    assert not service.start(app)
    assert service._task is None
    assert not service.retry()
    await service.shutdown()
    assert not service.status().enabled
    assert not [route for route in app.routes if route.path == "/mcp"]


@pytest.mark.asyncio
async def test_ws_error_does_not_fail_mcp(service, app, monkeypatch):
    monkeypatch.setattr(
        Publisher, "send", AsyncMock(side_effect=RuntimeError("disconnected"))
    )
    service.start(app)
    await wait_loaded(service)
    assert service.status().state == "ready"


@pytest.mark.asyncio
async def test_full_application_whitelist_and_schema_guards(monkeypatch):
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
        await wait_loaded(service)
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
