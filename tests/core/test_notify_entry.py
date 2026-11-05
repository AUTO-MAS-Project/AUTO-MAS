"""core.Notify 是进程共享的管理器，导入不装配渠道或连接。"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_global_system_notice_survives_disconnection_and_flushes(monkeypatch):
    from app.core import Config, Notify, Publisher

    monkeypatch.setattr(Config, "startup_notices", [])
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(Publisher, "send", send)
    await Notify.push_system_notice(
        level="warning", title="初始化提示", lines=["待连接"]
    )
    assert len(Config.startup_notices) == 1
    send.return_value = True
    await Notify.flush_startup_notices()
    assert Config.startup_notices == []
    await Notify.flush_startup_notices()
    assert send.await_count == 2
