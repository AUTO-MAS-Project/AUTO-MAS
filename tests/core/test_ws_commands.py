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


@pytest.mark.asyncio
async def test_api_registration_and_notify_share_command_executor(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.api import queue
    from app.core import Commands
    from app.core.notify import manager
    from app.core.ws import Commands as direct

    assert Commands is direct
    get_queue = AsyncMock(return_value=([], {}))
    monkeypatch.setattr(queue.Config, "get_queue", get_queue)
    registry = SimpleNamespace(by_id={}, bind=Mock(return_value=object()))
    monkeypatch.setattr(manager, "_get_registry", lambda: registry)
    notify = manager.NotificationManager()
    notify._transport
    dependencies = registry.bind.call_args.args[0]
    result = await dependencies.command_executor("queue.get", {"queueId": "queue"})
    assert result["success"] is True
    assert result["data"]["index"] == []
    get_queue.assert_awaited_once_with("queue")
