"""停止确认与晚到句柄、安装锁及进程级检测记录的协作。"""

import asyncio
import sys
import threading
import time
import uuid
from contextlib import suppress
from datetime import date, datetime, timezone

import pytest

from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.models.task import (
    LogRecord,
    ScriptItem,
    TaskExecuteBase,
    TaskItem,
    TaskMode,
    UserItem,
)
from app.services import script_install
from app.task.base import ScriptAutoProxyBase
from app.utils.common.process import runner
from tests.task_stop_support import StopTask, add_script


def start_task(operation):
    class ControlledTask(StopTask):
        async def main_task(self):
            await operation(self)

    info = TaskItem(info={"mode": TaskMode.AUTO_PROXY})
    task = ControlledTask(info)
    task.start()
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
            self.script_info = ScriptItem(
                script_id=script_id, name="test", status="运行"
            )
            self.cur_user_item = UserItem(user_id="u", name="test", status="运行")
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
        task.request_stop()
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
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)


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
        task.request_stop()
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
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
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
        task.request_stop()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert all(not item.done() for item in pending)
        release.set()
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 2)
        # 句柄交回后完成回调才继续回收；必须核对真实退出，不能抢读退出通知。
        await asyncio.wait_for(created[0].wait(), 2)
        assert created[0].returncode is not None
    finally:
        release.set()
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
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
        task.request_stop()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert not cleanup_calls
        await asyncio.wait_for(created[0].wait(), 2)
    finally:
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)


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


@pytest.mark.asyncio
async def test_file_worker_retains_lock_after_task_stop_until_thread_really_exits(
    tmp_path,
):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    def copy_files(cancelled):
        entered.set()
        try:
            assert release.wait(5)
            (tmp_path / "copied").write_text("complete")
            raise InterruptedError("stopped after blocking file operation")
        finally:
            stopped.set()

    async def run(task):
        task._stop_scope.checks[0].timeout = 0.02

        async def install():
            with script_install.installation_access(tmp_path):
                await script_install.run_worker(copy_files)

        await run_script_update(ScriptUpdateRequest("s", "BAAH"), install)

    task = start_task(run)
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        task.request_stop()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert not stopped.is_set()
        with pytest.raises(script_install.InstallUnsafeError):
            with script_install.installation_access(tmp_path):
                pytest.fail("file writer lost its lock while still writing")
        release.set()
        async with asyncio.timeout(2):
            while True:
                try:
                    script_install.assert_no_pending_process(tmp_path)
                    break
                except script_install.InstallUnsafeError:
                    await asyncio.sleep(0.01)
        with script_install.installation_access(tmp_path):
            assert (tmp_path / "copied").read_text() == "complete"
    finally:
        release.set()
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
        assert await asyncio.to_thread(stopped.wait, 2)


@pytest.mark.asyncio
async def test_maafw_prepare_retains_reservation_after_forced_stop(
    monkeypatch, tmp_path
):
    from app.models.config import MaaFWConfig
    from app.task.MaaFW import embedded_manager as module
    from app.task.MaaFW.tools.embedded.project_path import (
        release_project_path,
        try_reserve_project_path,
    )

    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    def prepare(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5)
            return False
        finally:
            stopped.set()

    monkeypatch.setattr(
        module.MaaFWEmbeddedManager,
        "_prepare_project_environment_sync",
        staticmethod(prepare),
    )
    monkeypatch.setattr(module, "resolve_maafw_project_root", lambda *args: tmp_path)
    monkeypatch.setattr(
        module.MaaFWEmbeddedManager, "_resolve_update_proxy", lambda self: (None, None)
    )
    config = MaaFWConfig()

    async def run(task):
        item = await add_script(task.task_info, str(uuid.uuid4()))
        manager = module.MaaFWEmbeddedManager(item)
        manager.script_config = config
        await manager._ensure_project_environment("BeforeRun")

    task = start_task(run)
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        task.request_stop()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        assert not stopped.is_set()
        key = await try_reserve_project_path(tmp_path)
        if key is not None:
            await release_project_path(key)
        assert key is None
        release.set()
        async with asyncio.timeout(2):
            while (key := await try_reserve_project_path(tmp_path)) is None:
                await asyncio.sleep(0.01)
        await release_project_path(key)
    finally:
        release.set()
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
        assert await asyncio.to_thread(stopped.wait, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("times_out", [False, True])
async def test_started_account_finalizer_saves_history_once_with_bounded_confirmation(
    monkeypatch, isolated_app_paths, times_out
):
    import app.core.history as history_module
    import app.task.history_core as manager_module
    from app.models.schema import HistoryWrite

    store = history_module.HistoryStore()
    await store.initialize(video_limit_bytes=1024 * 1024)
    monkeypatch.setattr(manager_module, "History", store)
    entered, release = asyncio.Event(), asyncio.Event()

    class Account(TaskExecuteBase):
        wait_for_finalizer_on_cancel = True
        stop_finalizer_timeout = 0.02 if times_out else 2

        async def main_task(self):
            pass

        async def final_task(self):
            entered.set()
            await release.wait()
            await self.history.save_user_history(
                [
                    HistoryWrite(
                        time=datetime(2026, 1, 2, tzinfo=timezone.utc),
                        username="u",
                        script_name="s",
                        status="success",
                        message="completed",
                        logs="done",
                    )
                ],
                script=self.script,
                user=self.user,
            )

        async def on_crash(self, error):
            raise error

    account = Account()

    async def run(task):
        account.info = task.task_info
        account.script = await add_script(task.task_info, "s", "u")
        account.user = account.script.user_list[0]
        await task.spawn(account)

    task = start_task(run)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.request_stop()
        if not times_out:
            # 让停止驱动真正开始，再完成账号本地收尾。
            await asyncio.sleep(0.02)
            release.set()
        await asyncio.wait_for(task.accomplish.wait(), 3)
        release.set()
        await asyncio.gather(task._task, return_exceptions=True)
        result = await store.search(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 3), mode="DAILY"
        )
        entries = [
            entry
            for scripts in result.values()
            for bucket in scripts.values()
            for entry in bucket.index
        ]
        assert len(entries) == (0 if times_out else 1)
        check = next(
            c for c in task._stop_scope.checks if c.name.startswith("finalize:")
        )
        assert check.status == ("timed_out" if times_out else "passed")
    finally:
        release.set()
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("late_success", [False, True])
async def test_cancelled_runner_preparation_releases_successful_resource_once(
    monkeypatch, tmp_path, late_success
):
    from app.task.MaaFW.tools.core.runner import environment
    from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService
    from app.task.MaaFW.tools.core.runtime_pool import binding
    from app.task.MaaFW.tools.embedded.runner_task import (
        _abandon_environment_preparation,
    )

    entered, release, released = threading.Event(), threading.Event(), threading.Event()
    cancelled = threading.Event()
    active_leases, release_calls = set(), []

    class Pool:
        root = tmp_path

        def release_lease(self, runtime_id, lease_id):
            active_leases.remove(lease_id)
            release_calls.append((runtime_id, lease_id))
            released.set()

    monkeypatch.setattr(environment, "MaaFWRuntimePool", lambda root: Pool())
    service = MaaFWRunnerService()
    # 一个引用属于本次准备，另一个属于无关使用者，用来核对没有重复释放。
    binding.retain_binding(tmp_path, "1.0")

    def prepare():
        active_leases.add("lease")
        binding.retain_binding(tmp_path, "1.0")
        entered.set()
        if late_success:
            assert release.wait(5)
        return environment.MaaFWRunnerEnvironment(
            python_executable=tmp_path / "python",
            venv_path=tmp_path,
            env={},
            packages=(),
            maafw_version="1.0",
            runtime_id="runtime",
            lease_id="lease",
            runtime_pool_root=tmp_path,
            binding_version="1.0",
        )

    async def run(task):
        task._stop_scope.checks[0].timeout = 0.03
        preparation = asyncio.create_task(
            task._stop_scope.run_update_worker(
                prepare,
                cancel=cancelled.set,
                release_cancelled=service.release_environment,
            )
        )
        try:
            await asyncio.shield(preparation)
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await _abandon_environment_preparation(
                preparation,
                release=service.release_environment,
                grace_seconds=0,
            )
            raise

    task = start_task(run)
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.01)
            if not late_success:
                await task._stop_scope._updates_idle.wait()
        task.request_stop()
        await asyncio.wait_for(task.accomplish.wait(), 2)
        if late_success:
            assert cancelled.is_set()
            assert active_leases == {"lease"}
        release.set()
        async with asyncio.timeout(3):
            while not released.is_set():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(
            asyncio.gather(
                *tuple(task._stop_scope.retained_workers), return_exceptions=True
            ),
            3,
        )
        assert not active_leases
        assert release_calls == [("runtime", "lease")]
        assert binding.retained_versions(tmp_path) == {"1.0"}
        binding.release_binding(tmp_path, "1.0")
        assert not binding.retained_versions(tmp_path)
    finally:
        release.set()
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
