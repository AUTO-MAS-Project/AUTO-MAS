"""任务停止先等待更新确认，确认结束后只清理本任务进程。"""

import asyncio
import sys
import uuid
from contextlib import suppress

import pytest

from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.core.task_manager import _TaskManager
from app.models.task import TaskItem, TaskMode
from app.utils.common.process.runner import create_subprocess
from tests.support.task_stop import StopTask


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

    class ControlledTask(StopTask):
        async def main_task(self):
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
            # 已经启动的句柄也须登记到本任务的进程组。
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
        ControlledTask,
        "STOP_CHECK_TIMEOUTS",
        {"update": 0.1 if times_out else 2, "finalize": 2},
    )
    uid = uuid.uuid4()
    info = TaskItem(uid=uid, info={"mode": TaskMode.AUTO_PROXY})

    task = ControlledTask(info)
    manager = _TaskManager()
    manager._running[uid] = task.execution
    task.start()
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
        for process in owned:
            for fd in (0, 1, 2):
                assert process._transport.get_pipe_transport(fd).is_closing()
        with pytest.raises(asyncio.CancelledError):
            with task._stop_scope.updating():
                pass
    finally:
        allow_exit.set()
        if not task.accomplish.is_set():
            task.request_stop()
        if task._task is not None:
            await asyncio.gather(task._task, return_exceptions=True)
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        for process in [*owned, unrelated]:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
