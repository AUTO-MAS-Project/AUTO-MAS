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
async def test_command_dispatch_validates_inputs_and_returns_stable_results():
    commands = _WSCommandRegistry()

    handler = AsyncMock(side_effect=lambda params: Result(count=params.count))
    commands.register("test.get", params=Params)(handler)

    for params in (None, {}, {"count": "invalid"}, [1]):
        result = await commands.execute("test.get", params)
        assert result["code"] == 400
        assert result["success"] is False
    handler.assert_not_awaited()
    assert await commands.execute("test.get", {"count": 3}) == {
        "success": True,
        "data": {"code": 200, "count": 3},
        "code": 200,
        "message": None,
    }
    handler.assert_awaited_once_with(Params(count=3))
    assert (await commands.execute("missing"))["code"] == 404
    handler = AsyncMock(side_effect=RuntimeError("failed"))
    commands.register("test.fail")(handler)
    result = await commands.execute("test.fail")
    assert result["code"] == 500
    assert result["success"] is False
    handler.assert_awaited_once_with()
