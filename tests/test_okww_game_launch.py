import asyncio
import importlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.task.Okww.AutoProxy import AutoProxyTask, _WUWA_CLIENT_PROCESS
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


def make_log_task(*, is_running: bool) -> AutoProxyTask:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_log = SimpleNamespace(content=[], status="")
    task.cur_user_item = SimpleNamespace(status="运行")
    task.script_info = SimpleNamespace(log="")
    task.script_config = ConfigStub({("Run", "RunTimeLimit"): 60})
    task.okww_process_manager = SimpleNamespace(
        is_running=AsyncMock(return_value=is_running)
    )
    task.wait_event = asyncio.Event()
    return task


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


def test_okww_window_closed_log_marks_success_before_process_exit() -> None:
    task = make_log_task(is_running=True)

    asyncio.run(
        task.check_log(
            ["MainWindow:Window closed exit_event.is_set\n"], datetime.now()
        )
    )

    assert task.cur_user_log.status == "Success!"
    assert task.cur_user_item.status == "完成"
    assert task.wait_event.is_set()


def test_okww_process_exit_without_window_closed_log_is_error() -> None:
    task = make_log_task(is_running=False)

    asyncio.run(task.check_log(["TaskExecutor:Executor destroy\n"], datetime.now()))

    assert task.cur_user_log.status == "OK-WW 在完成任务前退出"
    assert task.cur_user_item.status == "异常"
    assert task.wait_event.is_set()
