"""游戏或设备未显式选择时，启动器使用对应的会话授权。"""

import asyncio
import sys
from pathlib import Path

import pytest

from app.config import ConfigCollection, config_manager
from app.core import Config, Plugin
from app.core.game_manager import _GameManager
from app.models.config import ScriptEntry, UserEntry
from app.models.config.game import GameDeviceEntry, GameEntry
from app.plugin.base.client import ClientControl
from app.plugin.base.script import ScriptTypeDecl
from app.task.client import ClientProcess
from app.task.game import GameSession, current_game_session
from app.task.user_expander import UserExpander
from app.utils import ProcessManager
from tests.support.scheduler import create_runtime_tree


class _LocalClient(ClientControl[GameEntry, GameDeviceEntry]):
    executable_path = Path(sys.executable)
    launcher_path = executable_path

    async def refresh(self):
        if not self.config.devices:
            self.config.devices.add(GameDeviceEntry)
            await self.config.devices.commit()

    def checked_process(self, uid, *, ticket):
        self.check_subscription(uid, ticket)
        return ProcessManager()

    async def open(self, device_uid, *, ticket):
        self.check_subscription(device_uid, ticket)

    close = show = hide = minimize = maximize = open
    start_process = track_process = stop_process = start_protocol = open


async def _open_test_launcher(marker: Path) -> None:
    await ClientProcess().open_launcher(
        Path(sys.executable),
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
        str(marker),
    )
    async with asyncio.timeout(5):
        while not marker.exists():
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_unbound_client_can_open_launcher(tmp_path):
    _, script, _ = await create_runtime_tree()
    session = GameSession(script, ScriptEntry.build())
    await session.select()
    token = current_game_session.set(session)
    marker = tmp_path / "launcher-started"
    try:
        await _open_test_launcher(marker)
    finally:
        current_game_session.reset(token)
        await session.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("device_count", [1, 2])
async def test_selected_client_without_explicit_device_can_open_launcher(
    monkeypatch, tmp_path, device_count
):
    games = ConfigCollection[GameEntry].build([GameEntry])
    await games.activate()
    uid = games.add(GameEntry, payload={"info": {"type": "client"}})
    await games.commit()
    game = games[uid]
    control = _GameManager.create_control(config=game, control_class=_LocalClient)
    if device_count > 1:
        for _ in range(device_count):
            game.devices.add(GameDeviceEntry)
        await game.devices.commit()
    monkeypatch.setitem(config_manager._collections, "games", games)
    config = ScriptEntry.build(payload={"game": {"game_id": str(uid)}})
    await config.activate()
    assert config.game.game_id == uid and config.game.device_id == "-"
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setattr(Config, "ScriptConfig", {str(config.uid): config})
    monkeypatch.setattr(
        Plugin,
        "script_types",
        {config.uid: ScriptTypeDecl(ScriptEntry, UserEntry, UserExpander)},
    )
    monkeypatch.setattr("app.core.GameManager", _GameManager())

    _, script, _ = await create_runtime_tree(script_id=str(config.uid))
    session = GameSession(script, config)
    token = current_game_session.set(session)
    marker = tmp_path / "launcher-started"
    try:
        if device_count > 1:
            with pytest.raises(ValueError, match="请指定要运行的设备"):
                await session.select()
            assert all(control.device_usage(uid) is None for uid in game.devices.keys())
            return
        await session.select()
        await _open_test_launcher(marker)
        device_uid = next(iter(game.devices.keys()))
        assert control.device_usage(device_uid) is not None
        ticket = session.ticket
        await session.select()
        assert session.ticket == ticket
        assert config.game.device_id == "-"
    finally:
        current_game_session.reset(token)
        await session.release()
    assert control.device_usage(device_uid) is None
