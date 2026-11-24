"""取消任务后，启动器交互必须先退出再交还桌面。"""

import asyncio
from pathlib import Path
from threading import Event

import pytest

from app.task.OkNte.tools import launcher_start


@pytest.mark.asyncio
async def test_cancellation_waits_for_launcher_interaction_to_exit(monkeypatch):
    started = Event()
    stopped = Event()

    def run_launcher(_launcher, *, stop_event=None, **_):
        started.set()
        if stop_event is not None and stop_event.wait(2):
            stopped.set()
        return True

    monkeypatch.setattr(launcher_start, "start_game_via_launcher", run_launcher)
    task = asyncio.create_task(
        launcher_start.async_start_game_via_launcher(Path("launcher.exe"))
    )
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
