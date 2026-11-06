from pathlib import Path
from types import SimpleNamespace

from app.task.OkNte.AutoProxy import AutoProxyTask


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
