import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.task.OkNte.AutoProxy import AutoProxyTask, System
from app.task.OkNte.tools import launcher_start
from app.task.OkNte.tools.launcher_start import _action_items, _find_text


def test_launcher_action_area_excludes_update_news():
    items = [
        ("1.4版本『祷歌为谁而诵』更新", (171, 914, 334, 26)),
        ("安装游戏", (1643, 940, 120, 30)),
    ]
    assert _find_text(items, ("更新",)) is not None  # 修复前会把新闻当按钮
    assert _find_text(_action_items(items), ("更新",)) is None
    assert _find_text(_action_items(items), ("安装游戏",)) == (1643, 940, 120, 30)
    assert _find_text(
        _action_items([("开始更新", (1642, 940, 121, 31))]), ("更新",)
    ) == (
        1642,
        940,
        121,
        31,
    )


def test_global_launcher_from_legacy_client(tmp_path: Path):
    root = tmp_path / "Neverness To Everness"
    client = root / "Client" / "HTGame.exe"
    client.parent.mkdir(parents=True)
    client.touch()
    launcher = root / "NTEGlobalLauncher.exe"
    launcher.touch()
    proxy = SimpleNamespace(
        script_config=SimpleNamespace(Game=SimpleNamespace(Path=client)),
        script_config_path=tmp_path,
    )
    assert AutoProxyTask._resolve_launcher_path(proxy) == launcher


def test_manually_selected_launcher_is_used(tmp_path: Path):
    launcher = tmp_path / "CustomLauncher.exe"
    launcher.touch()
    proxy = SimpleNamespace(
        script_config=SimpleNamespace(Game=SimpleNamespace(Path=launcher)),
        script_config_path=tmp_path,
    )
    assert AutoProxyTask._resolve_launcher_path(proxy) == launcher


@pytest.mark.parametrize("nested", [False, True])
def test_global_launcher_window_path_for_installation(tmp_path: Path, nested: bool):
    global_dir = tmp_path / "NTEGlobal"
    launcher = (global_dir if nested else tmp_path) / "NTEGlobalLauncher.exe"
    assert launcher_start.launcher_process_paths(launcher) == (
        launcher,
        global_dir / "NTEGlobalGame.exe",
    )


@pytest.mark.skipif(
    not launcher_start.IS_WINDOWS, reason="启动器窗口枚举仅支持 Windows"
)
def test_launcher_window_matches_selected_installation(tmp_path: Path, monkeypatch):
    selected = tmp_path / "selected" / "NTEGlobalLauncher.exe"
    selected_window = selected.parent / "NTEGlobal" / "NTEGlobalGame.exe"
    other_window = tmp_path / "other" / "NTEGlobal" / "NTEGlobalGame.exe"
    paths = {1: other_window, 2: selected_window}
    monkeypatch.setattr(
        launcher_start.win32gui,
        "EnumWindows",
        lambda cb, _: [cb(i, None) for i in paths],
    )
    monkeypatch.setattr(launcher_start.win32gui, "IsWindowVisible", lambda _: True)
    monkeypatch.setattr(
        launcher_start.win32process, "GetWindowThreadProcessId", lambda hwnd: (0, hwnd)
    )
    monkeypatch.setattr(
        launcher_start, "_window_area", lambda hwnd: 100 if hwnd == 1 else 1
    )
    monkeypatch.setattr(
        launcher_start.psutil,
        "Process",
        lambda pid: SimpleNamespace(
            name=lambda: "nteglobalgame.exe", exe=lambda: str(paths[pid])
        ),
    )

    assert launcher_start._wait_launcher_hwnd(selected, timeout=1) == 2


@pytest.mark.parametrize("has_mas_launcher", [True, False])
@pytest.mark.asyncio
async def test_cleanup_uses_mas_launcher_not_script_config(
    tmp_path: Path, monkeypatch, has_mas_launcher: bool
):
    launcher = tmp_path / "NTEGlobalLauncher.exe"
    launcher.touch()
    window_process = tmp_path / "NTEGlobal" / "NTEGlobalGame.exe"
    window_process.parent.mkdir()
    window_process.touch()
    other = tmp_path / "Neverness To Everness" / "NTELauncher" / "NTEGame.exe"
    other.parent.mkdir(parents=True)
    other.touch()
    script_config = tmp_path / "LauncherTask.json"
    script_config.write_text(
        json.dumps({"Launcher Path": str(other)}), encoding="utf-8"
    )
    proxy = object.__new__(AutoProxyTask)
    proxy.script_config = SimpleNamespace(
        Game=SimpleNamespace(
            Enabled=True, Type="Client", Path=launcher if has_mas_launcher else None
        )
    )
    proxy.script_config_path = script_config
    proxy.oknte_process_manager = SimpleNamespace(
        kill=AsyncMock(), cleanup_executables=Mock(return_value=[])
    )
    kill_process = AsyncMock(return_value=True)
    monkeypatch.setattr(System, "kill_process", kill_process)

    await proxy.kill_managed_process(kill_game=False)

    if has_mas_launcher:
        assert kill_process.await_args_list == [
            call(launcher, kill_tree=False),
            call(window_process, kill_tree=True),
        ]
    else:
        kill_process.assert_not_awaited()
