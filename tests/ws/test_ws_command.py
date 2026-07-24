from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.api.ws_command import (
    execute_ws_command,
    get_ws_command_contracts,
    get_ws_command_registry,
    unregister_ws_command,
    ws_command,
)


class ExampleParams(BaseModel):
    name: str = Field(min_length=1)
    count: int = Field(ge=1, le=5)


class ExampleResult(BaseModel):
    code: int = 200
    message: str = "ok"
    value: int


@pytest.fixture
def registered_endpoints() -> list[str]:
    endpoints: list[str] = []
    yield endpoints
    for endpoint in endpoints:
        unregister_ws_command(endpoint)


@pytest.mark.asyncio
async def test_explicit_model_validates_and_invokes_handler(
    registered_endpoints: list[str],
) -> None:
    endpoint = "test.explicit-model"
    registered_endpoints.append(endpoint)
    received: list[ExampleParams] = []

    @ws_command(endpoint, params=ExampleParams)
    async def handler(params: ExampleParams) -> ExampleResult:
        received.append(params)
        return ExampleResult(value=params.count)

    result = await execute_ws_command(endpoint, {"name": "demo", "count": 3})

    assert received == [ExampleParams(name="demo", count=3)]
    assert result == {
        "success": True,
        "data": {"code": 200, "message": "ok", "value": 3},
        "code": 200,
        "message": "ok",
    }
    assert get_ws_command_registry()[endpoint] is handler
    assert get_ws_command_contracts()[endpoint].params_model is ExampleParams


@pytest.mark.asyncio
async def test_invalid_model_params_return_400_without_invocation(
    registered_endpoints: list[str],
) -> None:
    endpoint = "test.invalid-model"
    registered_endpoints.append(endpoint)
    called = False

    @ws_command(endpoint, params=ExampleParams)
    async def handler(params: ExampleParams) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"params": params.model_dump()}

    result = await execute_ws_command(endpoint, {"name": "", "count": 99})

    assert result["success"] is False
    assert result["code"] == 400
    assert called is False


@pytest.mark.asyncio
async def test_no_param_command_rejects_unexpected_data(
    registered_endpoints: list[str],
) -> None:
    endpoint = "test.no-params"
    registered_endpoints.append(endpoint)
    called = False

    @ws_command(endpoint)
    async def handler() -> str:
        nonlocal called
        called = True
        return "ok"

    rejected = await execute_ws_command(endpoint, {"unexpected": True})
    accepted = await execute_ws_command(endpoint, {})

    assert rejected["code"] == 400
    assert accepted == {"success": True, "data": "ok", "code": 200}
    assert called is True


@pytest.mark.asyncio
async def test_unknown_and_failed_commands_have_stable_errors(
    registered_endpoints: list[str],
) -> None:
    missing = await execute_ws_command("test.missing")
    assert missing["code"] == 404

    endpoint = "test.failure"
    registered_endpoints.append(endpoint)

    @ws_command(endpoint)
    async def handler() -> None:
        raise RuntimeError("boom")

    failed = await execute_ws_command(endpoint)
    assert failed["success"] is False
    assert failed["code"] == 500
    assert "RuntimeError: boom" in failed["message"]


def test_decorator_rejects_invalid_contracts() -> None:
    with pytest.raises(ValueError):
        ws_command("  ")
    with pytest.raises(TypeError):
        ws_command("test.bad-contract", params=str)  # type: ignore[arg-type]
