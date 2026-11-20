"""主后端通过桌面分身控制入口登记进程管理范围。"""

import asyncio
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.desktop_session import install_control
from app.core.desktop_session import lifecycle
from app.plugin.errors import PluginPrecheckError
from app.plugin.services import ServiceRegistry
from app.utils.common.process import operations, session
from app.utils.common.process.runner import popen_scoped
from app.utils.common.process.scope import TaskProcessScope, current_process_scope


@pytest.fixture
def desktop_session_native(monkeypatch):
    """在 Windows 系统调用边界模拟子会话状态。"""
    name = "app.utils.windows.desktop_session.native"
    native = ModuleType(name)
    native.child_session = Mock(return_value=None)
    native.session_state = Mock(return_value=0)
    monkeypatch.setitem(sys.modules, name, native)
    return native


def test_desktop_session_keeps_builtin_support_when_whimbox_is_a_plugin():
    from whimbox_adapter.config import WhimboxConfig

    from app.models.config import GeneralConfig

    general = GeneralConfig.build(payload={"Game": {"Enabled": False}})
    assert lifecycle.supports_task(general)
    assert not lifecycle.supports_task(WhimboxConfig.build())


@pytest.mark.asyncio
async def test_desktop_task_can_run_local_update_helper_without_adopting_local_processes(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(session, "matches_session", lambda pid, session_id: False)
    scope = TaskProcessScope()
    process_scope = current_process_scope.set(scope)
    desktop_target = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, tmp_path, tmp_path)
    )

    def run_helper() -> int:
        with popen_scoped([sys.executable, "-c", "pass"]) as process:
            return process.wait(timeout=10)

    try:
        with pytest.raises(ProcessLookupError):
            scope.track(psutil.Process(os.getpid()))
        assert await asyncio.to_thread(run_helper) == 0
    finally:
        session.desktop_process_target.reset(desktop_target)
        current_process_scope.reset(process_scope)
        await scope.force_close()


@pytest.mark.asyncio
async def test_dispatch_preflight_classifies_builtin_and_plugin_tasks_before_connecting(
    monkeypatch,
    desktop_session_native,
):
    from maa_adapter.config.script import MaaConfig
    from src_adapter.config import SrcConfig

    from app.core import Config, Plugin, TaskManager
    from app.models.config import (
        BetterGIConfig,
        HSRConfig,
        M9AConfig,
        OkwwConfig,
    )

    entries = {
        uuid4(): entry
        for entry in (
            MaaConfig.build(),
            M9AConfig.build(),
            SrcConfig.build(),
            BetterGIConfig.model_validate({"Run": {"UseAdmin": False}}),
            HSRConfig.build(),
            OkwwConfig.build(),
        )
    }
    monkeypatch.setattr(Config, "ScriptConfig", entries)
    monkeypatch.setattr(
        Plugin, "script_classes", lambda: {"MAA": MaaConfig, "SRC": SrcConfig}
    )
    current_session = desktop_session_native.child_session
    dispatch_scopes = []

    async def start(_mode, tasks, *, use_configured_session):
        assert not use_configured_session
        dispatch_scopes.append(
            (tasks[0]["children"][0]["uid"], session.desktop_process_target.get())
        )
        return uuid4()

    monkeypatch.setattr(TaskManager, "start", start)
    service = type(lifecycle.DesktopSessionLifecycle)()
    results = await service.dispatch_queues(
        list(entries), preview_only=True, main_session_queue_ids=set()
    )
    assert [row["code"] for row in results] == ["emulator_required"] * 3 + [""] * 3
    current_session.assert_not_called()
    assert dispatch_scopes == []

    main = {uid for uid, result in zip(entries, results, strict=True) if result["code"]}
    current_session.return_value = 7
    service.scope_state = (7, False)
    admitted = await service.dispatch_queues(
        list(entries), preview_only=False, main_session_queue_ids=main
    )
    assert all(row["taskId"] for row in admitted)
    assert {
        uid: scope.session_id if scope is not None else None
        for uid, scope in dispatch_scopes
    } == {str(uid): None if uid in main else 7 for uid in entries}


@pytest.mark.asyncio
async def test_single_script_default_uses_connected_session_and_respects_close(
    monkeypatch,
    desktop_session_native,
):
    from app.api.dispatch import TaskCreateIn, add_task
    from app.core import Config, Plugin, TaskManager
    from app.core.notify.commands import execute_notification_command
    from app.models.config import GeneralConfig

    desktop_id, legacy_id, queue_id = (uuid4() for _ in range(3))
    desktop = GeneralConfig.build(
        payload={"Info": {"Name": "Desktop"}, "Run": {"ExecutionSession": "desktop"}}
    )
    legacy = GeneralConfig.build()
    await desktop.activate()
    await legacy.activate()
    monkeypatch.setattr(
        Config, "ScriptConfig", {desktop_id: desktop, legacy_id: legacy}
    )
    monkeypatch.setattr(lifecycle, "_control_token", "test-token")
    services = ServiceRegistry()
    services.register("desktop_session.launcher", lambda: None, owner="desktop_session")
    monkeypatch.setattr(Plugin, "services", services)
    desktop_session_native.child_session.return_value = 7
    service = type(lifecycle.DesktopSessionLifecycle)()
    monkeypatch.setattr(lifecycle, "DesktopSessionLifecycle", service)
    starts = []
    running = {}

    async def launch(_run, node):
        uid = uuid4()
        running[uid] = object()
        starts.append((session.desktop_process_session_id(), node))
        return uid

    monkeypatch.setattr(TaskManager, "_check_accepting", lambda: None)
    monkeypatch.setattr(TaskManager, "_launch_selected", launch)
    monkeypatch.setattr(type(TaskManager), "task_info", property(lambda _: running))

    def single(uid):
        return TaskCreateIn.model_validate(
            {
                "mode": "AutoProxy",
                "tasks": {
                    "0": {
                        "uid": "-",
                        "children": {
                            "0": {
                                "uid": str(uid),
                                "children": {"0": {"uid": str(uuid4())}},
                            }
                        },
                    }
                },
            }
        )

    selected = single(desktop_id)
    assert (await add_task(selected)).code == 409
    assert "暂时无法启动" in await execute_notification_command(
        "retry_script", "Desktop"
    )
    assert not starts
    await service.set_process_scope(session_id=7, connecting=False)
    result = await add_task(selected)
    assert result.code == 200
    assert starts == [(7, selected.tasks[0])]
    assert service.prune_and_list_tasks() == (UUID(result.taskId),)

    assert "已提交脚本重试" in await execute_notification_command(
        "retry_script", "Desktop"
    )
    assert starts[-1][0] == 7
    assert not await service.set_preview_closing(closing=True)
    assert (await add_task(selected)).code == 409
    assert len(starts) == 2
    assert (await add_task(single(legacy_id))).code == 200
    queue = TaskCreateIn.model_validate(
        {"mode": "AutoProxy", "tasks": {"0": {"uid": str(queue_id)}}}
    )
    assert (await add_task(queue)).code == 200
    assert [(scope, node.uid) for scope, node in starts] == [
        (7, "-"),
        (7, "-"),
        (None, "-"),
        (None, str(queue_id)),
    ]


def test_dispatch_conflict_has_localizable_code(monkeypatch):
    monkeypatch.setattr(lifecycle, "_control_token", "")
    monkeypatch.setattr(
        "app.api.desktop_session.authenticated", lambda token: token == "test-control"
    )
    monkeypatch.setattr(
        lifecycle.DesktopSessionLifecycle,
        "dispatch_queues",
        AsyncMock(side_effect=lifecycle.DesktopSessionConflict("桌面分身连接已断开")),
    )
    app = FastAPI()
    install_control(app)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/internal/desktop-session/queues",
            json={"queueIds": ["00000000-0000-4000-8000-000000000001"]},
            headers={lifecycle.CONTROL_HEADER: "test-control"},
        )
    assert response.status_code == 409
    assert response.json() == {
        "code": "session_changed",
        "status": "error",
        "message": "桌面分身连接已断开",
    }


def test_preview_uses_enabled_plugin_and_holds_it_across_backend_restart(
    monkeypatch, isolated_app_paths, tmp_path
):
    from app.api.desktop_session import router
    from app.core import Plugin

    services = ServiceRegistry()
    monkeypatch.setattr(Plugin, "services", services)
    monkeypatch.setattr(lifecycle, "_control_token", "test-control-token")
    app = FastAPI()
    app.include_router(router)
    describe = "/internal/desktop-session/describe"
    headers = {lifecycle.CONTROL_HEADER: "test-control-token"}
    launcher = tmp_path / "wheel" / "desktop_session" / "bootstrap.py"
    restarted = type(lifecycle.DesktopSessionLifecycle)()
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.post(describe, headers=headers).status_code == 404
        services.register(
            "desktop_session.launcher", lambda: launcher, owner="desktop_session"
        )
        assert client.post(describe).status_code == 403
        assert client.post(describe, headers=headers).json()["launcher"] == str(
            launcher
        )
        restarted.assert_preview_closed()

        assert client.post(f"{describe}?reserve=true", headers=headers).is_success
        with pytest.raises(PluginPrecheckError):
            restarted.assert_preview_closed()
        assert client.post(
            "/internal/desktop-session/release", headers=headers
        ).is_success
        restarted.assert_preview_closed()

        services.unregister_owner("desktop_session")
        assert client.post(describe, headers=headers).status_code == 404


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.parametrize("restored", [False, True])
def test_parent_scope_protects_child_after_preview_disconnect(monkeypatch, restored):
    from app.utils.windows.desktop_session import native

    child_id = 7 if restored else None
    monkeypatch.setattr(native, "child_session", lambda: child_id)
    monkeypatch.setattr(
        native, "process_session", lambda pid: 1 if pid == os.getpid() else 7
    )
    monkeypatch.setattr(session, "_parent_scope", None)
    monkeypatch.setattr(lifecycle, "_control_token", "test-control-token")
    monkeypatch.setattr(lifecycle, "_parent_child_session", "7" if restored else "")

    app = FastAPI()
    install_control(app)
    path = "/internal/desktop-session/process-scope"
    assert path not in app.openapi()["paths"]
    headers = {lifecycle.CONTROL_HEADER: "test-control-token"}
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert session.process_in_scope(100) is (not restored)
        if not restored:
            assert client.post(path, json={"sessionId": 7}).status_code == 403
            assert client.post(
                path, headers=headers, json={"sessionId": None, "connecting": True}
            ).is_success
            assert session.process_in_scope(100)
            child_id = 7
            assert not session.process_in_scope(100)
            assert client.post(path, headers=headers, json={"sessionId": 7}).is_success
        assert not session.process_in_scope(100)
        assert client.post(path, headers=headers, json={"sessionId": None}).is_success
        assert not session.process_in_scope(100)
        child_id = None
        assert session.process_in_scope(100)


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
def test_process_operations_filter_and_recheck_scope(monkeypatch):
    from app.utils.windows.desktop_session import native

    process = Mock(pid=100)
    monkeypatch.setattr(operations.psutil, "process_iter", lambda _: iter([process]))
    monkeypatch.setattr(native, "process_session", lambda pid: 7)
    monkeypatch.setattr(session, "_parent_scope", None)
    assert list(operations.iter_processes(["pid"])) == [process]

    session.configure_parent_scope(lambda: 1)
    assert list(operations.iter_processes(["pid"])) == []
    token = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, Path.cwd(), Path.cwd())
    )
    try:
        assert list(operations.iter_processes(["pid"])) == [process]
    finally:
        session.desktop_process_target.reset(token)
    assert not operations.terminate_process(process, force=True)
    process.kill.assert_not_called()


@pytest.mark.asyncio
async def test_shared_game_update_guard_checks_other_sessions(monkeypatch, tmp_path):
    from app.task.MaaEnd.tools.update.checks import _release_install_dir
    from app.utils import process as process_api

    game = tmp_path / "game" / "Endfield.exe"
    process = Mock(pid=100)
    process.info = {"pid": 100, "name": game.name, "exe": str(game)}
    monkeypatch.setattr(operations.psutil, "process_iter", lambda _: iter([process]))
    monkeypatch.setattr(
        operations, "matches_session", lambda _, session_id: session_id in (None, 1)
    )
    kill = AsyncMock()
    monkeypatch.setattr(process_api, "kill_process", kill)
    token = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, tmp_path, tmp_path)
    )
    try:
        assert await operations.is_process_stopped(game)
        assert not await operations.is_process_stopped(game, all_sessions=True)
        assert await _release_install_dir(game)
        kill.assert_not_awaited()
        other_installation = tmp_path / "other" / game.name
        assert await operations.is_process_stopped(
            other_installation, all_sessions=True
        )
        process.info["exe"] = None
        assert not await operations.is_process_stopped(game, all_sessions=True)
    finally:
        session.desktop_process_target.reset(token)


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
def test_managed_process_separates_exited_from_out_of_scope(monkeypatch):
    from app.utils.windows.desktop_session import native

    monkeypatch.setattr(native, "process_session", lambda pid: 2)
    monkeypatch.setattr(session, "_parent_scope", None)

    exited = Mock()
    exited.create_time.side_effect = psutil.NoSuchProcess(100)
    monkeypatch.setattr(operations.psutil, "Process", lambda pid: exited)
    # 自己退出：调用方按「无事可做」处理。
    assert operations.managed_process(100) is None

    alive = Mock(pid=100)
    alive.create_time.return_value = 20
    alive.is_running.return_value = True
    monkeypatch.setattr(operations.psutil, "Process", lambda pid: alive)
    session.configure_parent_scope(lambda: 1)
    # 仍在运行但不归本会话管：不能当成已结束。
    with pytest.raises(ProcessLookupError):
        operations.managed_process(100)

    # PID 在另一会话被复用，旧快照对应的进程已退出。
    assert operations.managed_process(100, expected_create_time=10) is None

    # 打开进程后自然退出，WTS 已无法查询该 PID。
    def session_after_exit(pid):
        raise OSError(87, "进程已退出")

    monkeypatch.setattr(native, "process_session", session_after_exit)
    alive.is_running.return_value = False
    assert operations.managed_process(100, expected_create_time=20) is None


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 分身进程执行器")
@pytest.mark.asyncio
async def test_desktop_process_delivers_launcher_progress_before_completion(
    monkeypatch,
):
    import asyncio
    from threading import get_ident
    from unittest.mock import AsyncMock

    from app.utils.windows.desktop_session import process_runner

    monkeypatch.setattr(
        process_runner,
        "_read",
        AsyncMock(side_effect=[{"log": "launcher progress"}, {"returnCode": 0}]),
    )
    monkeypatch.setattr(process_runner, "_wait_worker", lambda worker: None)
    loop = asyncio.get_running_loop()
    loop_thread = get_ident()
    reported = []

    async def report(line):
        reported.append(line)

    def on_log(line):
        assert get_ident() != loop_thread
        asyncio.run_coroutine_threadsafe(report(line), loop).result(timeout=5)

    process = process_runner.DesktopProcess(42, Mock(), Mock(), on_log)
    assert await process.wait() == (0, b"", b"")
    assert reported == ["launcher progress"]


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows Job Object")
@pytest.mark.parametrize(
    "owned,command,breakaway",
    [
        (True, "stop", False),
        (False, "stop", False),
        (False, "release", False),
        (True, "stop", True),
    ],
)
def test_desktop_job_keeps_game_after_launcher_exits(
    monkeypatch, tmp_path, owned, command, breakaway
):
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue
    from threading import Event

    from app.utils.windows.desktop_session import process_worker

    frames = Queue()
    stop = Event()
    monkeypatch.setattr(process_worker, "send", lambda pipe, frame: frames.put(frame))
    monkeypatch.setattr(process_worker, "receive", lambda pipe: {command: True})
    monkeypatch.setattr(
        process_worker.win32pipe,
        "PeekNamedPipe",
        lambda pipe, size: (b"", int(stop.is_set()), 0),
    )

    game_pid_file = tmp_path / "game.pid"
    launcher = (
        "import subprocess, sys; from pathlib import Path; "
        "game = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        f"creationflags={subprocess.CREATE_BREAKAWAY_FROM_JOB if breakaway else 0}); "
        "Path(sys.argv[1]).write_text(str(game.pid))"
    )
    request = {
        "argv": [sys.executable, "-c", launcher, str(game_pid_file)],
        "cwd": str(tmp_path),
        "merge": False,
        "env": None,
        "retain": True,
        "owned": owned,
        "capture": False,
    }
    with ThreadPoolExecutor(max_workers=1) as thread_pool:
        worker = thread_pool.submit(
            process_worker.run_process,
            None,
            request,
            subprocess.DEVNULL,
            subprocess.DEVNULL,
        )
        try:
            launcher_pid = frames.get(timeout=10)["pid"]
            try:
                psutil.Process(launcher_pid).wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            game = psutil.Process(int(game_pid_file.read_text()))
            assert game.is_running()
            if not breakaway:
                assert not worker.done()
        finally:
            stop.set()
        worker.result(timeout=10)
        while "returnCode" not in (frame := frames.get(timeout=1)):
            assert frame == {"exitCode": 0}
        assert frame["returnCode"] == 0
        try:
            if command == "stop" and not breakaway:
                game.wait(timeout=10)
            else:
                assert game.is_running()
        finally:
            if game.is_running():
                game.kill()
                game.wait(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows Job Object")
@pytest.mark.parametrize("interactive", [False, True])
def test_desktop_job_forwards_stdio_before_exit(monkeypatch, tmp_path, interactive):
    import base64
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue

    from app.utils.windows.desktop_session import process_worker

    frames = Queue()
    controls = Queue()
    payload = base64.b64encode(b"run\n").decode("ascii")
    controls.put(
        {
            "argv": [
                sys.executable,
                "-u",
                "-c",
                "import sys; print('ready'); print(sys.stdin.readline().strip()); "
                "print('diagnostic', file=sys.stderr)",
            ],
            "cwd": str(tmp_path),
            "stream": True,
            "stream_stdout": True,
            "stream_stderr": True,
            "interactive": interactive,
            "stdin": None if interactive else payload,
            "merge": False,
            "env": None,
            "retain": False,
            "capture": False,
        }
    )
    monkeypatch.setattr(process_worker, "send", lambda pipe, frame: frames.put(frame))
    monkeypatch.setattr(process_worker, "receive", lambda pipe: controls.get(timeout=5))
    monkeypatch.setattr(
        process_worker.win32pipe,
        "PeekNamedPipe",
        lambda pipe, size: (b"", controls.qsize(), 0),
    )

    with ThreadPoolExecutor(max_workers=1) as thread_pool:
        worker = thread_pool.submit(process_worker.run, None)
        try:
            assert frames.get(timeout=10)["pid"] > 0
            output = {"stdout": bytearray(), "stderr": bytearray()}
            while "returnCode" not in (frame := frames.get(timeout=10)):
                for name in output.keys() & frame.keys():
                    output[name].extend(base64.b64decode(frame[name]))
                if interactive and b"ready" in output["stdout"]:
                    controls.put({"input": payload})
                    interactive = False
            assert frame["returnCode"] == 0
            assert output["stdout"].splitlines() == [b"ready", b"run"]
            assert output["stderr"].splitlines() == [b"diagnostic"]
        finally:
            controls.put({"stop": True})
        worker.result(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows Job Object")
def test_desktop_command_termination_preserves_game(monkeypatch, tmp_path):
    import base64
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue

    from app.utils.windows.desktop_session import process_worker

    frames, controls = Queue(), Queue()
    monkeypatch.setattr(process_worker, "send", lambda _, frame: frames.put(frame))
    monkeypatch.setattr(process_worker, "receive", lambda _: controls.get(timeout=1))
    monkeypatch.setattr(
        process_worker.win32pipe,
        "PeekNamedPipe",
        lambda pipe, size: (b"", controls.qsize(), 0),
    )
    command = (
        "import subprocess, sys, time; "
        "game = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "print(game.pid, flush=True); time.sleep(60)"
    )
    request = {
        "argv": [sys.executable, "-u", "-c", command],
        "cwd": str(tmp_path),
        "merge": False,
        "env": None,
        "retain": True,
        "owned": False,
        "stream": True,
        "stop_root_only": True,
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(
            process_worker.run_process,
            None,
            request,
            subprocess.PIPE,
            subprocess.DEVNULL,
        )
        game = None
        try:
            started = frames.get(timeout=10)
            assert started["pid"] > 0
            assert started["rootHandle"] > 0
            controls.put({"rootHandleReceived": True})
            pid_line = bytearray()
            while not pid_line.endswith(b"\n"):
                pid_line.extend(base64.b64decode(frames.get(timeout=10)["stdout"]))
            game = psutil.Process(int(pid_line))
            controls.put({"terminateRoot": True})
            while "exitCode" not in (frame := frames.get(timeout=10)):
                assert frame == {"eof": "stdout"}
            assert frame["exitCode"] != 0
            controls.put({"release": True})
            worker.result(timeout=10)
            assert game.is_running()
        finally:
            controls.put({"stop": True})
            if game is not None and game.is_running():
                game.kill()
                game.wait(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 进程句柄")
@pytest.mark.asyncio
async def test_desktop_worker_exit_stops_only_the_owned_root(monkeypatch, tmp_path):
    import subprocess

    import win32api
    import win32con

    from app.utils.windows.desktop_session import process_runner

    game_pid_file = tmp_path / "game.pid"
    command = (
        "import subprocess, sys, time; from pathlib import Path; "
        "game = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "pid_file = Path(sys.argv[1]); temporary = pid_file.with_suffix('.tmp'); "
        "temporary.write_text(str(game.pid)); temporary.replace(pid_file); time.sleep(60)"
    )
    access = win32con.SYNCHRONIZE | win32con.PROCESS_TERMINATE
    with (
        subprocess.Popen([sys.executable, "-c", command, str(game_pid_file)]) as root,
        subprocess.Popen([sys.executable, "-c", "pass"]) as worker,
    ):
        game = None
        try:
            async with asyncio.timeout(10):
                while not game_pid_file.exists():
                    await asyncio.sleep(0.05)
            game = psutil.Process(int(game_pid_file.read_text()))
            monkeypatch.setattr(
                process_runner, "_read", AsyncMock(side_effect=OSError("pipe closed"))
            )
            process = process_runner.DesktopProcess(
                root.pid,
                Mock(),
                win32api.OpenProcess(access, False, worker.pid),
                owned=False,
                root_handle=win32api.OpenProcess(access, False, root.pid),
            )
            with pytest.raises(OSError, match="pipe closed"):
                await process.wait()
            assert root.poll() is not None
            assert game.is_running()
        finally:
            if root.poll() is None:
                root.kill()
            if game is not None and game.is_running():
                game.kill()
                game.wait(timeout=10)
