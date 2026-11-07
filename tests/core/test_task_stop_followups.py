"""停止确认与晚到句柄、安装锁及进程级检测记录的协作。"""

import asyncio
import sys
import threading
import time
import uuid
from contextlib import suppress

import pytest

from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.core.task_manager.manager import Task, TaskInfo
from app.models.task import LogRecord, ScriptItem, UserItem
from app.services import script_install
from app.task.base import ScriptAutoProxyBase
from app.utils.common.process import runner


def start_task(operation):
    class ControlledTask(Task):
        async def _run_main_task(self):
            await operation(self)

    info = TaskInfo("AutoProxy", str(uuid.uuid4()), None, None, None)
    task = ControlledTask(info, [], manager_factories={})
    task.execute()
    return task


@pytest.mark.asyncio
async def test_task_stop_preserves_inflight_maintenance_until_thread_exits():
    entered, release = threading.Event(), threading.Event()
    calls = []
    script_id = str(uuid.uuid4())

    def detect():
        calls.append(True)
        entered.set()
        assert release.wait(5)
        return None

    class Proxy(ScriptAutoProxyBase):
        run_timeout_seconds = 10

        def __init__(self):
            super().__init__()
            self.script_info = ScriptItem(script_id, "test", "运行")
            self.cur_user_item = UserItem("u", "test", "运行")
            self.cur_user_log = LogRecord()

        async def main_task(self):
            await self.skip_on_game_maintenance(detect)

        async def final_task(self):
            pass

        async def on_crash(self, error):
            raise error

    proxy = Proxy()

    async def run(task):
        await task.spawn(proxy)

    task = start_task(run)
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        await asyncio.wait_for(proxy.accomplish.wait(), 2)
        assert await Proxy()._detect_game_maintenance(detect) is None
        assert len(calls) == 1
        release.set()
        from app.task.base import _INFLIGHT_DETECTIONS

        await asyncio.wait_for(_INFLIGHT_DETECTIONS[script_id], 2)
        assert await Proxy()._detect_game_maintenance(detect) is None
        assert len(calls) == 2
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["src", "bettergi"])
@pytest.mark.parametrize("grace", [0.02, 1.0])
async def test_update_deadline_kills_installer_before_releasing_install_lock(
    monkeypatch, tmp_path, engine, grace
):
    if engine == "src":
        from app.task.SRC.tools import program_update as update

        monkeypatch.setattr(update, "_WRITE_CLEANUP_SECONDS", grace, raising=False)

        async def install():
            await update.command("installer", cwd=tmp_path, writing=True)
    else:
        from app.task.BetterGI.tools import program_update as update

        monkeypatch.setattr(update, "_INSTALLER_CLEANUP_SECONDS", grace, raising=False)

        async def install():
            await update.run_installer(tmp_path / "installer.exe", tmp_path)

    ready, update_ended = asyncio.Event(), asyncio.Event()
    owned = []

    async def launch(*args, **kwargs):
        process = await runner.create_subprocess(
            sys.executable, "-I", "-c", "import time; time.sleep(30)", **kwargs
        )
        owned.append(process)
        ready.set()
        return process

    monkeypatch.setattr(update, "create_subprocess", launch)

    async def run(task):
        task._stop_scope.checks[0].timeout = 0.3

        async def perform():
            try:
                with script_install.installation_access(tmp_path):
                    await install()
            finally:
                update_ended.set()

        await run_script_update(ScriptUpdateRequest("s", "SRC"), perform)

    task = start_task(run)
    try:
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        if grace < 0.3:
            await asyncio.wait_for(update_ended.wait(), 1)
            assert owned[0].returncode is None
            with pytest.raises(script_install.InstallUnsafeError):
                with script_install.installation_access(tmp_path):
                    pytest.fail("still-running installation released its lock")
        await asyncio.wait_for(task.accomplish.wait(), 3)
        await asyncio.wait_for(owned[0].wait(), 2)
        assert task._stop_scope.checks[0].status == "timed_out"
        async with asyncio.timeout(2):
            while True:
                try:
                    script_install.assert_no_pending_process(tmp_path)
                    break
                except script_install.InstallUnsafeError:
                    await asyncio.sleep(0.01)
        with script_install.installation_access(tmp_path):
            pass
    finally:
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)
        for process in owned:
            if process.returncode is None:
                process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_stop_deadline_keeps_late_creation_reapable(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    created = []
    pending = []
    real_create = runner.create_subprocess

    async def delayed(*args, **kwargs):
        process = await real_create(*args, **kwargs)
        created.append(process)
        pending.append(asyncio.current_task())
        entered.set()
        await release.wait()
        return process

    monkeypatch.setattr(runner, "create_subprocess", delayed)

    async def run(task):
        await runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            kill_tree_on_cancel=True,
        )

    task = start_task(run)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert all(not item.done() for item in pending)
        release.set()
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 2)
        assert created[0].returncode is not None
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)
        for process in created:
            if process.returncode is None:
                process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_cleanup_deadline_preserves_standard_cancellation(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original_create = runner.create_subprocess
    owned = []
    monkeypatch.setattr(runner, "_PROCESS_CLEANUP_SECONDS", 0.04, raising=False)

    def blocked_cleanup(*args, **kwargs):
        entered.set()
        assert release.wait(5)

    async def create(*args, **kwargs):
        process = await original_create(*args, **kwargs)
        owned.append(process)
        return process

    monkeypatch.setattr(runner, "_terminate_process_tree", blocked_cleanup)
    monkeypatch.setattr(runner, "create_subprocess", create)
    operation = asyncio.create_task(
        runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            kill_tree_on_cancel=True,
        )
    )
    try:
        async with asyncio.timeout(3):
            while not owned:
                await asyncio.sleep(0.01)
        started = time.monotonic()
        operation.cancel()
        async with asyncio.timeout(1):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        for _ in range(4):
            operation.cancel()
            await asyncio.sleep(0.005)
        with pytest.raises(asyncio.CancelledError) as failure:
            await asyncio.wait_for(operation, 0.5)
        assert runner.is_process_cleanup_unconfirmed(failure.value)
        assert time.monotonic() - started < 0.5
        for fd in (1, 2):
            assert owned[0]._transport.get_pipe_transport(fd).is_closing()
    finally:
        release.set()
        for process in owned:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.asyncio
async def test_force_stopped_modavd_does_not_restart_instance_cleanup(monkeypatch):
    from app.utils.common.emulator2.avd import cli

    ready = asyncio.Event()
    created = []
    cleanup_calls = []
    real_create = runner.create_subprocess

    async def create(*args, **kwargs):
        process = await real_create(*args, **kwargs)
        created.append(process)
        ready.set()
        return process

    async def blocked_handler(process):
        cleanup_calls.append(True)
        await asyncio.Event().wait()

    monkeypatch.setattr(runner, "create_subprocess", create)

    async def run(task):
        await cli._run_process(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
            60,
            blocked_handler,
        )

    task = start_task(run)
    try:
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert not cleanup_calls
        await asyncio.wait_for(created[0].wait(), 2)
    finally:
        task.cancel()
        await asyncio.gather(task._execution_root, return_exceptions=True)


@pytest.mark.asyncio
async def test_modavd_timeout_bounds_instance_cleanup_handler(monkeypatch):
    from app.utils.common.emulator2.avd import cli

    monkeypatch.setattr(cli, "STOP_PROCESS_TIMEOUT_SECONDS", 0.02)
    handlers = []

    async def blocked_handler(process):
        handlers.append(True)
        await asyncio.Event().wait()

    started = time.monotonic()
    with pytest.raises(cli.CLIError) as failure:
        await cli._run_process(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
            0.03,
            blocked_handler,
        )
    assert failure.value.code == "timeout"
    assert handlers
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_deferred_install_lock_excludes_another_backend(tmp_path):
    completion = asyncio.get_running_loop().create_future()
    code = (
        "import sys; from pathlib import Path; from app.services import script_install as s\n"
        "try:\n"
        "    with s.installation_access(Path(sys.argv[1])): pass\n"
        "except s.InstallUnsafeError: sys.exit(3)\n"
    )

    async def another_backend():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            str(tmp_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await asyncio.wait_for(process.wait(), 5)

    try:
        with script_install.installation_access(tmp_path):
            script_install.defer_installation_release(tmp_path, completion)
        assert await another_backend() == 3
        completion.set_result(None)
        await asyncio.sleep(0)
        assert await another_backend() == 0
    finally:
        if not completion.done():
            completion.set_result(None)
        await asyncio.sleep(0)


def test_src_config_restore_respects_installation_access(tmp_path):
    from app.task.SRC.tools.backup_archive import restore_native_backup

    config = tmp_path / "config"
    config.mkdir()
    with script_install.installation_access(tmp_path):
        with pytest.raises(script_install.InstallUnsafeError):
            restore_native_backup(config, "missing", "s")
