import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import update as updater
from app.services import update_fluxdown as transport
from app.utils.common import fluxdown_cli as cli


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:7890",
        "socks5://127.0.0.1:1080",
        "http://u%40ser:p%3A%2Fword@127.0.0.1:7890",
        "socks5://user:password@127.0.0.1:1080",
    ],
)
def test_proxy_roundtrip_preserves_port_and_auth(url):
    original = httpx.Proxy(url)
    result = httpx.Proxy(transport._proxy_to_str(original))
    assert result.url == original.url
    assert result.auth == original.auth


def test_direct_proxy_and_history_redaction():
    assert transport._proxy_to_str(None) is None
    record = cli.FluxdownDownloadRecord(proxy="http://u%40ser:p%3A%2Fword@[::1]:7890")
    assert record.to_dict()["proxy"] == "http://[::1]:7890"


@pytest.mark.asyncio
async def test_mas_update_passes_configured_proxy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proxy = httpx.Proxy("http://127.0.0.1:7890")
    monkeypatch.setattr(updater, "Config", SimpleNamespace(proxy=proxy))

    async def download(url, destination, **kwargs):
        assert kwargs["proxy"] is proxy
        destination.write_bytes(b"downloaded")
        return 10

    handler = updater.UpdateHandler(download=download)
    handler._publish_completed = AsyncMock()
    await handler._download_update_locked(
        job=updater._DownloadJob(
            version="v1.0.1",
            source="GitHub",
            mirror_chyan_download_url=None,
            download_url="https://example.invalid/update.zip",
            downloader="fluxdown",
        )
    )
    assert (tmp_path / "UpdatePack_v1.0.1.zip").read_bytes() == b"downloaded"
    handler._publish_completed.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [False, True])
async def test_dispatch_passes_proxy_to_both_cli_modes(tmp_path, monkeypatch, mode):
    proxy = httpx.Proxy("http://user:password@127.0.0.1:7890")
    record = cli.FluxdownDownloadRecord(status="success")
    local = AsyncMock(return_value=(42, record))
    server = AsyncMock(return_value=(42, record))
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda path: Path("fluxdown.exe"))
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda path, enabled: True)
    monkeypatch.setattr(
        cli, "fluxdown_server_task_safe_to_overwrite", lambda *a, **kw: True
    )
    monkeypatch.setattr(cli, "fluxdown_server_forget", lambda *a: None)
    monkeypatch.setattr(cli, "fluxdown_download", local)
    monkeypatch.setattr(cli, "fluxdown_server_download", server)
    assert (
        await transport.download_file(
            "https://example.invalid/update.zip",
            tmp_path / "package.zip",
            timeout=30,
            proxy=proxy,
            options=transport.FluxdownOptions("fluxdown", "GitHub", "", 8, mode),
        )
        == 42
    )
    selected = server if mode else local
    assert selected.call_args.kwargs["proxy"] == "http://user:password@127.0.0.1:7890"


@pytest.mark.asyncio
async def test_proxy_change_cannot_resume_unconfirmed_old_task(tmp_path, monkeypatch):
    executable = tmp_path / "fluxdown.exe"
    target = tmp_path / "file.zip"
    key = cli._map_key("https://example.invalid/file.zip", target)
    mapping = {key: {"task_id": "old", "proxy_hash": cli._proxy_hash(None)}}
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda path: SimpleNamespace(gateway_port=12345, token="test"),
    )
    monkeypatch.setattr(cli, "_load_task_map", lambda path: mapping)
    calls = []

    def command(executable, env, args, timeout=30):
        calls.append(args)
        return 124, "timeout"

    monkeypatch.setattr(cli, "_run_cli", command)
    with pytest.raises(RuntimeError, match="旧任务未确认停止"):
        await cli.fluxdown_server_download(
            "https://example.invalid/file.zip",
            target,
            cli_exe=executable,
            proxy="http://127.0.0.1:7890",
            timeout=1,
        )
    assert calls == [["pause", "old"]]
    assert mapping[key]["task_id"] == "old"


def test_proxy_mapping_keeps_no_plaintext_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    executable = tmp_path / "fluxdown.exe"
    cli._map_put(
        executable,
        "key",
        "id",
        "https://example.invalid",
        tmp_path / "data",
        "http://user:password@localhost:7890",
    )
    text = cli._server_map_path(executable).read_text(encoding="utf-8")
    assert "password" not in text
    assert json.loads(text)["key"]["proxy_hash"] == cli._proxy_hash(
        "http://user:password@localhost:7890"
    )


def test_shutdown_uses_process_handles_instead_of_taskkill(monkeypatch):
    from unittest.mock import Mock

    child = Mock(pid=2)
    parent = Mock(pid=1)
    parent.children.return_value = [child]
    wait = Mock(return_value=([parent, child], []))
    monkeypatch.setattr(cli.psutil, "Process", lambda pid: parent)
    monkeypatch.setattr(cli.psutil, "wait_procs", wait)
    cli._kill_pid(1)
    parent.kill.assert_called_once()
    child.kill.assert_called_once()
    wait.assert_called_once_with([parent, child], timeout=5)
