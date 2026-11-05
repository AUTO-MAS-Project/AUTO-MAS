"""工具只使用调用方提供的程序目录，并保留 portable 安全要求。"""

import pytest

from app.utils import fluxdown_cli as cli


@pytest.fixture(autouse=True)
def windows_cli_names(monkeypatch):
    """仅模拟 Windows 文件布局；路径发现不运行真实二进制。"""
    monkeypatch.setattr(cli, "_FLUXDOWN_EXE_NAMES", ("fluxdown-cli.exe",))


def test_bundled_cli_requires_explicit_directory_and_portable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    bundled = tmp_path / "res" / "fluxdown-cli"
    bundled.mkdir(parents=True)
    executable = bundled / cli._FLUXDOWN_EXE_NAMES[0]
    executable.write_bytes(b"test binary")
    assert cli.fluxdown_find_cli(search_dirs=(bundled,)) is None
    (bundled / "portable").touch()
    assert cli.fluxdown_find_cli() is None
    assert cli.fluxdown_find_cli(search_dirs=(bundled,)) == executable


def test_explicit_cli_directory_does_not_require_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    executable = tmp_path / cli._FLUXDOWN_EXE_NAMES[0]
    executable.write_bytes(b"test binary")
    assert cli.fluxdown_find_cli(str(tmp_path)) == executable


def test_auto_detect_only_returns_complete_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli, "_candidate_drives", lambda: [])
    monkeypatch.setattr(cli.update_native, "FLUXDOWN_AGENT_NAME", "fluxdown-agent.exe")
    monkeypatch.setattr(cli.update_native, "FLUXDOWN_DAEMON_NAME", "fluxdownd.exe")

    directory = tmp_path / "installed"
    directory.mkdir()
    (directory / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (directory / "fluxdown-agent.exe").write_bytes(b"agent")
    (directory / "fluxdownd.exe").write_bytes(b"daemon")

    incomplete = cli.fluxdown_detect(str(directory), scan_budget=0.0)
    assert incomplete["path"] is None
    assert incomplete["candidates"]

    (directory / "fluxdown-cli.exe").write_bytes(b"cli")
    ready = cli.fluxdown_detect(str(directory), scan_budget=0.0)
    assert ready["path"] == str(directory)
    assert not ready["only_full_warning"] or ready["is_portable_cli"] is False


def test_auto_detect_rejects_empty_server_binary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli, "_candidate_drives", lambda: [])
    monkeypatch.setattr(cli.update_native, "FLUXDOWN_AGENT_NAME", "fluxdown-agent.exe")
    monkeypatch.setattr(cli.update_native, "FLUXDOWN_DAEMON_NAME", "fluxdownd.exe")

    directory = tmp_path / "installed"
    directory.mkdir()
    (directory / "fluxdown-cli.exe").write_bytes(b"cli")
    (directory / "fluxdown-agent.exe").write_bytes(b"agent")
    (directory / "fluxdownd.exe").touch()
    assert cli.fluxdown_detect(str(directory), scan_budget=0.0)["path"] is None
