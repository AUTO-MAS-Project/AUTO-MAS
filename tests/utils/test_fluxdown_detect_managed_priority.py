"""FluxDown 自动检测优先选择 MAS 托管目录的回归测试。"""

from pathlib import Path

from app.utils.common import fluxdown_cli


def _complete(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in (
        fluxdown_cli._FLUXDOWN_EXE_NAMES[0],
        fluxdown_cli.update_native.FLUXDOWN_AGENT_NAME,
        fluxdown_cli.update_native.FLUXDOWN_DAEMON_NAME,
    ):
        (directory / name).write_bytes(b"exe")


def test_managed_fluxdown_preferred_over_configured_path(tmp_path, monkeypatch):
    managed = tmp_path / "mas" / "data" / "fluxdown" / "bin"
    external = tmp_path / "external" / "fluxdown"
    _complete(managed)
    _complete(external)
    monkeypatch.setattr(fluxdown_cli, "_candidate_drives", lambda: [])

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("完整的 MAS 托管目录不应触发全盘扫描")

    monkeypatch.setattr(fluxdown_cli, "_scan_drives", unexpected_scan)
    for _ in range(3):
        result = fluxdown_cli.fluxdown_detect(
            str(external), managed_dir=managed
        )
        assert result["path"] == str(managed)
        assert result["scanned_drives"] == []


def test_incomplete_managed_fluxdown_falls_back(tmp_path, monkeypatch):
    managed = tmp_path / "mas" / "data" / "fluxdown" / "bin"
    external = tmp_path / "external" / "fluxdown"
    managed.mkdir(parents=True)
    (managed / fluxdown_cli._FLUXDOWN_EXE_NAMES[0]).write_bytes(b"exe")
    _complete(external)
    monkeypatch.setattr(fluxdown_cli, "_candidate_drives", lambda: [])
    monkeypatch.setattr(fluxdown_cli, "_scan_drives", lambda *args, **kwargs: [])
    result = fluxdown_cli.fluxdown_detect(
        str(external), managed_dir=managed
    )
    assert result["path"] == str(external)
