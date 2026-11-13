import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.common.update import fluxdown as transport
from app.utils.common import fluxdown_cli as cli


def test_direct_proxy_and_history_redaction():
    assert transport._proxy_to_str(None) is None
    record = cli.FluxdownDownloadRecord(proxy="http://u%40ser:p%3A%2Fword@[::1]:7890")
    assert record.to_dict()["proxy"] == "http://[::1]:7890"


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
    assert code is None
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
    output = target

    def command(exe, env, args, timeout=30):
        nonlocal output
        calls.append(args)
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            started.set()
            assert release.wait(5)
            return 0, '["task"]'
        if args[0] == "status":
            return 0, json.dumps(
                {
                    "status": 3 if complete else 2,
                    "downloadedBytes": 4,
                    "totalBytes": 4,
                    "saveDir": str(output.parent),
                    "fileName": output.name,
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
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await active
    key = cli._map_key(url, target)
    assert cli._load_task_map(exe)[key]["proxy_hash"] == cli._proxy_hash(proxy)
    output.write_bytes(b"data")
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
    output = target

    def command(exe, env, args, timeout=30):
        nonlocal output
        calls.append(args)
        if len(args) > 1 and args[1] == "removed":
            return 3, "NotFound"
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            output.write_bytes(b"data")
            return 0, '["new"]'
        return 0, json.dumps(
            {
                "status": 3,
                "downloadedBytes": 4,
                "totalBytes": 4,
                "saveDir": str(output.parent),
                "fileName": output.name,
            }
        )

    monkeypatch.setattr(cli, "_run_cli", command)
    assert (await cli.fluxdown_server_download(url, target, cli_exe=exe))[0] == 4
    assert ["pause", "removed"] in calls
    assert not any(args[0] == "resume" for args in calls)


@pytest.mark.asyncio
async def test_history_write_sanitizes_retained_records(monkeypatch):
    from contextlib import asynccontextmanager

    from app.core import downloads as host
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
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", lambda: None)
    with cli.fluxdown_install_guard():
        with pytest.raises(RuntimeError, match="正在安装"):
            await cli.fluxdown_server_download(
                "https://example.test/update.zip",
                tmp_path / "update.zip",
                cli_exe=tmp_path / "fluxdown.exe",
            )


def test_other_url_same_target_requires_stopped_writer(tmp_path, monkeypatch):
    exe = tmp_path / "fluxdown.exe"
    target = tmp_path / "package.zip"
    old_url = "https://example.invalid/old"
    new_url = "https://example.invalid/new"
    mapping = {
        cli._map_key(old_url, target): {
            "task_id": "old-task",
            "save_path": str(target),
        }
    }
    monkeypatch.setattr(cli, "_load_task_map", lambda _exe: mapping)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _exe: SimpleNamespace(gateway_port=12345, token="token"),
    )
    monkeypatch.setattr(cli, "_run_cli", lambda *_args, **_kwargs: (124, "timeout"))
    assert not cli.fluxdown_server_task_safe_to_overwrite(exe, new_url, target)
    assert not cli.fluxdown_server_task_safe_to_overwrite(
        exe, new_url, target, other_only=True
    )


def test_other_url_completed_allows_new_writer_without_resuming_old(
    tmp_path, monkeypatch
):
    exe = tmp_path / "fluxdown.exe"
    target = tmp_path / "package.zip"
    old_url, new_url = "https://example.invalid/old", "https://example.invalid/new"
    mapping = {
        cli._map_key(old_url, target): {
            "task_id": "old-task",
            "save_path": str(target),
        }
    }
    calls = []

    def cli_command(_exe, _env, args, timeout=30):
        calls.append(args)
        if args[0] == "pause":
            return 0, ""
        if args[0] == "status":
            return 0, json.dumps({"status": 3})
        raise AssertionError("completed task must not be resumed")

    monkeypatch.setattr(cli, "_load_task_map", lambda _exe: mapping)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _exe: SimpleNamespace(gateway_port=12345, token="token"),
    )
    monkeypatch.setattr(cli, "_run_cli", cli_command)
    assert cli.fluxdown_server_task_safe_to_overwrite(
        exe, new_url, target, other_only=True
    )
    assert calls == [["pause", "old-task"], ["status", "old-task", "--json"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("downloader", ["fluxdown", "builtin"])
@pytest.mark.parametrize("probe_result", [True, False, "error"])
async def test_cancelled_write_owner_probe_holds_target_lock_until_thread_exits(
    tmp_path, monkeypatch, downloader, probe_result
):
    import asyncio
    import threading

    monkeypatch.setattr(cli, "_server_data_dir", lambda _path: tmp_path)
    executable = tmp_path / "fluxdown.exe"
    destination = tmp_path / "release.zip"
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda _path, **kwargs: executable)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_probe(*_args, **_kwargs):
        started.set()
        try:
            assert release.wait(5), "probe thread was never released"
            if probe_result == "error":
                raise OSError("stop probe unavailable")
            return probe_result
        finally:
            finished.set()

    monkeypatch.setattr(cli, "fluxdown_server_task_safe_to_overwrite", slow_probe)
    options = transport.FluxdownOptions(downloader, "GitHub", str(executable), 8, True)
    backend = AsyncMock(return_value=1)
    first = asyncio.create_task(
        transport.download_file(
            "https://example.invalid/second",
            destination,
            timeout=30,
            options=options,
            downloader=downloader,
            source="GitHub",
            http_download=backend,
        )
    )
    assert await asyncio.to_thread(started.wait, 3)
    acquired = asyncio.Event()

    async def next_owner():
        async with cli.fluxdown_destination_lock(executable, destination):
            acquired.set()

    follower = None
    try:
        first.cancel()
        await asyncio.sleep(0.05)
        assert not first.done(), "cancellation released a still-running probe"
        follower = asyncio.create_task(next_owner())
        await asyncio.sleep(0.05)
        assert not acquired.is_set(), "next owner entered while old probe is active"
    finally:
        release.set()
    with pytest.raises(
        asyncio.CancelledError
        if probe_result is True
        else transport.FluxdownWriterUnconfirmed
    ):
        await asyncio.wait_for(first, timeout=5)
    assert finished.is_set()
    backend.assert_not_awaited()
    assert follower is not None
    await asyncio.wait_for(follower, timeout=5)
    assert acquired.is_set()


@pytest.mark.asyncio
async def test_unconfirmed_server_writer_propagates_as_unsafe_handoff(
    server_fixture, monkeypatch
):
    """A real server download failure must not be an ordinary resumable error."""
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "inflight", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_args, **_kw: True)
    calls = []

    def command(_exe, _env, args, timeout=30):
        calls.append(args)
        # Both the status query and attempted pause are unavailable, so the
        # daemon cannot be assumed to have stopped writing.
        return 124, "timeout"

    monkeypatch.setattr(cli, "_run_cli", command)
    options = transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True)
    with pytest.raises(transport.FluxdownWriterUnconfirmed):
        await transport.download_file(
            url, target, timeout=30, options=options, source="GitHub"
        )
    assert any(args[0] == "status" for args in calls)
    assert any(args[0] == "pause" for args in calls)
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == "inflight"


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_evidence", ["completed", "not_found"])
async def test_confirmed_server_stop_allows_safe_builtin_handoff(
    server_fixture, monkeypatch, stop_evidence
):
    """Completed HTTP tasks and authoritative NotFound permit switching to httpx."""
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "inflight", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    calls = []

    def command(_exe, _env, args, timeout=30):
        calls.append(args)
        if args[0] == "pause":
            return (3, "NotFound") if stop_evidence == "not_found" else (0, "")
        if args[0] == "status":
            return 0, json.dumps({"status": 3})
        raise AssertionError("No new daemon download should be started")

    monkeypatch.setattr(cli, "_run_cli", command)
    builtin = AsyncMock(return_value=10)
    options = transport.FluxdownOptions("builtin", "GitHub", str(exe), 8, True)
    assert (
        await transport.download_file(
            url,
            target,
            timeout=30,
            options=options,
            downloader="builtin",
            source="GitHub",
            http_download=builtin,
        )
        == 10
    )
    assert [a[0] for a in calls] == (
        ["pause"] if stop_evidence == "not_found" else ["pause", "status"]
    )
    builtin.assert_awaited_once()


@pytest.mark.parametrize(
    "owned,other_download,expected",
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),
        (True, "pending", False),
    ],
)
def test_emergency_shutdown_only_for_exclusive_owned_agent(
    tmp_path, monkeypatch, owned, other_download, expected
):
    exe = tmp_path / "fluxdown.exe"
    agent = tmp_path / "fluxdown-agent.exe"
    target = tmp_path / "package.zip"
    url = "https://example.invalid/package.zip"
    key = cli._map_key(url, target)
    mapping = {key: {"task_id": "own", "save_path": str(target)}}
    if other_download:
        mapping["another"] = {
            "task_id": None if other_download == "pending" else "other",
            "pending_add": other_download == "pending",
            "save_path": "other.zip",
        }
    monkeypatch.setattr(cli, "_active_downloads", 1)
    monkeypatch.setattr(cli, "_installing", False)
    monkeypatch.setattr(cli, "_load_task_map", lambda _exe: mapping)
    monkeypatch.setattr(
        cli, "_server_binaries", lambda _exe: (agent, tmp_path / "daemon")
    )
    monkeypatch.setattr(
        cli._server,
        "handle",
        SimpleNamespace(cli_exe=exe, agent_pid=34567),
    )
    monkeypatch.setattr(cli._server, "spawned_by_us", owned)
    process = SimpleNamespace(
        exe=lambda: str(agent),
        children=lambda recursive: [],
        is_running=lambda: False,
    )
    monkeypatch.setattr(cli.psutil, "Process", lambda _pid: process)
    killed = []
    monkeypatch.setattr(cli, "_kill_pid", killed.append)
    assert cli.fluxdown_server_emergency_stop_if_exclusive(exe, url, target) is expected
    assert killed == ([34567] if expected else [])


@pytest.mark.asyncio
async def test_cancel_falls_back_to_exclusive_emergency_shutdown(
    server_fixture, monkeypatch
):
    """When pause cannot be confirmed, stop only our exclusive private agent."""
    import asyncio

    exe, target, url = server_fixture
    # Reuse a known server task so Windows does not need to complete the
    # slower CLI add + mapping setup before the cancellation signal.
    cli._map_put(exe, cli._map_key(url, target), "existing", url, target)
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def command(_exe, _env, args, timeout=30):
        if args[0] == "resume":
            return 0, ""
        if args[0] == "status":
            loop.call_soon_threadsafe(started.set)
            return 0, json.dumps({"status": 1})
        if args[0] == "pause":
            return 124, "timeout"
        return 0, ""

    monkeypatch.setattr(cli, "_run_cli", command)
    emergency = []
    monkeypatch.setattr(
        cli,
        "fluxdown_server_emergency_stop_if_exclusive",
        lambda *_args: emergency.append(True) or True,
    )
    task = asyncio.create_task(cli.fluxdown_server_download(url, target, cli_exe=exe))
    await asyncio.wait_for(started.wait(), 10)
    task.cancel()
    with pytest.raises(cli.FluxdownCancelUnconfirmed, match="强制结束"):
        await task
    assert emergency == [True]
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == "existing"


@pytest.mark.asyncio
async def test_failed_emergency_shutdown_reports_unconfirmed_writer(
    server_fixture, monkeypatch
):
    import asyncio

    exe, target, url = server_fixture
    # Reuse a known server task so Windows does not need to complete the
    # slower CLI add + mapping setup before the cancellation signal.
    cli._map_put(exe, cli._map_key(url, target), "existing", url, target)
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def command(_exe, _env, args, timeout=30):
        if args[0] == "resume":
            return 0, ""
        if args[0] == "status":
            loop.call_soon_threadsafe(started.set)
            return 0, json.dumps({"status": 1})
        if args[0] == "pause":
            return 124, "timeout"
        return 0, ""

    def failed_stop(*_args):
        raise OSError("denied")

    monkeypatch.setattr(cli, "_run_cli", command)
    monkeypatch.setattr(cli, "fluxdown_server_emergency_stop_if_exclusive", failed_stop)
    task = asyncio.create_task(cli.fluxdown_server_download(url, target, cli_exe=exe))
    await asyncio.wait_for(started.wait(), 10)
    task.cancel()
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_confirmed", [False, True])
async def test_stalled_download_checks_pause_before_queue_handoff(
    server_fixture, monkeypatch, pause_confirmed
):
    """Stalled daemon cannot be a normal retry unless its writer stopped."""
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "existing", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_args, **_kw: True)
    paused = False
    commands = []

    def command(_exe, _env, args, timeout=30):
        nonlocal paused
        commands.append(args[0])
        if args[0] == "resume":
            return 0, ""
        if args[0] == "pause":
            if pause_confirmed:
                paused = True
                return 0, ""
            return 124, "timeout"
        if args[0] == "status":
            return 0, json.dumps({"status": 3 if paused else 1, "downloadedBytes": 0})
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    options = transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True)
    expected = (
        cli.FluxdownCancelUnconfirmed
        if not pause_confirmed
        else transport.FluxdownResumableError
    )
    with pytest.raises(expected):
        await transport.download_file(
            url, target, timeout=-1, options=options, source="GitHub"
        )
    assert "pause" in commands
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == "existing"


def test_exclusive_shutdown_blocks_new_download_admission(tmp_path, monkeypatch):
    """A cannot kill a daemon after B starts joining it during shutdown."""
    import asyncio
    import threading

    exe, agent = tmp_path / "fluxdown.exe", tmp_path / "fluxdown-agent.exe"
    target, url = tmp_path / "asset.zip", "https://example.invalid/asset"
    monkeypatch.setattr(cli, "_server_data_dir", lambda _exe: tmp_path)
    cli._map_put(exe, cli._map_key(url, target), "own", url, target)
    monkeypatch.setattr(cli, "_active_downloads", 1)
    monkeypatch.setattr(cli, "_installing", False)
    monkeypatch.setattr(cli, "_server_binaries", lambda _: (agent, tmp_path / "daemon"))
    monkeypatch.setattr(
        cli._server, "handle", SimpleNamespace(cli_exe=exe, agent_pid=24680)
    )
    monkeypatch.setattr(cli._server, "spawned_by_us", True)
    process = SimpleNamespace(
        exe=lambda: str(agent),
        children=lambda recursive: [],
        is_running=lambda: False,
    )
    monkeypatch.setattr(cli.psutil, "Process", lambda _: process)
    in_kill, release_kill, downloaded = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def slow_kill(_pid):
        in_kill.set()
        assert release_kill.wait(5)

    monkeypatch.setattr(cli, "_kill_pid", slow_kill)
    shutdown = threading.Thread(
        target=lambda: cli.fluxdown_server_emergency_stop_if_exclusive(exe, url, target)
    )

    @cli._using_fluxdown
    async def competing_download():
        downloaded.set()

    def run_second():
        asyncio.run(competing_download())

    shutdown.start()
    competitor = None
    try:
        assert in_kill.wait(5)
        competitor = threading.Thread(target=run_second)
        competitor.start()
        assert not downloaded.wait(0.05)
    finally:
        release_kill.set()
        shutdown.join(timeout=5)
        if competitor is not None:
            competitor.join(timeout=5)
    assert not shutdown.is_alive()
    assert downloaded.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [False, True])
async def test_add_failure_with_task_id_requires_confirmed_pause(
    server_fixture, monkeypatch, confirmed
):
    """A failed add may still leave a live daemon task; do not hand off."""
    exe, target, url = server_fixture
    paused = False
    commands = []

    def command(_exe, _env, args, timeout=30):
        nonlocal paused
        commands.append(args[0])
        if args[0] == "list":
            return 0, "[]"
        if args[0] == "add":
            return 1, '["created"]'
        if args[0] == "pause":
            if confirmed:
                paused = True
                return 0, ""
            return 124, "timeout"
        if args[0] == "status":
            return 0, json.dumps({"status": 3 if paused else 1})
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    expected = RuntimeError if confirmed else cli.FluxdownCancelUnconfirmed
    with pytest.raises(expected) as caught:
        await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert ("无法确认" in str(caught.value)) is (not confirmed)
    assert "pause" in commands
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == "created"


@pytest.mark.asyncio
async def test_emergency_shutdown_does_not_block_main_event_loop(tmp_path, monkeypatch):
    """A newly admitted download awaits emergency stop without freezing UI."""
    import asyncio
    import threading

    exe, agent = tmp_path / "fluxdown.exe", tmp_path / "fluxdown-agent.exe"
    target, url = tmp_path / "asset.zip", "https://example.invalid/asset"
    monkeypatch.setattr(cli, "_server_data_dir", lambda _exe: tmp_path)
    cli._map_put(exe, cli._map_key(url, target), "own", url, target)
    monkeypatch.setattr(cli, "_active_downloads", 1)
    monkeypatch.setattr(cli, "_installing", False)
    monkeypatch.setattr(cli, "_server_emergency_stopping", False)
    monkeypatch.setattr(cli, "_server_binaries", lambda _: (agent, tmp_path / "daemon"))
    monkeypatch.setattr(
        cli._server, "handle", SimpleNamespace(cli_exe=exe, agent_pid=24680)
    )
    monkeypatch.setattr(cli._server, "spawned_by_us", True)
    process = SimpleNamespace(
        exe=lambda: str(agent),
        children=lambda recursive: [],
        is_running=lambda: False,
    )
    monkeypatch.setattr(cli.psutil, "Process", lambda _: process)
    entered, release = threading.Event(), threading.Event()

    def slow_kill(_pid):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(cli, "_kill_pid", slow_kill)
    stop = asyncio.create_task(
        asyncio.to_thread(
            cli.fluxdown_server_emergency_stop_if_exclusive, exe, url, target
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        downloaded = asyncio.Event()

        @cli._using_fluxdown
        async def competitor():
            downloaded.set()

        other = asyncio.create_task(competitor())
        await asyncio.sleep(0.02)
        assert not downloaded.is_set()
        # A heartbeat must still run while the stop worker waits.
        beat = asyncio.Event()
        asyncio.get_running_loop().call_soon(beat.set)
        await asyncio.wait_for(beat.wait(), 1)
    finally:
        release.set()
    assert await asyncio.wait_for(stop, 5)
    await asyncio.wait_for(other, 5)
    assert downloaded.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["builtin", "server_error"])
async def test_unconfirmed_writer_survives_history_cancellation_via_public_download(
    tmp_path, monkeypatch, stage
):
    """A cancelled history transaction must not release an active daemon file."""
    import asyncio

    exe = tmp_path / "fluxdown.exe"
    destination = tmp_path / "private" / "payload.part"
    destination.parent.mkdir()
    destination.write_bytes(b"still daemon-owned")
    entered = asyncio.Event()
    backend = AsyncMock(return_value=12)

    async def blocked_history(_record):
        entered.set()
        await asyncio.Event().wait()

    def unsafe_stop_check(*_args, other_only=False, **_kwargs):
        return other_only

    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(
        cli, "fluxdown_server_task_safe_to_overwrite", unsafe_stop_check
    )
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_download",
        AsyncMock(side_effect=OSError("map write failed after add")),
    )
    monkeypatch.setattr(cli, "fluxdown_server_mark_failure", lambda *_a: 1)
    task = asyncio.create_task(
        transport.download_file(
            "https://example.invalid/payload",
            destination,
            timeout=10,
            options=transport.FluxdownOptions(
                "builtin" if stage == "builtin" else "fluxdown",
                "AutoSite",
                str(exe),
                8,
                True,
            ),
            write_history=blocked_history,
            http_download=backend,
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(transport.FluxdownWriterUnconfirmed):
        await asyncio.wait_for(task, 3)
    assert destination.read_bytes() == b"still daemon-owned"
    backend.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_add_response_blocks_retry_until_task_can_be_recovered(
    server_fixture, monkeypatch
):
    exe, target, url = server_fixture
    visible = False
    commands = []
    output = target

    def command(_exe, _env, args, *_, **_kwargs):
        nonlocal output
        commands.append(args)
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            output.write_bytes(b"data")
            return 124, "request timed out"
        if args[0] == "list":
            old_task = {
                "taskId": "historical-task",
                "url": url,
                "saveDir": str(target.parent),
                "fileName": target.name,
            }
            tasks = [old_task]
            if visible:
                tasks.append(
                    {**old_task, "taskId": "late-task", "fileName": output.name}
                )
            return 0, json.dumps(tasks)
        if args[0] == "resume":
            assert args[1] == "late-task"
            return 0, "resumed"
        if args[0] == "status":
            return 0, json.dumps(
                {
                    "status": 3,
                    "downloadedBytes": 4,
                    "totalBytes": 4,
                    "saveDir": str(output.parent),
                    "fileName": output.name,
                }
            )
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    for _ in range(2):
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await cli.fluxdown_server_download(url, target, cli_exe=exe)
        assert cli._load_task_map(exe)[cli._map_key(url, target)]["pending_add"]
        assert output.read_bytes() == b"data"
    visible = True
    size, _ = await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert size == 4
    assert target.read_bytes() == b"data"
    entry = cli._load_task_map(exe)[cli._map_key(url, target)]
    assert entry["task_id"] == "late-task"
    assert not entry["pending_add"]
    assert sum(args[0] == "add" for args in commands) == 1
    assert ["resume", "late-task"] in commands


@pytest.mark.asyncio
async def test_cancelled_destination_lock_wait_is_not_reported_as_stopped_writer(
    tmp_path, monkeypatch
):
    import asyncio

    monkeypatch.setattr(cli, "_server_data_dir", lambda _: tmp_path / "server")
    exe, target = tmp_path / "fluxdown.exe", tmp_path / "package.zip"
    target.write_bytes(b"another writer")
    backend = AsyncMock()
    async with cli.fluxdown_destination_lock(exe, target):
        task = asyncio.create_task(
            transport.download_file(
                "https://example.invalid/pkg",
                target,
                timeout=10,
                options=transport.FluxdownOptions(
                    "builtin", "GitHub", str(exe), 8, True
                ),
                http_download=backend,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await task
        assert target.read_bytes() == b"another writer"
    backend.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_marker_write_failure_does_not_submit_add(
    server_fixture, monkeypatch
):
    exe, target, url = server_fixture
    commands = []

    def command(_exe, _env, args, timeout=30):
        commands.append(args[0])
        if args[0] == "list":
            return 0, "[]"
        return 1, "request failed"

    def fail_replace(*args):
        raise PermissionError("map file is locked")

    monkeypatch.setattr(cli, "_run_cli", command)
    monkeypatch.setattr(cli.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="map file is locked"):
        await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert "add" not in commands


@pytest.mark.parametrize("contents", ["{broken", "[]"])
def test_unreadable_task_map_cannot_prove_file_is_unowned(server_fixture, contents):
    exe, target, url = server_fixture
    cli._server_map_path(exe).write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        cli.fluxdown_server_task_safe_to_overwrite(exe, url, target)


@pytest.mark.asyncio
async def test_unconfirmed_writer_map_failure_preserves_ownership_error(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(transport, "_can_downgrade", AsyncMock(return_value=False))

    def failed_save(*args):
        raise PermissionError("map file locked")

    monkeypatch.setattr(cli, "fluxdown_server_mark_failure", failed_save)
    with pytest.raises(transport.FluxdownWriterUnconfirmed):
        await transport._ensure_can_downgrade(
            tmp_path / "exe",
            "https://example.invalid/package",
            tmp_path / "package",
            segments=8,
            proxy_str=None,
            action="退出",
            write_history=None,
        )


@pytest.mark.asyncio
async def test_destination_lock_io_failure_does_not_grant_file_ownership(
    tmp_path, monkeypatch
):
    import errno

    exe, destination = tmp_path / "exe", tmp_path / "shared.zip"
    destination.write_bytes(b"other writer")
    monkeypatch.setattr(cli, "_server_data_dir", lambda *_: tmp_path)

    def fail_lock(_handle):
        raise OSError(errno.EIO, "file lock unavailable")

    monkeypatch.setattr(cli.file_lock, "acquire", fail_lock)
    backend = AsyncMock()
    with pytest.raises(transport.FluxdownWriterUnconfirmed):
        await transport.download_file(
            "https://example.invalid/package",
            destination,
            timeout=10,
            options=transport.FluxdownOptions("builtin", "GitHub", str(exe), 8, True),
            http_download=backend,
        )
    backend.assert_not_awaited()
    assert destination.read_bytes() == b"other writer"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_startup_snapshot_cannot_identify_a_late_historical_task(
    server_fixture, monkeypatch, cancel
):
    """An empty gateway snapshot is not proof that the next visible task is ours."""
    import asyncio
    import threading
    from pathlib import Path

    exe, target, url = server_fixture
    submitted, release = threading.Event(), threading.Event()
    calls = []
    output = target

    def command(_exe, _env, args, *_, **_kwargs):
        nonlocal output
        calls.append(args)
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            output.write_bytes(b"new writer")
            submitted.set()
            assert release.wait(5)
            return 124, "request timed out"
        if args[0] == "list":
            return 0, json.dumps(
                [
                    {
                        "taskId": "historical",
                        "url": url,
                        "saveDir": str(target.parent),
                        "fileName": target.name,
                    }
                ]
                if submitted.is_set()
                else []
            )
        if args[0] == "pause":
            return 0, ""
        if args[0] == "status":
            return 0, '{"status": 3}'
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    task = asyncio.create_task(cli.fluxdown_server_download(url, target, cli_exe=exe))
    try:
        for _ in range(500):
            if submitted.is_set():
                break
            await asyncio.sleep(0.01)
        assert submitted.is_set()
        if cancel:
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
        release.set()
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await task
        assert not any(args[:2] == ["pause", "historical"] for args in calls)
        assert cli._load_task_map(exe)[cli._map_key(url, target)]["pending_add"]
        assert output.read_bytes() == b"new writer"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_legacy_pending_add_cannot_be_recovered_from_a_snapshot(
    server_fixture, monkeypatch
):
    exe, target, url = server_fixture
    key = cli._map_key(url, target)
    cli._server_map_path(exe).write_text(
        json.dumps(
            {
                key: {
                    "pending_add": True,
                    "task_id": None,
                    "add_baseline": [],
                    "url": url,
                    "save_path": str(target),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "_run_cli",
        lambda *_a, **_kw: (
            0,
            json.dumps(
                [
                    {
                        "taskId": "historical",
                        "url": url,
                        "saveDir": str(target.parent),
                        "fileName": target.name,
                    }
                ]
            ),
        ),
    )
    assert cli._recover_pending_add(exe, url, target) is None
    assert cli._load_task_map(exe)[key]["pending_add"]


@pytest.mark.asyncio
@pytest.mark.parametrize("downloader", ["builtin", "fluxdown"])
@pytest.mark.parametrize("access", ["missing", "denied"])
@pytest.mark.parametrize("old_writer", [False, True])
async def test_unavailable_cli_checks_persisted_writer_before_fallback(
    server_fixture, monkeypatch, downloader, access, old_writer
):
    exe, target, url = server_fixture
    if old_writer:
        cli._map_put(exe, cli._map_key(url, target), "still-running", url, target)
    target.write_bytes(b"owned by daemon")
    monkeypatch.setattr(cli.shutil, "which", lambda *_a: None)
    if access == "denied":
        is_file = Path.is_file

        def inaccessible(path):
            if path == exe:
                raise PermissionError("CLI directory is inaccessible")
            return is_file(path)

        monkeypatch.setattr(Path, "is_file", inaccessible)
    monkeypatch.setattr(cli, "fluxdown_server_ensure", lambda *_a: None)

    async def builtin(_url, destination, **kwargs):
        destination.write_bytes(b"new")
        return 3

    backend = AsyncMock(side_effect=builtin)
    download = transport.download_file(
        url,
        target,
        timeout=1,
        options=transport.FluxdownOptions(downloader, "GitHub", str(exe), 8, True),
        http_download=backend,
    )
    if old_writer:
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await download
        backend.assert_not_awaited()
        assert target.read_bytes() == b"owned by daemon"
    else:
        assert await download == 3
        assert target.read_bytes() == b"new"


def test_exited_agent_does_not_hide_a_live_daemon_child(server_fixture, monkeypatch):
    exe, target, url = server_fixture
    agent = exe.with_name("fluxdown-agent.exe")
    cli._map_put(exe, cli._map_key(url, target), "own", url, target)
    monkeypatch.setattr(cli, "_active_downloads", 1)
    monkeypatch.setattr(cli, "_installing", False)
    monkeypatch.setattr(cli, "_server_emergency_stopping", False)
    monkeypatch.setattr(
        cli, "_server_binaries", lambda _: (agent, exe.with_name("daemon"))
    )
    handle = SimpleNamespace(cli_exe=exe, agent_pid=12345)
    monkeypatch.setattr(cli._server, "handle", handle)
    monkeypatch.setattr(cli._server, "spawned_by_us", True)

    def exited():
        raise cli.psutil.NoSuchProcess(12345)

    child = SimpleNamespace(
        is_running=lambda: True, status=lambda: cli.psutil.STATUS_RUNNING
    )
    process = SimpleNamespace(
        exe=lambda: str(agent), children=lambda recursive: [child], is_running=exited
    )
    monkeypatch.setattr(cli.psutil, "Process", lambda _: process)
    monkeypatch.setattr(cli, "_kill_pid", lambda _: None)
    assert not cli.fluxdown_server_emergency_stop_if_exclusive(exe, url, target)
    assert cli._server.handle is handle


@pytest.mark.asyncio
async def test_repeated_local_cancel_waits_for_process_exit(tmp_path, monkeypatch):
    import asyncio

    ready, stopping, exited, release = (asyncio.Event() for _ in range(4))

    class Output:
        async def __aiter__(self):
            ready.set()
            await exited.wait()
            if False:
                yield b""

    class Process:
        returncode = None
        pid = 12345
        stdout = Output()

        def kill(self):
            stopping.set()

        async def wait(self):
            await release.wait()
            self.returncode = -9
            exited.set()
            return self.returncode

        async def communicate(self):
            await self.wait()
            return b"", None

    monkeypatch.setattr(cli, "_local_cli_exe", lambda path: path)
    monkeypatch.setattr(
        cli.asyncio, "create_subprocess_exec", AsyncMock(return_value=Process())
    )
    task = asyncio.create_task(
        cli.fluxdown_download(
            "https://example.invalid/package",
            tmp_path / "package",
            cli_exe=tmp_path / "exe",
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        await asyncio.wait_for(stopping.wait(), 3)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done(), "cancellation released a still-running CLI writer"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set()
    finally:
        release.set()
        exited.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("snapshot_status", [2, 4])
@pytest.mark.parametrize("pause_code", [0, 124])
def test_stale_stopped_snapshot_does_not_prove_a_resumed_writer_stopped(
    server_fixture, monkeypatch, snapshot_status, pause_code
):
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "resumed", url, target)
    calls = []

    def command(_exe, _env, args, **_kwargs):
        calls.append(args)
        if args[0] == "status":
            return 0, json.dumps({"status": snapshot_status})
        if args[0] == "pause":
            return pause_code, "stop requested; writer may still be flushing"
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    assert not cli.fluxdown_server_task_safe_to_overwrite(exe, url, target)
    assert ["pause", "resumed"] in calls


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_status", [2, 4])
async def test_accepted_pause_with_stale_snapshot_keeps_cancel_unconfirmed(
    server_fixture, monkeypatch, snapshot_status
):
    import asyncio

    exe, target, url = server_fixture
    key = cli._map_key(url, target)
    cli._map_put(exe, key, "resumed", url, target)
    target.write_bytes(b"writer owns this file")
    started = asyncio.Event()
    pause_requested = False

    def command(_exe, _env, args, timeout=30):
        nonlocal pause_requested
        if args[0] == "resume":
            return 0, ""
        if args[0] == "pause":
            pause_requested = True
            return 0, ""
        if args[0] == "status":
            return 0, json.dumps(
                {
                    "status": snapshot_status if pause_requested else 1,
                    "downloadedBytes": 0,
                    "totalBytes": 10,
                }
            )
        raise AssertionError(args)

    async def progress(*_args):
        started.set()

    emergency = []
    monkeypatch.setattr(cli, "_run_cli", command)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_emergency_stop_if_exclusive",
        lambda *_args: emergency.append(True) or True,
    )
    task = asyncio.create_task(
        cli.fluxdown_server_download(url, target, cli_exe=exe, progress=progress)
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(cli.FluxdownCancelUnconfirmed, match="强制结束"):
            await task
        assert emergency == [True]
        assert cli._load_task_map(exe)[key]["task_id"] == "resumed"
        assert target.read_bytes() == b"writer owns this file"
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_status", [2, 4])
async def test_missing_status_then_accepted_pause_never_replaces_existing_task(
    server_fixture, monkeypatch, snapshot_status
):
    exe, target, url = server_fixture
    key = cli._map_key(url, target)
    cli._map_put(exe, key, "existing", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_args, **_kw: True)
    calls = []
    first_status = True

    def command(_exe, _env, args, timeout=30):
        nonlocal first_status
        calls.append(args)
        if args[0] == "status":
            if first_status:
                first_status = False
                return 124, "gateway unavailable"
            return 0, json.dumps({"status": snapshot_status})
        if args[0] == "pause":
            return 0, ""
        raise AssertionError("Unconfirmed task must not be replaced")

    monkeypatch.setattr(cli, "_run_cli", command)
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await transport.download_file(
            url,
            target,
            timeout=1,
            options=transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True),
        )
    assert not any(args[0] in ("add", "resume", "rm") for args in calls)
    assert cli._load_task_map(exe)[key]["task_id"] == "existing"


@pytest.mark.asyncio
async def test_resume_failure_with_stale_error_snapshot_keeps_existing_task(
    server_fixture, monkeypatch
):
    exe, target, url = server_fixture
    key = cli._map_key(url, target)
    cli._map_put(exe, key, "existing", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_args, **_kw: True)
    calls = []

    def command(_exe, _env, args, timeout=30):
        calls.append(args)
        if args[0] == "resume":
            return 1, "resume result unavailable"
        if args[0] == "status":
            return 0, '{"status": 4}'
        if args[0] == "pause":
            return 0, ""
        raise AssertionError("Unconfirmed task must not be replaced")

    monkeypatch.setattr(cli, "_run_cli", command)
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await transport.download_file(
            url,
            target,
            timeout=1,
            options=transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True),
        )
    assert not any(args[0] in ("add", "rm") for args in calls)
    assert cli._load_task_map(exe)[key]["task_id"] == "existing"


@pytest.mark.asyncio
async def test_task_map_updates_are_serialized_across_processes(tmp_path, monkeypatch):
    import asyncio
    import sys

    monkeypatch.setattr(cli, "_server_data_dir", lambda _: tmp_path)
    script = """
import sys
from pathlib import Path
from app.utils.common import fluxdown_cli as cli
root, mode = Path(sys.argv[1]), sys.argv[2]
cli._server_data_dir = lambda _: root
if mode == 'first':
    original = cli._load_task_map
    def delayed(path):
        mapping = original(path)
        print('read', flush=True)
        sys.stdin.readline()
        return mapping
    cli._load_task_map = delayed
else:
    print('started', flush=True)
cli._map_put(root / 'cli', mode, mode, 'https://example.invalid/' + mode, root / mode)
"""
    first = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(tmp_path),
        "first",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    second = None
    try:
        assert (await asyncio.wait_for(first.stdout.readline(), 5)).rstrip(
            b"\r\n"
        ) == b"read"
        second = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(tmp_path),
            "second",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert (await asyncio.wait_for(second.stdout.readline(), 5)).rstrip(
            b"\r\n"
        ) == b"started"
        try:
            await asyncio.wait_for(second.wait(), 0.1)
        except asyncio.TimeoutError:
            pass
        first.stdin.write(b"continue\n")
        await first.stdin.drain()
        await asyncio.wait_for(asyncio.gather(first.wait(), second.wait()), 5)
        assert first.returncode == second.returncode == 0
        assert set(cli._load_task_map(tmp_path / "cli")) == {"first", "second"}
    finally:
        for process in (first, second):
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.asyncio
async def test_completed_mapping_is_forgotten_before_cancellable_history(
    server_fixture, monkeypatch
):
    import asyncio

    exe, target, url = server_fixture
    output = target

    def command(_exe, _env, args, *_, **_kw):
        nonlocal output
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            output.write_bytes(b"data")
            return 0, '["created"]'
        if args[0] == "status":
            return 0, json.dumps(
                {
                    "status": 3,
                    "downloadedBytes": 4,
                    "totalBytes": 4,
                    "saveDir": str(output.parent),
                    "fileName": output.name,
                }
            )
        return 0, ""

    monkeypatch.setattr(cli, "_run_cli", command)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_a, **_kw: True)
    recording = asyncio.Event()

    async def history(_record):
        recording.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        transport.download_file(
            url,
            target,
            timeout=1,
            options=transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True),
            write_history=history,
        )
    )
    try:
        await asyncio.wait_for(recording.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert target.read_bytes() == b"data"
        assert cli._map_key(url, target) not in cli._load_task_map(exe)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_published_output_with_retained_mapping_can_be_downloaded_again(
    server_fixture, monkeypatch
):
    """A crash after publishing must not pin future retries to a missing source."""
    exe, target, url = server_fixture
    request_path = target.with_name(".mas-fluxdown-previous")
    cli._map_put(
        exe,
        cli._map_key(url, target),
        "previous",
        url,
        target,
        request_path=request_path,
    )
    target.write_bytes(b"old or externally modified")
    output = request_path
    calls = []

    def command(_exe, _env, args, *_, **_kw):
        nonlocal output
        calls.append(args)
        if args[0] == "add":
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            output.write_bytes(b"fresh")
            return 0, '["fresh"]'
        if args[0] == "status":
            path = request_path if args[1] == "previous" else output
            return 0, json.dumps(
                {
                    "status": 3,
                    "downloadedBytes": 5,
                    "totalBytes": 5,
                    "saveDir": str(path.parent),
                    "fileName": path.name,
                }
            )
        return 0, ""

    monkeypatch.setattr(cli, "_run_cli", command)
    size, _ = await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert size == 5 and target.read_bytes() == b"fresh"
    assert ["resume", "previous"] not in calls
    assert ["rm", "previous"] in calls


@pytest.mark.asyncio
async def test_local_cancel_drains_a_full_output_pipe(tmp_path, monkeypatch):
    import asyncio
    import sys

    spawn = asyncio.create_subprocess_exec
    spawned, release_spawn = asyncio.Event(), asyncio.Event()
    process = None

    async def delayed_spawn(*_args, **kwargs):
        nonlocal process
        process = await spawn(
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.buffer.write(b'x'*2000000); sys.stdout.flush(); time.sleep(30)",
            **kwargs,
        )
        spawned.set()
        await release_spawn.wait()
        return process

    monkeypatch.setattr(cli, "_local_cli_exe", lambda path: path)
    monkeypatch.setattr(cli.asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(
        cli.fluxdown_download(
            "https://example.invalid/package",
            tmp_path / "package",
            cli_exe=tmp_path / "exe",
        )
    )
    try:
        await asyncio.wait_for(spawned.wait(), 5)
        # 故意不消费输出，子进程输出量远大于 PIPE 的高水位。
        await asyncio.sleep(0.1)
        task.cancel()
        release_spawn.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 2)
        assert process.returncode is not None
    finally:
        release_spawn.set()
        if process is not None:
            if process.returncode is None:
                process.kill()
            if not task.done():
                # 旧代码的 wait() 在管道未排空时卡住，用同一个句柄完成测试收尾。
                await process.communicate()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_pending_write_does_not_become_a_retryable_disk_error(
    server_fixture, monkeypatch
):
    import asyncio
    import threading

    exe, target, url = server_fixture
    entered, release = threading.Event(), threading.Event()

    def failed_save(*_args):
        entered.set()
        assert release.wait(5)
        raise OSError("disk failure after cancellation")

    monkeypatch.setattr(cli, "_save_task_map", failed_save)
    command = AsyncMock()
    monkeypatch.setattr(cli, "_run_cli", command)
    task = asyncio.create_task(cli.fluxdown_server_download(url, target, cli_exe=exe))
    try:
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        command.assert_not_called()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_during_local_error_cleanup_takes_precedence(
    tmp_path, monkeypatch
):
    import asyncio

    stopping, release = asyncio.Event(), asyncio.Event()

    class Output:
        async def __aiter__(self):
            raise ValueError("CLI output line is too long")
            yield b""

    class Process:
        returncode = None
        pid = 12345
        stdout = Output()

        def kill(self):
            pass

        async def communicate(self):
            stopping.set()
            await release.wait()
            self.returncode = -9
            return b"", None

    monkeypatch.setattr(cli, "_local_cli_exe", lambda path: path)
    monkeypatch.setattr(
        cli.asyncio, "create_subprocess_exec", AsyncMock(return_value=Process())
    )
    task = asyncio.create_task(
        cli.fluxdown_download(
            "https://example.invalid/package",
            tmp_path / "package",
            cli_exe=tmp_path / "exe",
        )
    )
    try:
        await asyncio.wait_for(stopping.wait(), 3)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "history", ["none", "old_writer", "cli_unreadable", "no_writer_cli_unreadable"]
)
async def test_cancel_waiting_for_server_admission_preserves_writer_ownership(
    server_fixture, monkeypatch, history
):
    """A same-source retry may be cancelled before the download body starts."""
    import asyncio
    import threading

    exe, target, url = server_fixture
    exe = exe.with_name(cli._FLUXDOWN_EXE_NAMES[0])
    exe.touch()
    old_writer = history in ("old_writer", "cli_unreadable")
    target.write_bytes(b"retained archive")
    if old_writer:
        cli._map_put(exe, cli._map_key(url, target), "previous", url, target)
    admission, competitor_entered = asyncio.Event(), asyncio.Event()
    probing, release_probe = threading.Event(), threading.Event()
    builtin = AsyncMock(side_effect=AssertionError("unexpected HTTP fallback"))
    monkeypatch.setattr(transport, "_httpx_download", builtin)

    def available(*args, **kwargs):
        admission.set()
        return True

    def command(_exe, _env, args, timeout=30):
        assert args == ["pause", "previous"]
        probing.set()
        assert release_probe.wait(5)
        return 124, "timeout"

    monkeypatch.setattr(cli, "fluxdown_server_available", available)
    monkeypatch.setattr(cli, "_run_cli", command)
    monkeypatch.setattr(cli, "_active_downloads", 1)
    monkeypatch.setattr(cli._server, "spawned_by_us", False)
    options = transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True)

    async def competitor():
        async with cli.fluxdown_destination_lock(exe, target):
            competitor_entered.set()

    # Emergency stop closes admission before waiting for the server lock. It
    # may subsequently decline the stop, leaving an older retry's writer alive.
    cli._server.lock.acquire()
    shutdown = asyncio.create_task(
        asyncio.to_thread(
            cli.fluxdown_server_emergency_stop_if_exclusive,
            exe,
            "https://example.invalid/another",
            target.with_name("another"),
        )
    )
    active = queued = None
    try:
        async with asyncio.timeout(3):
            while not cli._server_emergency_stopping:
                await asyncio.sleep(0.001)
        active = asyncio.create_task(
            transport.download_file(url, target, timeout=30, options=options)
        )
        await asyncio.wait_for(admission.wait(), 3)
        if history.endswith("cli_unreadable"):
            is_file = Path.is_file

            def inaccessible(path):
                if path == exe:
                    raise PermissionError("CLI directory became inaccessible")
                return is_file(path)

            monkeypatch.setattr(Path, "is_file", inaccessible)
        active.cancel()
        if old_writer:
            async with asyncio.timeout(3):
                while not probing.is_set() and not active.done():
                    await asyncio.sleep(0.001)
            if probing.is_set():
                queued = asyncio.create_task(competitor())
                active.cancel()
                await asyncio.sleep(0.02)
                assert not active.done()
                assert not competitor_entered.is_set()
            release_probe.set()
            with pytest.raises(cli.FluxdownCancelUnconfirmed):
                await active
            assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == (
                "previous"
            )
        else:
            with pytest.raises(asyncio.CancelledError):
                await active
        assert target.read_bytes() == b"retained archive"
        builtin.assert_not_called()
    finally:
        release_probe.set()
        cli._server.lock.release()
        await asyncio.gather(
            *(task for task in (shutdown, active, queued) if task is not None),
            return_exceptions=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_add_spawn_failure_releases_pending_identity_for_retry(
    server_fixture, monkeypatch, cancelled
):
    """Failure before OS process creation cannot have submitted an add RPC."""
    import asyncio
    import sys
    import threading

    exe, target, url = server_fixture
    real_popen = cli.subprocess.Popen
    starting, release = threading.Event(), threading.Event()
    refused = False
    output = target
    monkeypatch.setattr(cli, "_local_cli_exe", lambda path: Path(sys.executable))

    def spawn(argv, **kwargs):
        nonlocal refused, output
        args = argv[1:]
        if args[0] == "add":
            if not refused:
                refused = True
                starting.set()
                assert release.wait(5)
                raise PermissionError("OS refused process creation")
            output = Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            program = (
                f"from pathlib import Path; Path({str(output)!r}).write_bytes(b'data');"
                " print('[\"created\"]')"
            )
        elif args[0] == "list":
            program = "print('[]')"
        elif args[0] == "status":
            payload = json.dumps(
                {
                    "status": 3,
                    "downloadedBytes": 4,
                    "totalBytes": 4,
                    "saveDir": str(output.parent),
                    "fileName": output.name,
                }
            )
            program = f"print({payload!r})"
        else:
            raise AssertionError(args)
        return real_popen([sys.executable, "-c", program], **kwargs)

    monkeypatch.setattr(cli.subprocess, "Popen", spawn)
    active = asyncio.create_task(cli.fluxdown_server_download(url, target, cli_exe=exe))
    try:
        async with asyncio.timeout(3):
            while not starting.is_set():
                await asyncio.sleep(0.001)
        if cancelled:
            active.cancel()
            await asyncio.sleep(0)
            active.cancel()
            await asyncio.sleep(0)
        release.set()
        expected = asyncio.CancelledError if cancelled else RuntimeError
        with pytest.raises(expected) as caught:
            await active
        assert not isinstance(caught.value, cli.FluxdownCancelUnconfirmed)
        assert cli._map_key(url, target) not in cli._load_task_map(exe)
        size, _ = await cli.fluxdown_server_download(url, target, cli_exe=exe)
        assert size == 4
        assert target.read_bytes() == b"data"
    finally:
        release.set()
        await asyncio.gather(active, return_exceptions=True)


@pytest.mark.asyncio
async def test_add_communication_failure_after_spawn_keeps_pending_identity(
    server_fixture, monkeypatch
):
    """A post-spawn pipe error cannot prove that the command was not submitted."""
    import sys

    exe, target, url = server_fixture
    real_popen = cli.subprocess.Popen
    children = []
    monkeypatch.setattr(cli, "_local_cli_exe", lambda path: Path(sys.executable))

    def spawn(argv, **kwargs):
        process = real_popen([sys.executable, "-c", "print('[]')"], **kwargs)
        children.append(process)
        if argv[1] == "add":
            communicate = process.communicate

            def fail_after_execution(*args, **kwargs):
                communicate(*args, **kwargs)
                raise OSError("pipe read failed after command execution")

            process.communicate = fail_after_execution
        return process

    monkeypatch.setattr(cli.subprocess, "Popen", spawn)
    with pytest.raises(cli.FluxdownCancelUnconfirmed):
        await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["pending_add"]
    assert all(process.poll() is not None for process in children)
