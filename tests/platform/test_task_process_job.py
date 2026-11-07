"""任务进程组可在 Runtime 的外层 Job 中运行和强制清理。"""

import asyncio
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="验证 Windows Runtime 的嵌套 Job")
@pytest.mark.parametrize("breakaway", [False, True])
async def test_task_job_inside_runtime_job(breakaway):
    import psutil
    import win32api
    import win32con
    import win32job
    import win32process

    outer = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK
    )
    win32job.SetInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation, info
    )
    code = textwrap.dedent(f"""
        import asyncio,sys
        from app.utils.common.process.runner import create_subprocess
        from app.utils.common.process.scope import TaskProcessScope,current_process_scope
        async def main():
            scope=TaskProcessScope()
            unrelated=await asyncio.create_subprocess_exec(sys._base_executable,'-c','import time; time.sleep(30)')
            token=current_process_scope.set(scope)
            try:
                owned=await create_subprocess(sys._base_executable,'-c','import time; time.sleep(30)',breakaway={breakaway!r})
            finally:
                current_process_scope.reset(token)
            await scope.run_checks()
            await scope.force_close()
            await asyncio.wait_for(owned.wait(),3)
            assert unrelated.returncode is None
            unrelated.kill()
            await unrelated.wait()
            print('runtime-job-compatible',flush=True)
        asyncio.run(main())
    """)
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW,
    )
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, process.pid
        )
        try:
            win32job.AssignProcessToJobObject(outer, handle)
        finally:
            handle.Close()
        for thread in psutil.Process(process.pid).threads():
            handle = win32api.OpenThread(
                win32con.THREAD_SUSPEND_RESUME, False, thread.id
            )
            try:
                win32process.ResumeThread(handle)
            finally:
                handle.Close()
        stdout, stderr = await asyncio.to_thread(process.communicate, timeout=15)
        assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
        assert b"runtime-job-compatible" in stdout
    finally:
        win32job.TerminateJobObject(outer, 1)
        outer.Close()
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait, timeout=5)
