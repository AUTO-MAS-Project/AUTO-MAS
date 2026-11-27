"""主后端通过桌面分身控制入口登记进程管理范围。"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.desktop_session import install_control
from app.core.desktop_session import lifecycle
from app.utils.common.process import operations, session
from app.utils.common.process.runner import popen_scoped
from app.utils.common.process.scope import TaskProcessScope, current_process_scope


def test_desktop_session_keeps_builtin_support_when_whimbox_is_a_plugin(monkeypatch):
    from whimbox_adapter.config import WhimboxConfig

    from app.models.config import GeneralConfig, ZzzOdConfig

    monkeypatch.setattr("app.utils.IS_ELEVATED", False)
    assert lifecycle.task_unavailable_reason(ZzzOdConfig.build()) == "admin_required"
    monkeypatch.setattr("app.utils.IS_ELEVATED", True)
    assert lifecycle.task_unavailable_reason(ZzzOdConfig.build()) is None
    general = GeneralConfig.build(payload={"Game": {"Enabled": False}})
    assert lifecycle.task_unavailable_reason(general) is None
    assert (
        lifecycle.task_unavailable_reason(WhimboxConfig.build()) == "plugin_unavailable"
    )


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
    process.as_dict.return_value = {"pid": process.pid}
    monkeypatch.setattr(
        operations.psutil, "process_iter", lambda attrs=None: iter([process])
    )
    monkeypatch.setattr(native, "process_session", lambda pid: 7)
    monkeypatch.setattr(session, "_parent_scope", None)
    assert list(operations.iter_processes(["pid"])) == [process]
    assert list(operations.iter_scoped_process_info(["pid"])) == [
        (process, {"pid": process.pid})
    ]

    session.configure_parent_scope(lambda: 1)
    assert list(operations.iter_processes(["pid"])) == []
    assert list(operations.iter_scoped_process_info(["pid"])) == []
    token = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, Path.cwd(), Path.cwd())
    )
    try:
        assert list(operations.iter_processes(["pid"])) == [process]
        assert list(operations.iter_scoped_process_info(["pid"])) == [
            (process, {"pid": process.pid})
        ]
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
    info = {"name": game.name, "exe": str(game)}
    process.as_dict.side_effect = lambda *, attrs: {attr: info[attr] for attr in attrs}
    monkeypatch.setattr(operations.psutil, "process_iter", lambda: iter([process]))
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
        info["exe"] = None
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


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 分身进程执行器")
def test_window_operation_after_target_exit_returns_false():
    from app.utils.windows.desktop_session import process_worker

    with subprocess.Popen([sys.executable, "-I", "-c", "pass"]) as child:
        pid = child.pid
        assert child.wait(timeout=10) == 0
    del child

    assert (
        process_worker.run_window_action(
            "hide_process_window", {"pid": pid, "createTime": 0.0}
        )
        == 1
    )


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 分身进程执行器")
@pytest.mark.asyncio
async def test_window_operations_run_in_the_selected_session(monkeypatch, tmp_path):
    from app.utils.common.process.manager import ProcessManager
    from app.utils.windows.desktop_session import process_runner, process_worker

    process = Mock(spec=psutil.Process, pid=101)
    process.create_time.return_value = 123.0
    process.is_running.return_value = True
    process.create_time.return_value = 123.0
    manager = ProcessManager()
    manager.target_process = process
    target = session.DesktopProcessTarget(7, tmp_path, tmp_path)

    def close_window(_hwnd):
        process.is_running.return_value = False
        return True

    close = Mock(side_effect=close_window)
    show, hide = Mock(return_value=True), Mock(return_value=True)
    monkeypatch.setattr(process_worker, "process_session", lambda _: 7)
    monkeypatch.setattr(
        operations, "managed_process", lambda pid, **_: process if pid == 101 else None
    )
    monkeypatch.setattr(
        "app.utils.common.process.manager.get_main_window_handle",
        lambda pid, *_: 42 if pid == 101 else None,
    )
    for name, operation in (
        ("close_window", close),
        ("show_window", show),
        ("hide_window", hide),
    ):
        monkeypatch.setattr(
            f"app.utils.common.process.manager.window.{name}", operation
        )

    async def run_in_child(selected, action, arguments, *, worker_module):
        assert selected == target
        assert worker_module == process_worker.__name__
        return process_worker.run_window_action(action, arguments), b"", b""

    monkeypatch.setattr(process_runner, "run_desktop_action", run_in_child)
    token = session.desktop_process_target.set(target)
    try:
        assert await manager.show_window()
        assert await manager.hide_window()
        await manager.close()
        assert not await manager.is_running()
    finally:
        session.desktop_process_target.reset(token)
    for operation in (show, hide, close):
        operation.assert_called_once_with(42)
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["main", "desktop", "disconnected", "queue", "selection_changed"]
)
async def test_manual_start_respects_configured_execution_session(monkeypatch, case):
    from uuid import uuid4

    from app.api.dispatch import TaskCreateIn, add_task
    from app.core import Config, TaskManager
    from app.models.config import GeneralConfig
    from app.utils.windows.desktop_session import native

    sid, task_id = uuid4(), uuid4()
    entry = GeneralConfig.build(
        payload={
            "Game": {"Enabled": False},
            "Run": {
                "ExecutionSession": "main"
                if case in {"main", "selection_changed"}
                else "desktop"
            },
        }
    )
    await entry.activate()
    monkeypatch.setattr(Config, "ScriptConfig", {str(sid): entry})
    service = lifecycle._DesktopSessionLifecycle()
    monkeypatch.setattr(lifecycle, "DesktopSessionLifecycle", service)
    service.scope_state = (7, False)
    monkeypatch.setattr(
        native, "child_session", lambda: None if case == "disconnected" else 7
    )
    monkeypatch.setattr(native, "session_state", lambda _: 0)
    seen = []

    async def start(mode, tasks):
        seen.append(session.desktop_process_target.get())
        return task_id

    monkeypatch.setattr(TaskManager, "start", start)
    root = (
        {"uid": str(uuid4())}
        if case == "queue"
        else {
            "uid": "-",
            "children": {0: {"uid": str(sid), "children": {0: {"uid": str(uuid4())}}}},
        }
    )
    result = await add_task(
        TaskCreateIn.model_validate(
            {
                "mode": "AutoProxy",
                "tasks": {0: root},
                "requireDesktopSession": case in {"desktop", "selection_changed"},
            }
        )
    )
    if case in {"disconnected", "selection_changed"}:
        assert result.code == 409
        assert result.reason == (
            "desktop_session_disconnected" if case == "disconnected" else None
        )
        assert not seen and not service.task_ids
    else:
        assert result.taskId == str(task_id)
        assert [target.session_id if target else None for target in seen] == [
            7 if case == "desktop" else None
        ]
        assert service.task_ids == ({task_id} if case == "desktop" else set())
    assert session.desktop_process_target.get() is None


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [True, False])
async def test_manual_start_reads_plugin_execution_session(monkeypatch, declared):
    """插件托管的配置类不继承宿主的运行设置类：Run 上声明了执行会话才按它选分身。"""
    from typing import Literal
    from uuid import uuid4

    from pydantic import Field

    from app.api.dispatch import TaskCreateIn, add_task
    from app.core import Config, Plugin, TaskManager
    from app.models.config import ConfigGroup, ScriptEntry
    from app.utils.windows.desktop_session import native

    class PluginScript(ScriptEntry):
        class RunFields(ConfigGroup):
            ProxyTimesLimit: int = 0
            if declared:
                ExecutionSession: Literal["main", "desktop"] = "main"

        Run: RunFields = Field(default_factory=RunFields)

    sid, task_id = uuid4(), uuid4()
    entry = PluginScript.build(
        payload={"Run": {"ExecutionSession": "desktop"} if declared else {}}
    )
    await entry.activate()
    monkeypatch.setattr(Config, "ScriptConfig", {str(sid): entry})
    monkeypatch.setattr(Plugin, "desktop_session_reason", lambda *_: None)
    service = lifecycle._DesktopSessionLifecycle()
    monkeypatch.setattr(lifecycle, "DesktopSessionLifecycle", service)
    service.scope_state = (7, False)
    monkeypatch.setattr(native, "child_session", lambda: 7)
    monkeypatch.setattr(native, "session_state", lambda _: 0)
    seen = []

    async def start(mode, tasks):
        seen.append(session.desktop_process_target.get())
        return task_id

    monkeypatch.setattr(TaskManager, "start", start)
    result = await add_task(
        TaskCreateIn.model_validate(
            {
                "mode": "AutoProxy",
                "tasks": {
                    0: {
                        "uid": "-",
                        "children": {
                            0: {"uid": str(sid), "children": {0: {"uid": str(uuid4())}}}
                        },
                    }
                },
                "requireDesktopSession": declared,
            }
        )
    )
    assert result.taskId == str(task_id)
    assert [target.session_id if target else None for target in seen] == [
        7 if declared else None
    ]
    assert service.task_ids == ({task_id} if declared else set())
    assert session.desktop_process_target.get() is None


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.asyncio
async def test_desktop_close_separates_external_processes_and_blocks_new_tasks(
    monkeypatch,
):
    from uuid import uuid4

    from app.core import TaskManager
    from app.utils.windows.desktop_session import inventory, native

    service = lifecycle._DesktopSessionLifecycle()
    service.set_process_scope(session_id=7, connecting=False)
    task_id = uuid4()
    service.task_ids.add(task_id)
    monkeypatch.setattr(native, "child_session", lambda: 7)
    tasks = {task_id: object()}
    attempt = uuid4()
    monkeypatch.setattr(type(TaskManager), "task_info", property(lambda _: tasks))
    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: False)
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        True,
        False,
        False,
    )

    tasks.clear()
    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: True)
    assert await service.close_status(7, "inspect") == (False, True, False)
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        False,
        True,
        False,
    )

    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: None)
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        False,
        None,
        False,
    )

    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: False)
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        False,
        False,
        True,
    )
    with pytest.raises(lifecycle.DesktopSessionConflict, match="正在关闭"):
        await service.dispatch_queues(
            [], preview_only=True, main_session_queue_ids=set()
        )
    await service.close_status(7, "release", attempt_id=uuid4())
    with pytest.raises(lifecycle.DesktopSessionConflict, match="正在关闭"):
        await service.dispatch_queues(
            [], preview_only=True, main_session_queue_ids=set()
        )
    await service.close_status(7, "release", attempt_id=attempt)
    assert service._close_reservation is None

    # 读取响应超时后，释放先于原关闭请求到达时也应保持可派发。
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        False,
        None,
        False,
    )
    monkeypatch.setattr(native, "session_state", lambda _: 0)
    assert service._connected_target().session_id == 7

    # Windows 已自行注销原分身，用户仍应能确认关闭旧预览并收尾。
    monkeypatch.setattr(native, "child_session", lambda: None)
    assert await service.close_status(7, "confirmed", attempt_id=uuid4()) == (
        False,
        None,
        True,
    )


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
@pytest.mark.asyncio
async def test_desktop_close_reservation_expires_after_controller_loss(monkeypatch):
    from uuid import uuid4

    from app.utils.windows.desktop_session import inventory, native

    service = lifecycle._DesktopSessionLifecycle()
    service.set_process_scope(session_id=7, connecting=False)
    monkeypatch.setattr(native, "child_session", lambda: 7)
    monkeypatch.setattr(native, "session_state", lambda _: 0)
    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: False)
    monkeypatch.setattr(lifecycle, "monotonic", lambda: 5.0)
    attempt = uuid4()
    assert await service.close_status(7, "idle", attempt_id=attempt) == (
        False,
        False,
        True,
    )

    # 客户端未能发送释放；随后其他程序使重新检查不能开始注销。
    monkeypatch.setattr(inventory, "has_unmanaged_processes", lambda _: True)
    monkeypatch.setattr(
        lifecycle, "monotonic", lambda: 5.0 + lifecycle._CLOSE_RESERVATION_SECONDS
    )
    assert await service.close_status(7, "idle", attempt_id=uuid4()) == (
        False,
        True,
        False,
    )
    assert service._connected_target().session_id == 7


@pytest.mark.skipif(os.name != "nt", reason="桌面分身仅在 Windows 使用 WTS")
def test_desktop_inventory_ignores_mas_jobs_but_not_external_apps(monkeypatch):
    from app.utils.windows.desktop_session import inventory

    rows = [
        (1, 20, "unrelated.exe", None),
        (7, 21, "executor.exe", None),
        (7, 22, "owned-game.exe", None),
        (7, 23, "explorer.exe", None),
    ]
    monkeypatch.setattr(inventory.win32ts, "WTSEnumerateProcesses", lambda *_: rows)
    monkeypatch.setattr(inventory, "supervised_processes", lambda _: {21})
    monkeypatch.setattr(inventory, "desktop_task_processes", lambda _: {22})
    monkeypatch.setattr(inventory, "process_session", lambda _: 7)
    monkeypatch.setattr(inventory, "_windows_shell", lambda pid, *_: pid == 23)
    assert inventory.has_unmanaged_processes(7) is False
    rows.append((7, 24, "user-app.exe", None))
    assert inventory.has_unmanaged_processes(7) is True


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 分身进程执行器")
@pytest.mark.parametrize("created", [None, 124.0, 123.0])
def test_desktop_window_operation_skips_gone_or_reused_process(monkeypatch, created):
    from app.utils.windows.desktop_session import process_worker

    target = None if created is None else Mock(spec=psutil.Process, pid=101)
    if target is not None:
        target.create_time.return_value = created
        target.is_running.return_value = False
    monkeypatch.setattr(operations, "managed_process", lambda pid, **_: target)

    def exited(pid):
        if pid == 101:
            raise OSError(0, "ProcessIdToSessionId", None, 87)
        return 7

    session_lookup = Mock(side_effect=exited)
    monkeypatch.setattr(process_worker, "process_session", session_lookup)
    assert (
        process_worker.run_window_action(
            "close_process_window", {"pid": "101", "createTime": 123.0}
        )
        == 1
    )
    looked_up_target = any(args == (101,) for args, _ in session_lookup.call_args_list)
    assert looked_up_target is (created == 123.0)


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 分身宿主")
def test_desktop_host_disconnects_without_logging_off_on_eof(monkeypatch):
    from app.core.desktop_session.host import Host

    host = Host.__new__(Host)
    host.dead = True
    host.viewer = None
    host.session_id = 7
    monkeypatch.setattr(host, "read_commands", lambda: None)
    monkeypatch.setattr(host, "report", Mock())
    close = Mock()
    monkeypatch.setattr(host, "close", close)
    host.run()
    close.assert_called_once_with(logoff=False)


@pytest.mark.asyncio
async def test_script_session_support_reads_resources_off_the_event_loop(
    monkeypatch, tmp_path
):
    from threading import get_ident

    from app.models.config import MaaEndConfig
    from app.task.MaaEnd import resource_loader

    caller = get_ident()

    def load(*_):
        assert get_ident() != caller
        return "Win32"

    monkeypatch.setattr(resource_loader, "load_maaend_controller_protocol", load)
    config = MaaEndConfig.build(payload={"Info": {"Path": str(tmp_path)}})
    await config.activate()
    assert await lifecycle.query_task_reason(config) is None
