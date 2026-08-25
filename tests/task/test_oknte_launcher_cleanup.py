import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from app.core.config import Config  # noqa: F401  初始化 core，避免 services 循环导入
from app.task.OkNte import AutoProxy as oknte_module
from app.task.OkNte.AutoProxy import AutoProxyTask, _load_nte_launcher_path

System = oknte_module.System


def test_oknte_cleanup_kills_launcher_without_game_process_tree(tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    launcher_path = tmp_path / "Neverness To Everness" / "NTELauncher" / "NTEGame.exe"
    (config_dir / "LauncherTask.json").write_text(
        json.dumps({"Launcher Path": str(launcher_path)}),
        encoding="utf-8",
    )

    task = object.__new__(AutoProxyTask)
    task.oknte_process_manager = SimpleNamespace(kill=AsyncMock())
    task.script_exe_path = tmp_path / "ok-nte.exe"
    task.script_root_path = tmp_path / "ok-nte"
    task.script_config_path = config_dir
    task.script_config = SimpleNamespace(get=lambda _group, _key: "")
    track_path = task.script_root_path / "data/apps/ok-nte/python/pythonw.exe"

    async def search_pids(path):
        return {
            task.script_exe_path: [100],
            track_path: [101],
            launcher_path: [123],
        }.get(path, [])

    run_process = AsyncMock()
    with (
        patch.object(System, "search_pids", new=AsyncMock(side_effect=search_pids)),
        patch("app.services.system.ProcessRunner.run_process", new=run_process),
    ):
        asyncio.run(task._kill_oknte_process())

    assert run_process.await_args_list == [
        call("taskkill", "/F", "/T", "/PID", "100"),
        call("taskkill", "/F", "/T", "/PID", "101"),
        call("taskkill", "/F", "/PID", "123"),
    ]


def test_oknte_launcher_path_rejects_other_executables(tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "LauncherTask.json").write_text(
        json.dumps({"Launcher Path": str(tmp_path / "Other" / "NTEGame.exe")}),
        encoding="utf-8",
    )

    assert _load_nte_launcher_path(config_dir) is None


def test_oknte_launcher_path_supports_file_config(tmp_path) -> None:
    launcher_path = tmp_path / "Neverness To Everness" / "NTELauncher" / "NTEGame.exe"
    config_path = tmp_path / "LauncherTask.json"
    config_path.write_text(
        json.dumps({"Launcher Path": str(launcher_path)}),
        encoding="utf-8",
    )

    assert _load_nte_launcher_path(config_path) == launcher_path
