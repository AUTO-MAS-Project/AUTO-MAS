"""混合启动仍保持 Runtime 归属，并完整回收任务进程树。"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import uuid
from contextlib import suppress

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 任务 Job")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launcher,first_breakaway,allow_breakaway,force_retry",
    [
        (launcher, first, allow, False)
        for launcher in ("async", "popen")
        for first in (False, True)
        for allow in (False, True)
    ]
    + [(launcher, True, True, True) for launcher in ("async", "popen")],
)
async def test_task_job_inside_runtime_job(
    launcher, first_breakaway, allow_breakaway, force_retry, record_property
):
    import ctypes

    import psutil
    import win32api
    import win32con
    import win32job
    import win32process

    name = f"AUTO_MAS_test_{uuid.uuid4().hex}"
    outer = win32job.CreateJobObject(None, name)
    info = win32job.QueryInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | (win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK if allow_breakaway else 0)
    )
    win32job.SetInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation, info
    )
    code = textwrap.dedent("""
        import asyncio,ctypes,json,subprocess,sys
        import psutil,win32api,win32con,win32job
        from app.utils import process_platform
        from app.utils.common.process.runner import create_subprocess
        from app.utils.common.process.scope import TaskProcessScope,current_process_scope

        async def main():
            name,launcher,first_breakaway,allow_breakaway,force_retry=json.loads(sys.argv[1])
            outer=win32job.OpenJobObject(win32job.JOB_OBJECT_QUERY,False,name)
            scope=TaskProcessScope()
            unrelated=await asyncio.create_subprocess_exec(
                sys._base_executable,'-I','-c','import time; time.sleep(30)')
            retry_pending=force_retry
            if force_retry:
                native_async=asyncio.create_subprocess_exec
                native_popen=subprocess.Popen

                def check_flags(flags):
                    nonlocal retry_pending
                    if retry_pending and flags & process_platform.platform_process.breakaway_flags:
                        retry_pending=False
                        error=PermissionError('injected CREATE_BREAKAWAY_FROM_JOB rejection')
                        error.winerror=5
                        raise error

                async def spawn_async(*args,**kwargs):
                    check_flags(kwargs.get('creationflags',0))
                    return await native_async(*args,**kwargs)

                def spawn_popen(*args,**kwargs):
                    check_flags(kwargs.get('creationflags',0))
                    return native_popen(*args,**kwargs)

                asyncio.create_subprocess_exec=spawn_async
                subprocess.Popen=spawn_popen
            token=current_process_scope.set(scope)
            owned=[]
            descendants=[]
            memberships=[]
            try:
                for index,breakaway in enumerate((first_breakaway,not first_breakaway,first_breakaway)):
                    delay=0 if index==0 else 30
                    payload=(
                        'import subprocess,sys,time; '
                        "child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'],"
                        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
                        f'print(child.pid,flush=True); time.sleep({delay})')
                    if launcher=='async':
                        process=await create_subprocess(
                            sys._base_executable,'-I','-c',payload,
                            breakaway=breakaway,stdout=subprocess.PIPE)
                        owned.append(process)
                        child_pid=int(await asyncio.wait_for(process.stdout.readline(),3))
                    else:
                        process=await asyncio.to_thread(
                            scope.popen,[sys._base_executable,'-I','-c',payload],
                            creationflags=process_platform.platform_process.breakaway_flags if breakaway else 0,
                            stdout=subprocess.PIPE)
                        owned.append(process)
                        child_pid=int(await asyncio.wait_for(asyncio.to_thread(process.stdout.readline),3))
                    descendants.append(psutil.Process(child_pid))
                    handle=win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION,False,child_pid)
                    try:
                        inherited=bool(win32job.IsProcessInJob(handle,outer))
                    finally:
                        handle.Close()
                    memberships.append(inherited)
                    expected=not breakaway or not allow_breakaway or (force_retry and index==0)
                    assert inherited == expected
                    if index==0:
                        if launcher=='async':
                            await asyncio.wait_for(process.wait(),3)
                        else:
                            await asyncio.to_thread(process.wait,timeout=3)
            finally:
                current_process_scope.reset(token)
                try:
                    await scope.force_close()
                    for process in owned:
                        if launcher=='async':
                            await asyncio.wait_for(process.wait(),3)
                        else:
                            await asyncio.to_thread(process.wait,timeout=3)
                    _,alive=await asyncio.to_thread(psutil.wait_procs,descendants,timeout=3)
                    assert not alive
                    assert unrelated.returncode is None
                    assert not retry_pending
                finally:
                    for child in descendants:
                        if child.is_running():
                            child.kill()
                    unrelated.kill()
                    await unrelated.wait()
                    outer.Close()
            print(json.dumps({'elevated':bool(ctypes.windll.shell32.IsUserAnAdmin()),
                              'memberships':memberships}),flush=True)
        asyncio.run(main())
    """)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            json.dumps([name, launcher, first_breakaway, allow_breakaway, force_retry]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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
        stdout, stderr = await asyncio.to_thread(process.communicate, timeout=20)
        assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
        result = json.loads(stdout)
        assert result["elevated"] == bool(ctypes.windll.shell32.IsUserAnAdmin())
        record_property("elevated", result["elevated"])
        assert len(result["memberships"]) == 3
    finally:
        win32job.TerminateJobObject(outer, 1)
        outer.Close()
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait, timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "child_before_registration,intermediate",
    [(False, False), (True, False), (False, True)],
)
async def test_adoption_reaps_descendants_but_never_a_looked_up_foreign_process(
    tmp_path, monkeypatch, child_before_registration, intermediate
):
    """接管进程的已有及后续子进程都须随任务停止，任务外进程不受影响。"""
    import psutil

    from app.utils.common.process.manager import ProcessInfo, ProcessManager
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    scope = TaskProcessScope()
    gate, pid_file, heartbeat = (
        tmp_path / name for name in ("gate", "pid", "heartbeat")
    )
    marker = f"mas-adoption-test-{uuid.uuid4().hex}"
    child_code = (
        "import os,sys,time; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(str(os.getpid())); "
        "p=Path(sys.argv[2]); "
        "\nfor i in range(600):\n p.write_text(str(i)); time.sleep(.02)"
    )
    launch = (
        "subprocess.Popen([sys.executable,'-I','-c',sys.argv[2],"
        "sys.argv[3],sys.argv[4],sys.argv[5]])"
    )
    if intermediate:
        wrapper = "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-c',*sys.argv[1:]])"
        launch = (
            f"subprocess.Popen([sys.executable,'-I','-c',{wrapper!r},sys.argv[2],"
            "sys.argv[3],sys.argv[4],sys.argv[5]])"
        )
    parent_code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "gate=Path(sys.argv[1]); "
        f"\ndef start():\n {launch}"
        "\nif sys.argv[6]=='before': start()"
        "\nwhile not gate.exists(): time.sleep(.01)"
        "\nif sys.argv[6]=='after': start()"
    )
    unrelated = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )
    parent = await asyncio.create_subprocess_exec(
        sys._base_executable,
        "-I",
        "-c",
        parent_code,
        str(gate),
        child_code,
        str(pid_file),
        str(heartbeat),
        marker,
        "before" if child_before_registration else "after",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    child = None
    output = asyncio.create_task(parent.communicate())
    try:
        # 只隔离宿主进程目录；身份、后代查询与 Job 操作仍使用真实进程。
        known = [psutil.Process(unrelated.pid), psutil.Process(parent.pid)]

        def iter_known(attrs):
            for process in known:
                process.info = process.as_dict(attrs=attrs)
                yield process

        monkeypatch.setattr(psutil, "process_iter", iter_known)
        if child_before_registration:
            async with asyncio.timeout(5):
                while not pid_file.exists():
                    await asyncio.sleep(0.01)
        token = current_process_scope.set(scope)
        try:
            observer = ProcessManager()
            await observer.search_process(
                ProcessInfo(pid=unrelated.pid), timeout_seconds=3, owned=False
            )
            manager = ProcessManager()
            await manager.search_process(ProcessInfo(pid=parent.pid), timeout_seconds=3)
        finally:
            current_process_scope.reset(token)
        gate.touch()
        async with asyncio.timeout(5):
            while (
                not pid_file.exists()
                or parent.returncode is None
                or not heartbeat.exists()
            ):
                await asyncio.sleep(0.01)
        child = psutil.Process(int(pid_file.read_text()))
        child.create_time()
        assert marker in child.cmdline()
        assert not output.done(), "子进程应仍占用父进程的输出管道"
        await asyncio.wait_for(scope.force_close(), timeout=3)
        _, alive = await asyncio.to_thread(psutil.wait_procs, [child], timeout=1)
        assert not alive, "接管的父进程退出后，其子进程仍然存活"
        before = heartbeat.read_text()
        await asyncio.sleep(0.08)
        assert heartbeat.read_text() == before
        await asyncio.wait_for(asyncio.shield(output), timeout=1)
        assert unrelated.returncode is None
    finally:
        gate.touch()
        if child is None and pid_file.exists():
            child = psutil.Process(int(pid_file.read_text()))
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
                await asyncio.to_thread(child.wait, timeout=3)
        with suppress(ProcessLookupError):
            parent.kill()
        await asyncio.wait_for(asyncio.shield(output), timeout=3)
        if not scope.closed:
            await scope.force_close()
        unrelated.kill()
        await unrelated.wait()
