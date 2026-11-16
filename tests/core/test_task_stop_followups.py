"""停止确认与晚到句柄、安装锁及进程级检测记录的协作。"""

import asyncio
import sys
import threading

import pytest

from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.models.task import (
    TaskItem,
    TaskMode,
)
from app.services import script_install
from tests.support.task_stop import StopTask


def start_task(operation):
    class ControlledTask(StopTask):
        async def main_task(self):
            await operation(self)

    info = TaskItem(info={"mode": TaskMode.AUTO_PROXY})
    task = ControlledTask(info)
    task.start()
    return task


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
