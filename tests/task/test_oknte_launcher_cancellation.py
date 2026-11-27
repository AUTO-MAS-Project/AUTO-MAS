"""取消任务后，启动器交互必须先退出再交还桌面。"""

import asyncio
import json
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.task.client import ClientProcess
from app.task.game import GameSession, current_game_session
from app.task.OkNte.AutoProxy import AutoProxyTask
from app.task.OkNte.tools import launcher_start
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


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


@pytest.mark.asyncio
async def test_native_launcher_path_does_not_start_game_without_bound_client(tmp_path):
    launcher_path = tmp_path / "Neverness To Everness/NTELauncher/NTEGame.exe"
    launcher_path.parent.mkdir(parents=True)
    launcher_path.touch()
    (tmp_path / "LauncherTask.json").write_text(
        json.dumps({"Launcher Path": str(launcher_path)}), encoding="utf-8"
    )
    config = await activate_config(
        OkNteConfig(Game={"Enabled": True, "LaunchBeforeTask": True})
    )
    account = await activate_config(OkNteUserConfig())
    user_id = uuid4()
    _, script, _ = await create_runtime_tree(user_id=str(user_id))
    session = GameSession(script, config)
    await session.select()
    token = current_game_session.set(session)
    try:
        proxy = AutoProxyTask(script, config, {user_id: account}, ClientProcess())
        proxy.script_config_path = tmp_path
        with pytest.raises(RuntimeError, match="请绑定异环客户端"):
            await proxy._mas_launch_game_before_task()
    finally:
        current_game_session.reset(token)
        await session.release()
