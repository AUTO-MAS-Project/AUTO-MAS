"""工具只使用调用方提供的程序目录，并保留 portable 安全要求。"""

import json
from pathlib import Path
from types import SimpleNamespace

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
    assert incomplete["candidates"][0]["has_server"]
    assert not incomplete["candidates"][0]["has_cli"]
    assert incomplete["candidates"][0]["missing"] == "CLI"

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("legacy_request", "output_change"),
    [
        (False, "original"),
        (False, "toggle_dot"),
        (False, "different_name"),
        (False, "different_directory"),
        (True, "original"),
        (True, "toggle_dot"),
    ],
)
async def test_server_download_handoff_after_filename_sanitization(
    tmp_path, monkeypatch, legacy_request, output_change
):
    """新旧临时名均兼容前导点差异，但拒绝其他文件或目录。"""
    monkeypatch.chdir(tmp_path)
    executable = tmp_path / "fluxdown-cli.exe"
    destination = tmp_path / "更新" / "package.zip"
    destination.parent.mkdir()
    destination.write_bytes(b"previous package")
    payload = b"downloaded package"
    url = "https://example.test/package.zip"
    task_id = "01a1b282-604d-7049-a9d0-5de2ec85c99b"
    output = None

    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _: SimpleNamespace(gateway_port=27896, token="test-token"),
    )

    def write_output(request_path):
        name = request_path.name
        directory = request_path.parent
        if output_change == "toggle_dot":
            name = name[1:] if name.startswith(".") else f".{name}"
        elif output_change == "different_name":
            name = "unrelated.zip"
        elif output_change == "different_directory":
            directory = tmp_path / "other"
            directory.mkdir()
        result = directory / name
        result.write_bytes(payload)
        return result

    if legacy_request:
        request_path = destination.with_name(f".mas-fluxdown-{'a' * 32}.zip")
        cli._map_put(
            executable,
            cli._map_key(url, destination),
            task_id,
            url,
            destination,
            None,
            request_path,
        )
        output = write_output(request_path)

    def run_cli(cli_exe, env, args, timeout):
        nonlocal output
        if args[0] == "add":
            directory = Path(args[args.index("-d") + 1])
            output = write_output(directory / args[args.index("-o") + 1])
            return 0, json.dumps({"taskId": task_id})
        if args[0] == "resume":
            return 0, ""
        assert args[0] == "status"
        assert output is not None
        return 0, json.dumps(
            {
                "taskId": task_id,
                "status": 3,
                "saveDir": str(output.parent),
                "fileName": output.name,
                "totalBytes": len(payload),
                "downloadedBytes": len(payload),
            }
        )

    monkeypatch.setattr(cli, "_run_cli", run_cli)
    download = cli.fluxdown_server_download(url, destination, cli_exe=executable)
    if output_change in ("different_name", "different_directory"):
        with pytest.raises(RuntimeError):
            await download
        assert destination.read_bytes() == b"previous package"
        assert output.read_bytes() == payload
    else:
        size, record = await download
        assert size == len(payload)
        assert record.status == "success"
        assert destination.read_bytes() == payload
        assert not output.exists()
