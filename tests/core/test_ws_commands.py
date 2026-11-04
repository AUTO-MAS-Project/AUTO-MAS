"""共享 WS 命令组件保留参数校验和返回结果契约。"""

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.ws.commands import _WSCommandRegistry


class Params(BaseModel):
    count: int


class Result(BaseModel):
    code: int = 200
    count: int


@pytest.mark.asyncio
async def test_validated_params_and_model_response():
    commands = _WSCommandRegistry()

    @commands.register("test.get", params=Params)
    async def handler(params):
        return Result(count=params.count)

    assert await commands.execute("test.get", {"count": 3}) == {
        "success": True,
        "data": {"code": 200, "count": 3},
        "code": 200,
        "message": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [None, {}, {"count": "invalid"}, [1]])
async def test_invalid_params_do_not_invoke_handler(params):
    commands = _WSCommandRegistry()
    handler = AsyncMock()
    commands.register("test.get", params=Params)(handler)
    result = await commands.execute("test.get", params)
    assert result["code"] == 400
    assert result["success"] is False
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_command_and_handler_failure():
    commands = _WSCommandRegistry()
    assert (await commands.execute("missing"))["code"] == 404
    handler = AsyncMock(side_effect=RuntimeError("failed"))
    commands.register("test.fail")(handler)
    result = await commands.execute("test.fail")
    assert result["code"] == 500
    assert result["success"] is False
    handler.assert_awaited_once_with()
