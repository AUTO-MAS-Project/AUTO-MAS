"""任务停止先等待更新确认，确认结束后只清理本任务进程。"""

import asyncio
import json
import sys
import threading
import uuid
import weakref
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psutil
import pytest

from app.core.runtime_tasks import OwnedTaskRegistry
from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.core.task_manager.manager import Task, TaskInfo, _TaskManager
from app.core.timer import _MainTimer
from app.models.config import MaaConfig, MaaUserConfig
from app.models.task import ScriptItem, UserItem
from app.utils.common.process.runner import ProcessRunner, create_subprocess
from app.utils.common.process.scope import TaskProcessScope, current_process_scope


@pytest.mark.asyncio
@pytest.mark.parametrize("shutdown", ["delayed_exit", "stuck_window", "stuck_process"])
@pytest.mark.parametrize("base", ["native", "shared"])
async def test_maa_config_stop_saves_before_kill_or_reports_timeout(
    monkeypatch, tmp_path, shutdown, base
):
    import importlib

    module = importlib.import_module("app.task.MAA.ScriptConfig")
    process_module = importlib.import_module("app.utils.common.process.manager")
    host = tmp_path / "mas"
    host.mkdir()
    monkeypatch.chdir(host)
    ready = asyncio.Event()
    install = tmp_path / "maa"
    output = install / "config" / "gui.new.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"Gui":{"custom":"original"}}', encoding="utf-8")
    window_closed = tmp_path / "window-closed"
    unresponsive = shutdown != "delayed_exit"
    shutdown_code = {
        "delayed_exit": (
            "p=Path(sys.argv[1]); d=json.loads(p.read_text(encoding='utf-8-sig')); "
            "d.setdefault('Gui', {})['custom']='saved'; "
            "p.write_text(json.dumps(d), encoding='utf-8'); "
            "Path(sys.argv[2]).touch(); time.sleep(1)"
        ),
        "stuck_window": "time.sleep(30)",
        "stuck_process": "Path(sys.argv[2]).touch(); time.sleep(30)",
    }[shutdown]

    class GuiProcess(process_module.ProcessManager):
        async def open_process(self, path):
            self.process = await create_subprocess(
                sys.executable,
                "-I",
                "-c",
                "import sys,time,json; from pathlib import Path; sys.stdin.readline(); "
                + shutdown_code,
                str(output),
                str(window_closed),
                stdin=asyncio.subprocess.PIPE,
            )
            ready.set()

    def close_window(hwnd):
        child = session.maa_process_manager.process
        assert child is not None and child.stdin is not None
        child.stdin.write(b"close\n")
        return True

    monkeypatch.setattr(module, "ProcessManager", GuiProcess)
    # 只替换窗口边界；保留真实 close()，覆盖窗口先消失、进程稍后退出的间隔。
    monkeypatch.setattr(
        process_module,
        "get_main_window_handle",
        lambda *args: None if window_closed.exists() else 1,
    )
    monkeypatch.setattr(process_module.window, "close_window", close_window)
    monkeypatch.setattr(module.System, "kill_process", AsyncMock())
    monkeypatch.setattr(
        module.ScriptConfigTask,
        "GUI_CLOSE_TIMEOUT",
        0.5 if unresponsive else 2,
        raising=False,
    )
    user_id = uuid.uuid4()
    script = ScriptItem(
        str(uuid.uuid4()), "test", "运行", [UserItem(str(user_id), "test", "运行")], 0
    )
    info = TaskInfo(
        "ScriptConfig", str(uuid.uuid4()), None, script.script_id, str(user_id)
    )
    object.__setattr__(script, "_task_item_ref", weakref.ref(info))
    config = MaaConfig.build(payload={"Info": {"Path": str(install)}})
    user = MaaUserConfig.build(payload={"Info": {"Base": base}})
    await config.activate()
    await user.activate()
    session = module.ScriptConfigTask(script, config, {user_id: user}, None)
    discarded = AsyncMock()
    monkeypatch.setattr(session, "_notify_config_discarded", discarded)

    class ConfigTask(Task):
        async def _run_main_task(self):
            await self.spawn(session)

    task = ConfigTask(info, [], manager_factories={})
    task.execute()
    try:
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 3)
        await asyncio.wait_for(session.accomplish.wait(), 3)
        await asyncio.wait_for(session.maa_process_manager.process.wait(), 3)
        saved = (
            output
            if base == "native"
            else (
                host
                / "data"
                / script.script_id
                / "Default"
                / "ConfigFile"
                / "gui.new.json"
            )
        )
        document = json.loads(saved.read_text(encoding="utf-8-sig"))
        if unresponsive:
            assert document.get("Gui", {}).get("custom") != "saved"
            discarded.assert_awaited_once_with("not_written")
        else:
            assert document["Gui"]["custom"] == "saved"
            discarded.assert_not_awaited()
        check = next(c for c in task._stop_scope.checks if c.name == "maa_config_save")
        assert check.status == ("timed_out" if unresponsive else "passed")
    finally:
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)


@pytest.mark.asyncio
async def test_task_stop_during_display_insert_preserves_guard_ownership(monkeypatch):
    import importlib

    module = importlib.import_module("app.core.desktop_guard")
    from app.utils import vdd

    entered, release = threading.Event(), threading.Event()
    recorded, removed = [], []

    class Display:
        index = 7
        applied_mode = (1920, 1080, 60)

        def __init__(self, *, mode):
            pass

        def __enter__(self):
            entered.set()
            assert release.wait(5)
            return self

        def close(self):
            removed.append(self.index)

    monkeypatch.setattr(vdd, "VirtualDisplay", Display)
    monkeypatch.setattr(vdd, "probe", lambda: SimpleNamespace(status=vdd.VddStatus.OK))
    monkeypatch.setattr(module, "_describe", lambda: "test")
    monkeypatch.setattr(module, "_has_real_output", lambda: True)
    monkeypatch.setattr(module, "_desktop_has_room", lambda: True)
    monkeypatch.setattr(module, "_write_state", recorded.append)
    monkeypatch.setattr(module, "_clear_state", lambda: None)
    guard = module._DesktopGuard()
    monkeypatch.setattr(guard, "_sync_display_hold", lambda: None)

    class DisplayTask(Task):
        async def _run_main_task(self):
            await guard._attach("test")

    info = TaskInfo("AutoProxy", str(uuid.uuid4()), None, None, None)
    task = DisplayTask(info, [], manager_factories={})
    task.execute()
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        release.set()
        await asyncio.wait_for(guard._attaching, 2)
        assert recorded == [7]
        assert guard._display is not None
        await guard._teardown("test")
        assert removed == [7]
    finally:
        release.set()
        await asyncio.gather(task._execution_root, return_exceptions=True)
        if guard._attaching is not None:
            await asyncio.gather(guard._attaching, return_exceptions=True)


@pytest.mark.asyncio
async def test_each_stop_check_has_an_independent_timeout():
    scope = TaskProcessScope()
    release = asyncio.Event()

    async def slow():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    async def quick():
        await asyncio.sleep(0.03)

    scope.add_check("slow", slow, timeout=0.01)
    scope.add_check("quick", quick, timeout=0.5)
    try:
        async with asyncio.timeout(1):
            await scope.run_checks()
        assert [check.status for check in scope.checks] == ["timed_out", "passed"]
    finally:
        release.set()
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows 保留已退出父进程的 PPID")
async def test_force_stop_reaps_worker_after_wrapper_exited(tmp_path):
    scope = TaskProcessScope()
    pid_file = tmp_path / "worker.pid"
    code = (
        "import subprocess,sys; from pathlib import Path; "
        "worker=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'],"
        "stdout=sys.stdout,stderr=sys.stderr); "
        "Path(sys.argv[1]).write_text(str(worker.pid))"
    )
    token = current_process_scope.set(scope)
    process = None
    worker = None
    try:
        process = await create_subprocess(
            sys.executable,
            "-I",
            "-c",
            code,
            str(pid_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        scope.track(psutil.Process(process.pid))
        current_process_scope.reset(token)
        token = None
        async with asyncio.timeout(5):
            while not pid_file.exists() or process.returncode is None:
                await asyncio.sleep(0.01)
        worker = psutil.Process(int(pid_file.read_text()))
        assert worker.is_running()
        await scope.run_checks()
        await scope.force_close()
        await asyncio.to_thread(worker.wait, timeout=3)
        assert not worker.is_running()
        assert process._transport.get_pipe_transport(1).is_closing()
    finally:
        if token is not None:
            current_process_scope.reset(token)
        if worker is not None:
            with suppress(psutil.NoSuchProcess):
                worker.kill()
        if process is not None:
            if process.returncode is None:
                process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_update_cleanup_error_is_not_reported_as_confirmed():
    scope = TaskProcessScope()
    started = asyncio.Event()

    async def update():
        with scope.updating():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                raise RuntimeError("writer state unknown")

    task = asyncio.create_task(update())
    await started.wait()
    scope.add_check("update", scope.stop_updates, timeout=1)
    await scope.run_checks()
    assert scope.checks[0].status == "failed"
    await asyncio.gather(task, return_exceptions=True)
    await scope.force_close()


@pytest.mark.asyncio
async def test_new_confirmation_checks_also_register_their_processes():
    scope = TaskProcessScope()
    process = None

    async def check():
        nonlocal process
        process = await create_subprocess(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            stdout=asyncio.subprocess.PIPE,
        )
        await asyncio.Event().wait()

    scope.add_check("future-check", check, timeout=0.5)
    try:
        await scope.run_checks()
        assert scope.checks[0].status == "timed_out"
        assert process is not None and process.returncode is None
        await scope.force_close()
        await asyncio.wait_for(process.wait(), 3)
        assert process._transport.get_pipe_transport(1).is_closing()
    finally:
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("times_out", [False, True])
@pytest.mark.parametrize("update_in_main", [False, True])
async def test_task_stop_waits_for_update_then_force_closes_owned_processes(
    monkeypatch, times_out, update_in_main
):
    update_started, cleaning, allow_exit, ready = (asyncio.Event() for _ in range(4))
    owned = []
    # 任务外进程必须不受停止操作影响。
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-c", "import time; time.sleep(30)"
    )
    finalized = asyncio.Event()

    class ControlledTask(Task):
        async def _run_main_task(self):
            owned.append(
                await create_subprocess(
                    sys.executable,
                    "-I",
                    "-c",
                    "import time; time.sleep(30)",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            )
            # 已有句柄也可以登记归属，不要求重新加入系统 Job。
            adopted = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                "-c",
                "import time; time.sleep(30)",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._stop_scope.track(adopted)
            owned.append(adopted)

            async def update():
                try:
                    update_started.set()
                    ready.set()
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await allow_exit.wait()

            if update_in_main:
                await run_script_update(ScriptUpdateRequest("s", "MAA"), update)
                return
            asyncio.create_task(
                run_script_update(ScriptUpdateRequest("s", "MAA"), update)
            )
            await update_started.wait()
            ready.set()
            await asyncio.Event().wait()

        async def final_task(self):
            await super().final_task()
            finalized.set()

        async def on_crash(self, error):
            raise error

    monkeypatch.setattr(
        ControlledTask, "STOP_CHECK_TIMEOUTS", {"update": 0.1 if times_out else 2}
    )
    uid = uuid.uuid4()
    info = TaskInfo("AutoProxy", str(uid), None, None, None)

    async def blocked_history_cleanup():
        await asyncio.Event().wait()

    monkeypatch.setattr(info, "discard_history_captures", blocked_history_cleanup)
    task = ControlledTask(info, [], manager_factories={})
    manager = _TaskManager()
    manager.task_handler[uid] = task
    task.execute()
    stopping = None
    try:
        await asyncio.wait_for(ready.wait(), 3)
        stopping = asyncio.create_task(manager.stop_task(str(uid)))
        await asyncio.wait_for(cleaning.wait(), 1)
        assert owned[0].returncode is None
        assert not task._stop_scope.finished.is_set()
        assert not finalized.is_set()
        if not times_out:
            allow_exit.set()
        async with asyncio.timeout(3):
            await stopping
            await asyncio.gather(*(process.wait() for process in owned))
        assert finalized.is_set()
        assert all(process.returncode is not None for process in owned)
        assert unrelated.returncode is None
        assert task._stop_scope.checks[0].status == (
            "timed_out" if times_out else "passed"
        )
        for process in owned:
            for fd in (0, 1, 2):
                assert process._transport.get_pipe_transport(fd).is_closing()
        with pytest.raises(asyncio.CancelledError):
            with task._stop_scope.updating():
                pass
    finally:
        allow_exit.set()
        if not task.accomplish.is_set():
            task.cancel()
        if task._execution_root is not None:
            await asyncio.gather(task._execution_root, return_exceptions=True)
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        for process in [*owned, unrelated]:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_application_background_tasks_are_not_owned_by_stopped_task():
    registry = OwnedTaskRegistry()
    entered = asyncio.Event()
    release = asyncio.Event()
    background = []

    async def shared_work():
        entered.set()
        await release.wait()
        return current_process_scope.get()

    class BackgroundTask(Task):
        async def _run_main_task(self):
            background.append(registry.spawn(shared_work(), name="test-shared-work"))
            await asyncio.Event().wait()

    info = TaskInfo("AutoProxy", str(uuid.uuid4()), None, None, None)
    task = BackgroundTask(info, [], manager_factories={})
    task.execute()

    try:
        await asyncio.wait_for(entered.wait(), 1)
        work = background[0]
        assert work is not None
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert not work.done()
        release.set()
        assert await work is None
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)
        await registry.shutdown()


@pytest.mark.asyncio
async def test_community_sign_is_independent_of_task_stop(monkeypatch):
    timer = _MainTimer()
    scope = TaskProcessScope()
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered = []

    async def shared_sign(*, source):
        assert source == "task_manual"
        assert current_process_scope.get() is None
        entered.set()
        await release.wait()
        return [{"ok": True}]

    monkeypatch.setattr(timer, "_has_pending_community_sign", lambda *, source: True)
    monkeypatch.setattr(timer, "try_community_for_task", shared_sign)
    token = current_process_scope.set(scope)
    try:
        timer.schedule_community_for_task(
            source="task_manual", on_completed=delivered.append
        )
    finally:
        current_process_scope.reset(token)

    work = timer.community_sign_task
    assert work is not None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert work.get_context().get(current_process_scope) is None
        await scope.force_close()
        assert not work.done()
        release.set()
        await work
        await asyncio.sleep(0)
        assert delivered == [[{"ok": True}]]
    finally:
        release.set()
        if not work.done():
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)


@pytest.mark.asyncio
async def test_explicit_cleanup_subprocess_is_allowed_after_task_scope_closes():
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    try:
        await scope.force_close()
        with pytest.raises(asyncio.CancelledError):
            await ProcessRunner.run_process(
                sys.executable, "-I", "-c", "print('blocked')", timeout=3
            )
        result = await ProcessRunner.run_process(
            sys.executable, "-I", "-c", "print('cleanup')", timeout=3, cleanup=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "cleanup"
        assert not scope._processes
    finally:
        current_process_scope.reset(token)
