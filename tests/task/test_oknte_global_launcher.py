import json
from pathlib import Path
from types import SimpleNamespace

from app.task.OkNte.AutoProxy import AutoProxyTask, _load_nte_launcher_path


def test_global_launcher_from_saved_config_and_legacy_client(tmp_path: Path):
    root = tmp_path / "Neverness To Everness"
    client = root / "Client" / "HTGame.exe"
    client.parent.mkdir(parents=True)
    client.touch()
    launcher = root / "NTEGlobalLauncher.exe"
    launcher.touch()
    config = tmp_path / "LauncherTask.json"
    config.write_text(json.dumps({"Launcher Path": str(launcher)}), encoding="utf-8")

    assert _load_nte_launcher_path(config) == launcher
    proxy = SimpleNamespace(
        script_config=SimpleNamespace(Game=SimpleNamespace(Path=client)),
        script_config_path=config,
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
