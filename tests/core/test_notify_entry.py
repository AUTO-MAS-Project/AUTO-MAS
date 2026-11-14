"""断连期间的系统通知在连接恢复后继续交付。"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_global_system_notice_survives_disconnection_and_flushes(monkeypatch):
    from app.core import Config, Notify, Publisher

    monkeypatch.setattr(Config, "startup_notices", [])
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(Publisher, "send", send)
    await Notify.push_system_notice(
        level="warning",
        title="初始化提示",
        lines=["待连接"],
        title_key="core.setting.func.scheduledWakeupFailure",
        line_keys=["core.setting.func.scheduledWakeupFailureTip"],
    )
    assert len(Config.startup_notices) == 1
    send.return_value = True
    await Notify.flush_startup_notices()
    assert Config.startup_notices == []
    data = send.await_args.kwargs["data"]
    assert data.titleKey == "core.setting.func.scheduledWakeupFailure"
    assert data.lineKeys == ["core.setting.func.scheduledWakeupFailureTip"]
    await Notify.flush_startup_notices()
    assert send.await_count == 2
