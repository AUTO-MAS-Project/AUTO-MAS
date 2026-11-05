import json
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


def test_other_url_paused_allows_new_writer_without_resuming_old(tmp_path, monkeypatch):
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
        if args[0] == "status":
            return 0, json.dumps({"status": 2})
        raise AssertionError("paused task must not be resumed")

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
    assert calls == [["status", "old-task", "--json"]]


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
async def test_confirmed_server_stop_allows_safe_builtin_handoff(
    server_fixture, monkeypatch
):
    """Status ACTIVE -> pause success -> status PAUSED can switch to httpx."""
    exe, target, url = server_fixture
    cli._map_put(exe, cli._map_key(url, target), "inflight", url, target)
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_args, **_kw: exe)
    calls = []
    stopped = False

    def command(_exe, _env, args, timeout=30):
        nonlocal stopped
        calls.append(args)
        if args[0] == "pause":
            stopped = True
            return 0, ""
        if args[0] == "status":
            return 0, json.dumps({"status": 2 if stopped else 1})
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
    assert [a[0] for a in calls] == ["status", "pause", "status"]
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
    with pytest.raises(asyncio.CancelledError):
        await task
    assert emergency == [True]


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
            return 0, json.dumps({"status": 2 if paused else 1, "downloadedBytes": 0})
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
            return 0, json.dumps({"status": 2 if paused else 1})
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

    def command(_exe, _env, args, *_, **_kwargs):
        commands.append(args)
        if args[0] == "add":
            target.write_bytes(b"data")
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
                tasks.append({**old_task, "taskId": "late-task"})
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
                    "saveDir": str(target.parent),
                    "fileName": target.name,
                }
            )
        raise AssertionError(args)

    monkeypatch.setattr(cli, "_run_cli", command)
    for _ in range(2):
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await cli.fluxdown_server_download(url, target, cli_exe=exe)
        assert cli._load_task_map(exe)[cli._map_key(url, target)]["pending_add"]
        assert target.read_bytes() == b"data"
    visible = True
    size, _ = await cli.fluxdown_server_download(url, target, cli_exe=exe)
    assert size == 4
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
