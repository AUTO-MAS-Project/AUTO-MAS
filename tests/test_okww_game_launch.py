import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.task.Okww.AutoProxy import (
    AutoProxyTask,
    _WUWA_CLIENT_PROCESS,
)
from app.utils import ProcessManager

okww_auto_proxy = importlib.import_module("app.task.Okww.AutoProxy")


class ConfigStub:
    def __init__(self, values: dict[tuple[str, str], object]) -> None:
        self.values = values

    def get(self, section: str, key: str) -> object:
        return self.values[(section, key)]


class ProcessManagerStub(ProcessManager):
    def __init__(self) -> None:
        self.target_process = None
        self.opened: tuple[Path, tuple[str, ...]] | None = None
        self.searched_process_name: str | None = None
        self.searched_process_exe: str | None = None
        self.events: list[str] = []

    async def open_process(self, program: Path, *args: str) -> None:
        self.opened = (program, args)
        self.events.append("open-game")

    async def search_process(self, target, deadline) -> None:
        self.searched_process_name = target.name
        self.searched_process_exe = target.exe
        self.events.append("track-game")


def test_okww_launches_decoded_game_process_directly(monkeypatch) -> None:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.game_process_path = Path(
        "D:/Wuthering Waves/Client/Binaries/Win64/Client-Win64-Shipping.exe"
    )
    task.game_manager = ProcessManagerStub()
    task.script_config = ConfigStub(
        {
            ("Game", "Arguments"): "-dx11",
            ("Game", "WaitTime"): 60,
        }
    )
    task.script_info = SimpleNamespace(log="")

    async def sleep(seconds: float) -> None:
        if seconds:
            task.game_manager.events.append(f"wait-{int(seconds)}-seconds")

    monkeypatch.setattr(okww_auto_proxy, "is_process_running", lambda name: False)
    monkeypatch.setattr(okww_auto_proxy.asyncio, "sleep", sleep)

    asyncio.run(task._mas_launch_game_before_task())

    assert task.game_manager.opened == (task.game_process_path, ("-dx11",))
    assert task.game_manager.events == ["open-game", "wait-60-seconds"]
    assert task.script_info.log == "等待游戏启动（60 秒）..."


def test_okww_tracks_running_game_by_decoded_path(monkeypatch) -> None:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.game_process_path = Path(
        "D:/Wuthering Waves/Client/Binaries/Win64/Client-Win64-Shipping.exe"
    )
    task.game_manager = ProcessManagerStub()

    monkeypatch.setattr(okww_auto_proxy, "is_process_running", lambda name: True)

    asyncio.run(task._mas_launch_game_before_task())

    assert task.game_manager.opened is None
    assert task.game_manager.searched_process_name == _WUWA_CLIENT_PROCESS
    assert task.game_manager.searched_process_exe == str(task.game_process_path)


def test_okww_force_kill_uses_resolved_game_process_path(monkeypatch) -> None:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.game_manager = None
    task.game_process_path = Path(
        "D:/Wuthering Waves/Client/Binaries/Win64/Client-Win64-Shipping.exe"
    )
    kill_process = AsyncMock()
    monkeypatch.setattr(okww_auto_proxy.System, "kill_process", kill_process)

    asyncio.run(task._kill_game_process())

    kill_process.assert_awaited_once_with(task.game_process_path)
