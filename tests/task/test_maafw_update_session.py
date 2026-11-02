"""MFW 手动与自动更新共用会话，必须经过公共调度入口。"""

from unittest.mock import AsyncMock

import pytest

from app.task.MaaFW.tools.embedded import update_session


@pytest.mark.asyncio
async def test_session_dispatches_complete_operation_through_shared_entry(monkeypatch):
    result = object()
    core_call = AsyncMock()
    update = AsyncMock(return_value=result)
    requests = []
    original = update_session.run_script_update

    async def dispatch(request, operation, *args, **kwargs):
        requests.append(request)
        update.assert_not_awaited()
        return await original(request, operation, *args, **kwargs)

    monkeypatch.setattr(update_session, "run_script_update", dispatch)
    monkeypatch.setattr(update_session.view_update, "run_view_update", update)
    session = update_session.UpdateSession(
        "script",
        channel="stable",
        members=[],
        send_log=lambda _: None,
        reservation_held=False,
    )
    assert await session.run(core_call) is result
    assert len(requests) == 1
    assert requests[0].script_id == "script"
    assert requests[0].script_type == "MaaFW"
    assert update.call_args.kwargs["core_call"] is core_call
    assert update.call_args.kwargs["reservation_held"] is False
