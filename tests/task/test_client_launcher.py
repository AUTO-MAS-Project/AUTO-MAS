"""未绑定设备的托管仍能拉起由专项管理的启动器。"""

import asyncio
import sys
from pathlib import Path

import pytest

from app.models.config import ScriptEntry
from app.task.client import ClientProcess
from app.task.game import GameSession, current_game_session
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
async def test_unbound_client_can_open_launcher(tmp_path):
    _, script, _ = await create_runtime_tree()
    session = GameSession(script, ScriptEntry.build())
    await session.select()
    token = current_game_session.set(session)
    marker = tmp_path / "launcher-started"
    try:
        await ClientProcess().open_launcher(
            Path(sys.executable),
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
            str(marker),
        )
        async with asyncio.timeout(5):
            while not marker.exists():
                await asyncio.sleep(0.05)
    finally:
        current_game_session.reset(token)
        await session.release()
