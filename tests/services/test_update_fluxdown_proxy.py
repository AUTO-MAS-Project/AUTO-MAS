import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import update as updater
from app.services.common.update import fluxdown as transport
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
def test_cli_proxy_endpoint_preserves_port_without_auth(url):
    original = httpx.Proxy(url)
    result = httpx.Proxy(transport._proxy_to_str(original))
    assert result.url == original.url
    assert result.auth is None


def test_direct_proxy_and_history_redaction():
    assert transport._proxy_to_str(None) is None
    record = cli.FluxdownDownloadRecord(proxy="http://u%40ser:p%3A%2Fword@[::1]:7890")
    assert record.to_dict()["proxy"] == "http://[::1]:7890"


@pytest.mark.asyncio
async def test_mas_update_passes_configured_proxy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proxy = httpx.Proxy("http://127.0.0.1:7890")
    monkeypatch.setattr(
        updater, "Config", SimpleNamespace(proxy=proxy, work_path=tmp_path)
    )

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
    proxy = httpx.Proxy("http://127.0.0.1:7890")
    record = cli.FluxdownDownloadRecord(status="success")
    local = AsyncMock(return_value=(42, record))
    server = AsyncMock(return_value=(42, record))
    monkeypatch.setattr(
        cli, "fluxdown_find_cli", lambda path, **kwargs: Path("fluxdown.exe")
    )
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
    assert selected.call_args.kwargs["proxy"] == "http://127.0.0.1:7890"


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


@pytest.mark.asyncio
async def test_authenticated_proxy_uses_httpx_without_cli_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    proxy = httpx.Proxy("http://user:password@127.0.0.1:7890")
    builtin = AsyncMock(return_value=42)
    server, local = AsyncMock(), AsyncMock()
    monkeypatch.setattr(transport, "_httpx_download", builtin)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda path, **kwargs: None)
    monkeypatch.setattr(cli, "fluxdown_server_download", server)
    monkeypatch.setattr(cli, "fluxdown_download", local)
    assert (
        await transport.download_file(
            "https://example.invalid",
            tmp_path / "package",
            timeout=30,
            proxy=proxy,
            options=transport.FluxdownOptions("fluxdown", "GitHub", "", 8, True),
        )
        == 42
    )
    assert builtin.call_args.kwargs["proxy"] is proxy
    server.assert_not_called()
    local.assert_not_called()


def test_failures_preserve_proxy_and_accumulate(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    exe, target = tmp_path / "fluxdown.exe", tmp_path / "data"
    url = "https://example.invalid"
    key = cli._map_key(url, target)
    cli._map_put(exe, key, "task", url, target, "http://localhost:7890")
    assert cli.fluxdown_server_mark_failure(exe, url, target) == 1
    assert cli.fluxdown_server_mark_failure(exe, url, target) == 2
    assert cli._load_task_map(exe)[key]["proxy_hash"] == cli._proxy_hash(
        "http://localhost:7890"
    )
    assert cli._proxy_hash("http://user:weak@localhost:7890") == cli._proxy_hash(
        "http://localhost:7890"
    )


def test_private_cli_failure_does_not_spawn_agent(tmp_path, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(cli, "_server_binaries", lambda path: (path, path))

    def fail(path):
        raise RuntimeError("private copy failed")

    monkeypatch.setattr(cli, "_local_cli_exe", fail)
    spawn = Mock()
    monkeypatch.setattr(cli.subprocess, "Popen", spawn)
    assert cli.fluxdown_server_ensure(tmp_path / "fluxdown.exe") is None
    spawn.assert_not_called()
    code, message = cli._run_cli(tmp_path / "fluxdown.exe", {}, ["ping"])
    assert code == 1
    assert "server 不可用" in message


@pytest.mark.asyncio
async def testfluxdown_destination_lock_serializes_tasks_and_cancelled_waiter(
    tmp_path, monkeypatch
):
    import asyncio

    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    first, release = asyncio.Event(), asyncio.Event()
    order = []

    async def owner():
        async with cli.fluxdown_destination_lock(tmp_path / "exe", tmp_path / "file"):
            first.set()
            await release.wait()
            order.append("owner")

    async def waiter():
        async with cli.fluxdown_destination_lock(tmp_path / "exe", tmp_path / "file"):
            order.append("waiter")

    active = asyncio.create_task(owner())
    await first.wait()
    cancelled = asyncio.create_task(waiter())
    queued = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)
    assert not order
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    await asyncio.gather(active, queued)
    assert order == ["owner", "waiter"]


@pytest.fixture
def server_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda path: SimpleNamespace(gateway_port=12345, token="test"),
    )
    return (
        tmp_path / "fluxdown.exe",
        tmp_path / "package",
        "https://example.invalid/package",
    )


@pytest.mark.asyncio
async def test_cancelled_add_salvages_proxy_and_retry_resumes(
    server_fixture, monkeypatch
):
    import asyncio
    import threading

    exe, target, url = server_fixture
    started, release = threading.Event(), threading.Event()
    proxy = "http://localhost:7890"
    calls = []
    complete = False

    def command(exe, env, args, timeout=30):
        calls.append(args)
        if args[0] == "add":
            started.set()
            assert release.wait(5)
            return 0, '["task"]'
        if args[0] == "status":
            return 0, json.dumps(
                {
                    "status": 3 if complete else 2,
                    "downloadedBytes": 4,
                    "totalBytes": 4,
                    "saveDir": str(target.parent),
                    "fileName": target.name,
                }
            )
        return 0, ""

    monkeypatch.setattr(cli, "_run_cli", command)
    active = asyncio.create_task(
        cli.fluxdown_server_download(url, target, cli_exe=exe, proxy=proxy)
    )
    for _ in range(500):
        if started.is_set():
            break
        await asyncio.sleep(0.01)
    assert started.is_set()
    active.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await active
    key = cli._map_key(url, target)
    assert cli._load_task_map(exe)[key]["proxy_hash"] == cli._proxy_hash(proxy)
    target.write_bytes(b"data")
    complete = True
    assert (await cli.fluxdown_server_download(url, target, cli_exe=exe, proxy=proxy))[
        0
    ] == 4
    assert sum(args[0] == "add" for args in calls) == 1
    assert ["resume", "task"] in calls
    assert not any(args[0] == "rm" for args in calls)


@pytest.mark.asyncio
async def test_missing_task_mapping_recovers_without_proxy_change(
    server_fixture, monkeypatch
):
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "removed", url, target)
    calls = []

    def command(exe, env, args, timeout=30):
        calls.append(args)
        if len(args) > 1 and args[1] == "removed":
            return 3, "NotFound"
        if args[0] == "add":
            target.write_bytes(b"data")
            return 0, '["new"]'
        return 0, json.dumps(
            {
                "status": 3,
                "downloadedBytes": 4,
                "totalBytes": 4,
                "saveDir": str(target.parent),
                "fileName": target.name,
            }
        )

    monkeypatch.setattr(cli, "_run_cli", command)
    assert (await cli.fluxdown_server_download(url, target, cli_exe=exe))[0] == 4
    assert ["pause", "removed"] in calls
    assert not any(args[0] == "resume" for args in calls)


@pytest.mark.asyncio
async def test_history_write_sanitizes_retained_records(monkeypatch):
    from contextlib import asynccontextmanager

    from app.core import update as host
    from app.models.config.setting import GlobalConfig

    setting = GlobalConfig.model_validate(
        {
            "Update": {
                "LastUpdateHistory": [{"proxy": "http://old:password@localhost:7890"}]
            }
        }
    )
    saved = AsyncMock()
    monkeypatch.setattr(GlobalConfig, "update", saved)
    monkeypatch.setattr(host.Config, "setting", setting)

    @asynccontextmanager
    async def transaction():
        yield

    monkeypatch.setattr(host.config_manager, "transaction", transaction)
    await host._write_history(
        cli.FluxdownDownloadRecord(proxy="http://new:secret@localhost:7891")
    )
    history = saved.call_args.args[0].Update.LastUpdateHistory
    assert [item.proxy for item in history] == [
        "http://localhost:7890",
        "http://localhost:7891",
    ]


@pytest.mark.asyncio
async def test_destination_lock_is_visible_to_other_processes(tmp_path, monkeypatch):
    import asyncio
    import sys

    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    async with cli.fluxdown_destination_lock(tmp_path / "exe", tmp_path / "file"):
        path = next((tmp_path / "locks").glob("*.lock"))
        script = """
import os, sys
with open(sys.argv[1], 'r+b') as handle:
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)
    sys.exit(1)
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script, str(path)
        )
        assert await proc.wait() == 0


@pytest.mark.asyncio
async def test_server_download_prevents_installation_until_cancelled(
    tmp_path, monkeypatch
):
    import asyncio

    started = asyncio.Event()

    async def download(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(cli, "_server_data_dir", lambda path: tmp_path)
    monkeypatch.setattr(cli, "_fluxdown_server_download", download)
    shutdown = AsyncMock()
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", shutdown)
    task = asyncio.create_task(
        cli.fluxdown_server_download(
            "https://example.test/update.zip",
            tmp_path / "update.zip",
            cli_exe=tmp_path / "fluxdown.exe",
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        with pytest.raises(RuntimeError):
            with cli.fluxdown_install_guard():
                pytest.fail("installation must not interrupt the active download")
        shutdown.assert_not_called()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cli._active_downloads == 0
    async with cli.fluxdown_destination_lock(
        tmp_path / "fluxdown.exe", tmp_path / "update.zip"
    ):
        pass
